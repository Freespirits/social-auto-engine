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

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Make sibling modules importable when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
# Also load persisted OAuth tokens written by the /oauth/<platform>/callback flows
load_dotenv(Path.home() / ".social-auto-engine" / "tokens.env", override=False)

import json  # noqa: E402

from manager import Manager  # noqa: E402

from . import db  # noqa: E402
from . import scheduler  # noqa: E402
from .auth import (  # noqa: E402
    AuthMiddleware,
    auth_required,
    check_password,
    create_session_token,
    COOKIE_NAME,
    SESSION_MAX_AGE,
)

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

from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start scheduler on boot, stop on shutdown."""
    db.init_db()
    scheduler.start()
    yield
    scheduler.shutdown(wait=True)


app = FastAPI(title="Social Auto Engine", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

fb = Manager()


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

def _sidebar_groups() -> list[dict]:
    """Build the sidebar accounts list, grouped by parent company.

    Returned shape:
        [
          {"company": "Meta", "accounts": [{cls, icon, label, connected, platform}, ...]},
          {"company": "LinkedIn", "accounts": [...]},
          ...
        ]
    Order is fixed: Meta → LinkedIn → TikTok → YouTube → X.
    """
    page_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
    linkedin_info = _safe_linkedin_info()
    tiktok_info = _safe_tiktok_info()
    youtube_info = _safe_youtube_info()

    return [
        {
            "company": "Meta",
            "key": "meta",
            "accounts": [
                {
                    "platform": "facebook",
                    "cls": "fb",
                    "icon": "f",
                    "label": page_info.get("name", "Facebook"),
                    "connected": bool(page_info.get("id")),
                },
                {
                    "platform": "instagram",
                    "cls": "ig",
                    "icon": "IG",
                    "label": f"@{ig_info.get('username')}" if ig_info.get("connected") else "Instagram",
                    "connected": ig_info.get("connected", False),
                },
                {
                    "platform": "threads",
                    "cls": "th",
                    "icon": "@",
                    "label": f"@{threads_info.get('username')}" if threads_info.get("connected") else "Threads",
                    "connected": threads_info.get("connected", False),
                },
                {
                    "platform": "whatsapp",
                    "cls": "wa",
                    "icon": "W",
                    "label": wa_info.get("display_phone_number", "WhatsApp") if wa_info.get("connected") else "WhatsApp",
                    "connected": wa_info.get("connected", False),
                },
            ],
        },
        {
            "company": "LinkedIn",
            "key": "linkedin",
            "accounts": [
                {
                    "platform": "linkedin",
                    "cls": "li",
                    "icon": "in",
                    "label": linkedin_info.get("name", "LinkedIn") if linkedin_info.get("connected") else "LinkedIn",
                    "connected": linkedin_info.get("connected", False),
                },
            ],
        },
        {
            "company": "TikTok",
            "key": "tiktok",
            "accounts": [
                {
                    "platform": "tiktok",
                    "cls": "tt",
                    "icon": "TT",
                    "label": (
                        f"@{tiktok_info.get('username')}"
                        if tiktok_info.get("connected") and tiktok_info.get("username")
                        else (tiktok_info.get("name") if tiktok_info.get("connected") else "TikTok")
                    ),
                    "connected": tiktok_info.get("connected", False),
                },
            ],
        },
        {
            "company": "YouTube",
            "key": "youtube",
            "accounts": [
                {
                    "platform": "youtube",
                    "cls": "yt",
                    "icon": "YT",
                    "label": youtube_info.get("name", "YouTube") if youtube_info.get("connected") else "YouTube",
                    "connected": youtube_info.get("connected", False),
                },
            ],
        },
        {
            "company": "X",
            "key": "x",
            "accounts": [
                {
                    "platform": "x",
                    "cls": "x",
                    "icon": "\U0001d54f",
                    "label": "X / Twitter",
                    "connected": False,
                },
            ],
        },
    ]


def _base_context(active_nav: str = "inbox") -> dict:
    """Common template context shared by all pages."""
    return {
        "stats": db.stats(),
        "sidebar_groups": _sidebar_groups(),
        "active_nav": active_nav,
        "auth_active": auth_required(),
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = _base_context("inbox")
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
    linkedin_info = _safe_linkedin_info()
    wa_templates = _safe_wa_templates() if wa_info.get("connected") else []
    pending_singles, pending_groups = db.list_pending_grouped()
    ctx.update({
        "page": _safe_page_info(),
        "ig": ig_info,
        "wa": wa_info,
        "threads": threads_info,
        "linkedin": linkedin_info,
        "wa_templates": wa_templates,
        "pending": pending_singles,
        "pending_groups": pending_groups,
        "published": db.list_posts(status="published", limit=10),
        "failed": db.list_posts(status="failed", limit=5),
        "rejected": db.list_posts(status="rejected", limit=5),
    })
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar(request: Request):
    from datetime import datetime, timezone as tz, timedelta

    # Default to this week (Mon–Sun)
    now = datetime.now(tz.utc)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=7)

    cal_posts = db.calendar_posts(monday.isoformat(), sunday.isoformat())
    ctx = _base_context("calendar")
    ctx["posts_json"] = json.dumps(cal_posts, default=str)
    return templates.TemplateResponse(request, "calendar.html", ctx)


@app.get("/api/calendar")
async def api_calendar(start: str = "", end: str = ""):
    """JSON endpoint for the calendar JS to fetch posts for a given week."""
    from fastapi.responses import JSONResponse
    if not start or not end:
        return JSONResponse([])
    posts = db.calendar_posts(start, end)
    return JSONResponse(posts)


@app.get("/published", response_class=HTMLResponse)
async def published_page(request: Request):
    ctx = _base_context("published")
    ctx["published"] = db.list_posts(status="published", limit=50)
    return templates.TemplateResponse(request, "published.html", ctx)


# ---------------------------------------------------------------------------
# HTMX-powered fragments
# ---------------------------------------------------------------------------

SUPPORTED_PLATFORMS = {"facebook", "instagram", "whatsapp", "threads", "linkedin"}
BROADCAST_PLATFORMS = {"facebook", "instagram", "threads", "linkedin"}
ACCOUNT_LABELS = {
    "facebook": "Hack-Tech",
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
    "threads": "Threads",
    "linkedin": "LinkedIn",
}


@app.post("/compose", response_class=HTMLResponse)
async def compose(
    request: Request,
    message: str = Form(""),
    platform: str = Form(""),
    platforms: list[str] = Form([]),
    image_url: str = Form(""),
    recipient: str = Form(""),
    template_name: str = Form(""),
):
    """Create one or more pending posts.

    Two ways to call this:
    - Single platform (legacy / direct message): pass `platform=facebook` etc.
    - Broadcast: pass `platforms=facebook&platforms=instagram&...`. Creates one
      group_id and N pending rows, one per platform.
    """
    message = message.strip()
    image_url = image_url.strip() or None
    recipient = recipient.strip() or None
    template_name = template_name.strip() or None

    targets = [p.strip() for p in platforms if p and p.strip()]
    if not targets and platform.strip():
        targets = [platform.strip()]
    if not targets:
        raise HTTPException(400, "Pick at least one platform.")

    unknown = [p for p in targets if p not in SUPPORTED_PLATFORMS]
    if unknown:
        raise HTTPException(400, f"Unknown platform(s): {', '.join(unknown)}")

    if "whatsapp" in targets and len(targets) > 1:
        raise HTTPException(
            400,
            "WhatsApp messages are 1:1 and cannot be combined with broadcast platforms.",
        )

    if "whatsapp" in targets:
        if not recipient:
            raise HTTPException(400, "WhatsApp messages need a recipient phone number.")
        if not message and not template_name:
            raise HTTPException(400, "WhatsApp messages need either a body or a template.")
    else:
        if not message:
            raise HTTPException(400, "Message cannot be empty.")
        if "instagram" in targets and not image_url:
            raise HTTPException(400, "Instagram posts require an image URL.")

    if len(targets) == 1:
        only = targets[0]
        db.create_post(
            message or f"[Template: {template_name}]",
            account_name=ACCOUNT_LABELS[only],
            platform=only,
            image_url=image_url,
            recipient=recipient,
            template_name=template_name,
        )
    else:
        broadcast_targets = [
            {"platform": p, "account_name": ACCOUNT_LABELS[p]} for p in targets
        ]
        db.create_broadcast(
            message=message,
            targets=broadcast_targets,
            image_url=image_url,
        )

    return _refresh_all(request)


@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, topic: str = Form("")):
    """Generate a post draft via the configured AI provider.

    The Sparkles button on the compose form posts a topic here and
    receives the generated post text in the response body. The client
    drops it into the textarea so the user can edit before submitting.
    """
    from content.generator import GeneratorError, generate_post

    topic = topic.strip()
    if not topic:
        raise HTTPException(400, "Topic must not be empty.")
    try:
        text = generate_post(topic, project_root=ROOT)
    except GeneratorError as exc:
        raise HTTPException(500, str(exc))
    return HTMLResponse(text)


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

        elif platform == "threads":
            if post.get("image_url"):
                result = fb.post_image_to_threads(
                    image_url=post["image_url"], text=post["message"]
                )
            else:
                result = fb.post_text_to_threads(post["message"])
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")
            try:
                detail = fb.threads.get_thread_permalink(platform_post_id) if platform_post_id else {}
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

        elif platform == "linkedin":
            result = fb.post_to_linkedin(
                message=post["message"],
                image_url=post.get("image_url"),
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")

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
    return _refresh_all(request, toast=("info", "Rejected — won't publish"))


@app.post("/approve-all", response_class=HTMLResponse)
async def approve_all(request: Request):
    pending = db.list_posts(status="pending")
    n = len(pending)
    for post in pending:
        _publish_post(post)
    return _refresh_all(request, toast=("success", f"Approved & published {n} posts"))


@app.post("/approve-group/{group_id}", response_class=HTMLResponse)
async def approve_group(request: Request, group_id: str):
    """Publish every pending row sharing this group_id."""
    rows = db.list_group(group_id, status="pending")
    if not rows:
        raise HTTPException(404, "No pending posts in this group")

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for post in rows:
        _publish_post(post)
        refreshed = db.get_post(post["id"])
        platform_label = (post.get("platform") or "?").title()
        if refreshed and refreshed.get("status") == "published":
            succeeded.append(platform_label)
        else:
            err = (refreshed or {}).get("error_message") or "unknown error"
            failed.append((platform_label, err[:80]))

    if not failed:
        toast = ("success", f"Published to {', '.join(succeeded)}")
    elif not succeeded:
        toast = ("error", f"All {len(failed)} publishes failed. See activity log.")
    else:
        broken = ", ".join(f"{p} ({reason})" for p, reason in failed)
        toast = (
            "warning",
            f"Published {len(succeeded)} of {len(rows)}. Failed: {broken}",
        )
    return _refresh_all(request, toast=toast)


@app.post("/reject-group/{group_id}", response_class=HTMLResponse)
async def reject_group(request: Request, group_id: str):
    """Reject every pending row sharing this group_id."""
    rows = db.list_group(group_id, status="pending")
    if not rows:
        raise HTTPException(404, "No pending posts in this group")
    for post in rows:
        db.reject_post(post["id"])
    return _refresh_all(
        request,
        toast=("info", f"Rejected broadcast — {len(rows)} posts won't publish"),
    )


@app.get("/favicon.ico")
async def favicon():
    """Serve the SVG favicon for browsers that request /favicon.ico."""
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login form.  Redirect to / if already authenticated or auth is off."""
    if not auth_required():
        return RedirectResponse(url="/", status_code=303)
    from .auth import validate_session_token
    token = request.cookies.get(COOKIE_NAME)
    if token and validate_session_token(token):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form("")):
    """Validate password and set session cookie."""
    if not auth_required():
        return RedirectResponse(url="/", status_code=303)
    if not check_password(password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Incorrect password"}, status_code=401,
        )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout():
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# OAuth connect flows (LinkedIn / TikTok / YouTube)
# ---------------------------------------------------------------------------
#
# Each platform has the same shape:
#   GET  /oauth/<platform>/start    -> redirects to provider auth page
#   GET  /oauth/<platform>/callback -> exchanges ?code= for tokens, persists
#
# Tokens are persisted to ~/.social-auto-engine/tokens.env using the same
# key names the adapters read at boot. When the user signs in next, the
# tokens are loaded by python-dotenv (see lifespan / load_dotenv) or by
# the adapter's os.getenv on init.
#
# We DO NOT write back to the project's repo .env file. The token store
# is a separate file under the user's home directory.

