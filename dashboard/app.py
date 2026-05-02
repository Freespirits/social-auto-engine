"""Social Auto Engine dashboard.

Run: python -m dashboard.app
Open: http://127.0.0.1:7651

Architecture:
- FastAPI + Jinja2 + HTMX (no SPA build)
- SQLite for the approval queue
- Reuses facebook_api.FacebookAPI from the MCP server
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Make sibling modules importable when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import json

from manager import Manager  # noqa: E402

from . import db  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _time_ago(iso: str | None) -> str:
    """Format an ISO timestamp as 'just now', '5m ago', '3h ago', '2d ago'."""
    if not iso:
        return ""
    from datetime import datetime, timezone
    try:
        ts = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
    except Exception:
        return iso[:16].replace("T", " ") if len(iso) >= 16 else iso

    if secs < 5:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    if secs < 86400 * 7:
        return f"{secs // 86400}d ago"
    return iso[:10]


templates.env.filters["time_ago"] = _time_ago

app = FastAPI(title="Social Auto Engine")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

fb = Manager()
db.init_db()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    pending = db.list_posts(status="pending")
    published = db.list_posts(status="published", limit=10)
    failed = db.list_posts(status="failed", limit=5)
    rejected = db.list_posts(status="rejected", limit=5)
    page_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    wa_templates = _safe_wa_templates() if wa_info.get("connected") else []
    stats = db.stats()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "page": page_info,
            "ig": ig_info,
            "wa": wa_info,
            "wa_templates": wa_templates,
            "pending": pending,
            "published": published,
            "failed": failed,
            "rejected": rejected,
            "stats": stats,
        },
    )


# ---------------------------------------------------------------------------
# HTMX-powered fragments
# ---------------------------------------------------------------------------

@app.post("/compose", response_class=HTMLResponse)
async def compose(
    request: Request,
    message: str = Form(""),
    platform: str = Form("facebook"),
    image_url: str = Form(""),
    recipient: str = Form(""),
    template_name: str = Form(""),
):
    message = message.strip()
    image_url = image_url.strip() or None
    recipient = recipient.strip() or None
    template_name = template_name.strip() or None

    if platform not in {"facebook", "instagram", "whatsapp"}:
        raise HTTPException(400, "Unknown platform")
    if platform != "whatsapp" and not message:
        raise HTTPException(400, "Message cannot be empty")
    if platform == "instagram" and not image_url:
        raise HTTPException(400, "Instagram posts require an image URL.")
    if platform == "whatsapp":
        if not recipient:
            raise HTTPException(400, "WhatsApp messages need a recipient phone number.")
        if not message and not template_name:
            raise HTTPException(400, "WhatsApp messages need either a body or a template.")

    account = {
        "facebook": "Hack-Tech",
        "instagram": "Instagram",
        "whatsapp": "WhatsApp",
    }[platform]

    db.create_post(
        message or f"[Template: {template_name}]",
        account_name=account,
        platform=platform,
        image_url=image_url,
        recipient=recipient,
        template_name=template_name,
    )
    return _refresh_all(request)


@app.post("/approve/{post_id}", response_class=HTMLResponse)
async def approve(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")
    _publish_post(post)
    refreshed = db.get_post(post_id) or post
    if refreshed.get("status") == "published":
        toast = ("success", f"Published to {post['account_name']}")
    else:
        toast = ("error", f"Failed: {refreshed.get('error_message', 'unknown error')[:120]}")
    return _refresh_all(request, toast=toast)


def _publish_post(post: dict) -> None:
    """Dispatch to the right platform adapter and record the result."""
    platform = post.get("platform", "facebook")
    try:
        permalink = None

        if platform == "facebook":
            result = fb.post_to_facebook(post["message"])
            platform_post_id = result.get("id")
            try:
                detail = fb.get_post_permalink(platform_post_id) if platform_post_id else {}
                permalink = detail.get("permalink_url") if isinstance(detail, dict) else None
            except Exception:
                permalink = None

        elif platform == "instagram":
            result = fb.post_to_instagram(
                image_url=post["image_url"], caption=post["message"]
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")
            try:
                detail = fb.ig.get_media_permalink(platform_post_id) if platform_post_id else {}
                permalink = detail.get("permalink") if isinstance(detail, dict) else None
            except Exception:
                permalink = None

        elif platform == "whatsapp":
            recipient = post.get("recipient")
            if not recipient:
                raise RuntimeError("WhatsApp post missing recipient")
            if post.get("template_name"):
                result = fb.send_whatsapp_template(recipient, post["template_name"])
            else:
                result = fb.send_whatsapp_text(recipient, post["message"])
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")  # WA message ID

        else:
            raise RuntimeError(f"Unknown platform: {platform}")

        db.mark_published(post["id"], platform_post_id, permalink)
    except Exception as exc:
        db.mark_failed(post["id"], str(exc))


@app.post("/reject/{post_id}", response_class=HTMLResponse)
async def reject(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")
    db.reject_post(post_id)
    return _refresh_all(request, toast=("info", f"Rejected — won't publish"))


@app.post("/approve-all", response_class=HTMLResponse)
async def approve_all(request: Request):
    pending = db.list_posts(status="pending")
    n = len(pending)
    for post in pending:
        _publish_post(post)
    return _refresh_all(request, toast=("success", f"Approved & published {n} posts"))


@app.get("/favicon.ico")
async def favicon():
    """Serve the SVG favicon for browsers that request /favicon.ico."""
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    fb_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    accounts = []
    accounts.append({
        "platform": "facebook",
        "platform_label": "Facebook",
        "icon_class": "fb",
        "icon_label": "f",
        "name": fb_info.get("name", "—"),
        "id": fb_info.get("id", "—"),
        "connected": bool(fb_info.get("id") and fb_info.get("name")),
        "details": fb_info.get("category", ""),
    })
    accounts.append({
        "platform": "instagram",
        "platform_label": "Instagram",
        "icon_class": "ig",
        "icon_label": "IG",
        "name": f"@{ig_info.get('username')}" if ig_info.get("connected") else "Not connected",
        "id": ig_info.get("id", "—"),
        "connected": bool(ig_info.get("connected")),
        "details": (
            f"{ig_info.get('followers_count', 0):,} followers · {ig_info.get('media_count', 0)} posts"
            if ig_info.get("connected") else ig_info.get("error", "")
        ),
    })
    accounts.append({
        "platform": "whatsapp",
        "platform_label": "WhatsApp",
        "icon_class": "wa",
        "icon_label": "W",
        "name": wa_info.get("verified_name", "—") if wa_info.get("connected") else "Not connected",
        "id": wa_info.get("display_phone_number", "—"),
        "connected": bool(wa_info.get("connected")),
        "details": (
            f"Quality: {wa_info.get('quality_rating', 'UNKNOWN')}"
            if wa_info.get("connected") else wa_info.get("error", "")
        ),
    })
    for plat, label, cls, ic in [
        ("linkedin", "LinkedIn", "li", "in"),
        ("x", "X / Twitter", "x", "𝕏"),
        ("tiktok", "TikTok", "tt", "TT"),
    ]:
        accounts.append({
            "platform": plat,
            "platform_label": label,
            "icon_class": cls,
            "icon_label": ic,
            "name": "Not connected",
            "id": "—",
            "connected": False,
            "details": "Adapter coming — see issues #5 and integrations.md",
        })

    env_summary = {
        "META_APP_ID": os.getenv("META_APP_ID", ""),
        "META_APP_SECRET": "set" if os.getenv("META_APP_SECRET") else "missing",
        "FACEBOOK_PAGE_ID": os.getenv("FACEBOOK_PAGE_ID", ""),
        "FACEBOOK_ACCESS_TOKEN": "set" if os.getenv("FACEBOOK_ACCESS_TOKEN") else "missing",
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID", "—"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "—"),
    }
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"accounts": accounts, "env": env_summary, "stats": db.stats()},
    )


@app.post("/settings/test/{platform}", response_class=HTMLResponse)
async def test_connection(request: Request, platform: str):
    """Re-check connection for a given platform; return updated status row."""
    if platform == "facebook":
        info = _safe_page_info()
        connected = bool(info.get("id"))
        message = info.get("name", "Page check failed") if connected else "Token may have expired"
    elif platform == "instagram":
        info = _safe_ig_info()
        connected = bool(info.get("connected"))
        message = f"@{info.get('username')}" if connected else info.get("error", "Not linked")
    elif platform == "whatsapp":
        info = _safe_wa_info()
        connected = bool(info.get("connected"))
        message = info.get("verified_name", "OK") if connected else info.get("error", "")
    else:
        connected, message = False, "Adapter not implemented"
    response = HTMLResponse(
        f'<span class="conn-status {"ok" if connected else "off"}">'
        f'{"✓ Connected · " + message if connected else "✗ " + message}'
        f'</span>'
    )
    response.headers["HX-Trigger"] = json.dumps({
        "toast": {
            "kind": "success" if connected else "error",
            "message": f"{platform.title()}: {message}",
        }
    })
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_all(request: Request, toast: tuple[str, str] | None = None) -> HTMLResponse:
    response = templates.TemplateResponse(
        request,
        "_columns.html",
        {
            "pending": db.list_posts(status="pending"),
            "published": db.list_posts(status="published", limit=10),
            "failed": db.list_posts(status="failed", limit=5),
            "rejected": db.list_posts(status="rejected", limit=5),
            "stats": db.stats(),
        },
    )
    if toast:
        kind, message = toast
        response.headers["HX-Trigger"] = json.dumps({"toast": {"kind": kind, "message": message}})
    return response


def _safe_page_info() -> dict:
    """Best-effort page info; never crashes the dashboard if the API is unhappy."""
    try:
        info = fb.get_page_info() if hasattr(fb, "get_page_info") else {}
        if isinstance(info, dict) and "name" in info:
            return info
    except Exception:
        pass
    page_id = os.getenv("FACEBOOK_PAGE_ID", "?")
    return {"id": page_id, "name": "Hack-Tech", "category": "Education website"}


def _safe_ig_info() -> dict:
    """Lookup Instagram account; safe fallback when token is missing/expired."""
    try:
        info = fb.get_instagram_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_wa_info() -> dict:
    """Lookup WhatsApp Business phone-number info."""
    try:
        info = fb.get_whatsapp_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_wa_templates() -> list[dict]:
    try:
        return [t for t in fb.list_whatsapp_templates() if t.get("status") == "APPROVED"]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import uvicorn

    port = int(os.getenv("DASHBOARD_PORT", "7651"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