import secrets  # noqa: E402

TOKENS_PATH = Path.home() / ".social-auto-engine" / "tokens.env"


def _store_tokens(updates: dict[str, str]) -> None:
    """Write or update KEY=VALUE pairs in ~/.social-auto-engine/tokens.env.

    Also updates the live os.environ AND patches the in-memory adapter
    instances so the running dashboard sees the new tokens without restart.
    """
    TOKENS_PATH.parent.mkdir(exist_ok=True)
    existing: dict[str, str] = {}
    if TOKENS_PATH.exists():
        for line in TOKENS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            existing[k.strip()] = v.strip()
    existing.update({k: v for k, v in updates.items() if v})
    TOKENS_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    # Push to live env so a fresh adapter init sees them
    for k, v in updates.items():
        if v:
            os.environ[k] = v
    # Patch the live adapter instances so we don't need a restart
    if "LINKEDIN_ACCESS_TOKEN" in updates:
        fb.linkedin.access_token = updates["LINKEDIN_ACCESS_TOKEN"]
        fb.linkedin._person_urn = None  # force re-fetch on next call
    if "TIKTOK_ACCESS_TOKEN" in updates:
        fb.tiktok.access_token = updates["TIKTOK_ACCESS_TOKEN"]
    if "YOUTUBE_ACCESS_TOKEN" in updates:
        fb.youtube.access_token = updates["YOUTUBE_ACCESS_TOKEN"]
    if "YOUTUBE_REFRESH_TOKEN" in updates:
        fb.youtube.refresh_token = updates["YOUTUBE_REFRESH_TOKEN"]


def _public_redirect_uri(request: Request, platform: str) -> str:
    """Compute the OAuth callback URL for a given platform.

    Default: derive from the request's base URL so localhost works without
    any configuration.

    Override: set OAUTH_REDIRECT_BASE_URL in the environment when the
    dashboard runs behind a reverse proxy or tunnel and the redirect URI
    needs to match exactly what was registered in the platform dev portal.
    Example value: "https://yourdomain.com" (no trailing slash).
    """
    override = os.getenv("OAUTH_REDIRECT_BASE_URL", "").rstrip("/")
    base = override or str(request.base_url).rstrip("/")
    return f"{base}/oauth/{platform}/callback"


def _verify_oauth_state(request: Request, cookie_name: str, supplied_state: str) -> None:
    """Reject the callback when the state cookie is missing or doesn't match.

    Prevents CSRF: an attacker cannot trick a logged-in user into accepting
    OAuth credentials they did not start. The cookie is set during /start
    and removed after the callback runs.
    """
    expected = request.cookies.get(cookie_name)
    if not expected:
        raise HTTPException(
            400,
            "OAuth flow not properly initiated (no state cookie). "
            "Start the connection from the Settings page.",
        )
    if not supplied_state or supplied_state != expected:
        raise HTTPException(400, "OAuth state mismatch")


@app.get("/oauth/linkedin/start")
async def oauth_linkedin_start(request: Request):
    """Kick off the LinkedIn OAuth dance."""
    redirect_uri = _public_redirect_uri(request, "linkedin")
    state = secrets.token_urlsafe(16)
    url = fb.linkedin.get_auth_url(redirect_uri) + f"&state={state}"
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("linkedin_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/oauth/linkedin/callback")
async def oauth_linkedin_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Receive ?code= from LinkedIn, exchange for token, store, redirect."""
    if error:
        raise HTTPException(400, f"LinkedIn auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "linkedin_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "linkedin")
    result = fb.linkedin.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    _store_tokens({"LINKEDIN_ACCESS_TOKEN": token})
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("linkedin_oauth_state")
    return response


@app.get("/oauth/tiktok/start")
async def oauth_tiktok_start(request: Request):
    redirect_uri = _public_redirect_uri(request, "tiktok")
    state = secrets.token_urlsafe(16)
    url = fb.tiktok.get_auth_url(redirect_uri, state=state)
    response = RedirectResponse(url=url, status_code=303)
    # Stash the state in a short-lived cookie so we can validate the callback
    response.set_cookie("tiktok_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/oauth/tiktok/callback")
async def oauth_tiktok_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        raise HTTPException(400, f"TikTok auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "tiktok_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "tiktok")
    result = fb.tiktok.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    updates = {
        "TIKTOK_ACCESS_TOKEN": token,
    }
    if result.get("refresh_token"):
        updates["TIKTOK_REFRESH_TOKEN"] = result["refresh_token"]
    _store_tokens(updates)
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("tiktok_oauth_state")
    return response


@app.get("/oauth/youtube/start")
async def oauth_youtube_start(request: Request):
    redirect_uri = _public_redirect_uri(request, "youtube")
    state = secrets.token_urlsafe(16)
    url = fb.youtube.get_auth_url(redirect_uri, state=state)
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("youtube_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.post("/oauth/{platform}/disconnect")
async def oauth_disconnect(request: Request, platform: str):
    """Clear stored tokens for a platform and patch the live adapter."""
    if platform not in {"linkedin", "tiktok", "youtube"}:
        raise HTTPException(404, f"Unknown platform: {platform}")

    keys_to_clear = {
        "linkedin": ["LINKEDIN_ACCESS_TOKEN"],
        "tiktok": ["TIKTOK_ACCESS_TOKEN", "TIKTOK_REFRESH_TOKEN"],
        "youtube": ["YOUTUBE_ACCESS_TOKEN", "YOUTUBE_REFRESH_TOKEN"],
    }[platform]

    # Remove keys from the persisted tokens file
    if TOKENS_PATH.exists():
        existing: dict[str, str] = {}
        for line in TOKENS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() not in keys_to_clear:
                existing[k.strip()] = v.strip()
        TOKENS_PATH.write_text(
            "\n".join(f"{k}={v}" for k, v in existing.items()) + ("\n" if existing else ""),
            encoding="utf-8",
        )

    # Clear from live env
    for key in keys_to_clear:
        os.environ.pop(key, None)

    # Patch the live adapter instance
    if platform == "linkedin":
        fb.linkedin.access_token = None
        fb.linkedin._person_urn = None
    elif platform == "tiktok":
        fb.tiktok.access_token = None
    elif platform == "youtube":
        fb.youtube.access_token = None
        fb.youtube.refresh_token = None

    return RedirectResponse(url="/settings", status_code=303)


@app.get("/oauth/youtube/callback")
async def oauth_youtube_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        raise HTTPException(400, f"YouTube auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "youtube_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "youtube")
    result = fb.youtube.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    updates = {"YOUTUBE_ACCESS_TOKEN": token}
    if result.get("refresh_token"):
        updates["YOUTUBE_REFRESH_TOKEN"] = result["refresh_token"]
    _store_tokens(updates)
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("youtube_oauth_state")
    return response


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    fb_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
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
    accounts.append({
        "platform": "threads",
        "platform_label": "Threads",
        "icon_class": "th",
        "icon_label": "@",
        "name": f"@{threads_info.get('username')}" if threads_info.get("connected") else "Not connected",
        "id": threads_info.get("id", "—"),
        "connected": bool(threads_info.get("connected")),
        "details": (
            threads_info.get("name", "")
            if threads_info.get("connected") else threads_info.get("error", "")
        ),
    })
    linkedin_info = _safe_linkedin_info()
    accounts.append({
        "platform": "linkedin",
        "platform_label": "LinkedIn",
        "icon_class": "li",
        "icon_label": "in",
        "name": linkedin_info.get("name", "Not connected") if linkedin_info.get("connected") else "Not connected",
        "id": linkedin_info.get("id", "—"),
        "connected": bool(linkedin_info.get("connected")),
        "details": (
            linkedin_info.get("email", "")
            if linkedin_info.get("connected") else linkedin_info.get("error", "")
        ),
    })
    tiktok_info = _safe_tiktok_info()
    accounts.append({
        "platform": "tiktok",
        "platform_label": "TikTok",
        "icon_class": "tt",
        "icon_label": "TT",
        "name": (
            f"@{tiktok_info.get('username')}"
            if tiktok_info.get("connected") and tiktok_info.get("username")
            else (tiktok_info.get("name", "Not connected") if tiktok_info.get("connected") else "Not connected")
        ),
        "id": tiktok_info.get("id", "—"),
        "connected": bool(tiktok_info.get("connected")),
        "details": (
            f"{tiktok_info.get('follower_count', 0):,} followers"
            if tiktok_info.get("connected") else tiktok_info.get("error", "")
        ),
    })
    youtube_info = _safe_youtube_info()
    accounts.append({
        "platform": "youtube",
        "platform_label": "YouTube",
        "icon_class": "yt",
        "icon_label": "YT",
        "name": youtube_info.get("name", "Not connected") if youtube_info.get("connected") else "Not connected",
        "id": youtube_info.get("id", "—"),
        "connected": bool(youtube_info.get("connected")),
        "details": (
            f"{youtube_info.get('subscriber_count', 0):,} subscribers · {youtube_info.get('video_count', 0)} videos"
            if youtube_info.get("connected") else youtube_info.get("error", "")
        ),
    })
    accounts.append({
        "platform": "x",
        "platform_label": "X / Twitter",
        "icon_class": "x",
        "icon_label": "\U0001d54f",
        "name": "Not connected",
        "id": "—",
        "connected": False,
        "details": "Adapter planned — paid API tier required ($100/mo Basic).",
    })

    env_summary = {
        "META_APP_ID": os.getenv("META_APP_ID", ""),
        "META_APP_SECRET": "set" if os.getenv("META_APP_SECRET") else "missing",
        "FACEBOOK_PAGE_ID": os.getenv("FACEBOOK_PAGE_ID", ""),
        "FACEBOOK_ACCESS_TOKEN": "set" if os.getenv("FACEBOOK_ACCESS_TOKEN") else "missing",
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID", "—"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "—"),
        "THREADS_APP_ID": os.getenv("THREADS_APP_ID", "—"),
        "THREADS_ACCESS_TOKEN": "set" if os.getenv("THREADS_ACCESS_TOKEN") else "missing",
        "LINKEDIN_CLIENT_ID": os.getenv("LINKEDIN_CLIENT_ID", "—"),
        "LINKEDIN_CLIENT_SECRET": "set" if os.getenv("LINKEDIN_CLIENT_SECRET") else "missing",
        "LINKEDIN_ACCESS_TOKEN": "set" if os.getenv("LINKEDIN_ACCESS_TOKEN") else "missing",
        "TIKTOK_CLIENT_KEY": os.getenv("TIKTOK_CLIENT_KEY", "—"),
        "TIKTOK_CLIENT_SECRET": "set" if os.getenv("TIKTOK_CLIENT_SECRET") else "missing",
        "TIKTOK_ACCESS_TOKEN": "set" if os.getenv("TIKTOK_ACCESS_TOKEN") else "missing",
        "YOUTUBE_CLIENT_ID": os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID") or "—",
        "YOUTUBE_CLIENT_SECRET": "set" if (os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")) else "missing",
        "YOUTUBE_ACCESS_TOKEN": "set" if os.getenv("YOUTUBE_ACCESS_TOKEN") else "missing",
        "YOUTUBE_REFRESH_TOKEN": "set" if os.getenv("YOUTUBE_REFRESH_TOKEN") else "missing",
    }
    ctx = _base_context("settings")
    ctx.update({"accounts": accounts, "env": env_summary})
    return templates.TemplateResponse(request, "settings.html", ctx)


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
    elif platform == "threads":
        info = _safe_threads_info()
        connected = bool(info.get("connected"))
        message = f"@{info.get('username')}" if connected else info.get("error", "Not linked")
    elif platform == "linkedin":
        info = _safe_linkedin_info()
        connected = bool(info.get("connected"))
        message = info.get("name", "OK") if connected else info.get("error", "Not linked")
    elif platform == "tiktok":
        info = _safe_tiktok_info()
        connected = bool(info.get("connected"))
        message = (
            f"@{info.get('username')}" if connected and info.get("username")
            else info.get("name", "OK") if connected
            else info.get("error", "Not linked")
        )
    elif platform == "youtube":
        info = _safe_youtube_info()
        connected = bool(info.get("connected"))
        message = info.get("name", "OK") if connected else info.get("error", "Not linked")
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
# Scheduler routes
# ---------------------------------------------------------------------------

@app.post("/schedule/{post_id}", response_class=HTMLResponse)
async def schedule_post(request: Request, post_id: int, at: str = Form("")):
    """Schedule a pending post for future publication."""
    from datetime import datetime, timezone as tz

    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] not in ("pending", "scheduled"):
        raise HTTPException(409, f"Post is {post['status']}, cannot schedule")

    at = at.strip()
    if not at:
        raise HTTPException(400, "Missing 'at' — provide an ISO-8601 datetime")

    try:
        run_at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=tz.utc)
    except ValueError:
        raise HTTPException(400, f"Bad datetime: {at}")

    if run_at <= datetime.now(tz.utc):
        raise HTTPException(400, "Scheduled time must be in the future")

    scheduler.schedule_post(post_id, run_at)
    return _refresh_all(
        request,
        toast=("success", f"Scheduled post #{post_id} for {run_at:%Y-%m-%d %H:%M} UTC"),
    )


@app.post("/unschedule/{post_id}", response_class=HTMLResponse)
async def unschedule_post(request: Request, post_id: int):
    """Cancel a scheduled post and return it to pending."""
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "scheduled":
        raise HTTPException(409, f"Post is {post['status']}, not scheduled")

    removed = scheduler.cancel_post(post_id)
    if removed:
        toast = ("info", f"Post #{post_id} unscheduled — back to pending")
    else:
        toast = ("warning", f"Post #{post_id} job not found, reset to pending")
    return _refresh_all(request, toast=toast)


@app.get("/schedules", response_class=HTMLResponse)
async def list_schedules(request: Request):
    """Return all scheduled posts + active APScheduler jobs."""
    scheduled = db.list_scheduled()
    jobs = scheduler.list_jobs()
    return templates.TemplateResponse(
        request,
        "_schedules.html",
        {"scheduled": scheduled, "jobs": jobs},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_all(request: Request, toast: tuple[str, str] | None = None) -> HTMLResponse:
    pending_singles, pending_groups = db.list_pending_grouped()
    response = templates.TemplateResponse(
        request,
        "_columns.html",
        {
            "pending": pending_singles,
            "pending_groups": pending_groups,
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
    """Lookup Facebook page info; safe fallback when token is missing/expired.

    Returns the API result with `connected=True` on success, or a dict with
    `connected=False` and an error string when the call fails. Other helpers
    in this module follow the same shape.
    """
    try:
        info = fb.get_page_info() if hasattr(fb, "get_page_info") else None
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    if isinstance(info, dict) and info.get("id") and info.get("name"):
        # Mark explicitly connected so consumers don't have to infer
        info = {**info, "connected": True}
        return info
    return {"connected": False, "error": "Facebook page check returned no name/id"}


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


def _safe_threads_info() -> dict:
    """Lookup Threads account; safe fallback when token is missing/expired."""
    try:
        info = fb.get_threads_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_linkedin_info() -> dict:
    """Lookup LinkedIn profile; safe fallback when token is missing/expired."""
    try:
        info = fb.get_linkedin_profile()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_tiktok_info() -> dict:
    """Lookup TikTok profile; safe fallback when token is missing/expired."""
    try:
        info = fb.get_tiktok_profile()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_youtube_info() -> dict:
    """Lookup YouTube channel info; safe fallback when token is missing/expired."""
    try:
        info = fb.get_youtube_channel_info()
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
