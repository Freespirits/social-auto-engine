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

from manager import Manager  # noqa: E402

from . import db  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
    stats = db.stats()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "page": page_info,
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
async def compose(request: Request, message: str = Form(...)):
    message = message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty")
    db.create_post(message)
    return _refresh_all(request)


@app.post("/approve/{post_id}", response_class=HTMLResponse)
async def approve(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")

    try:
        result = fb.post_to_facebook(post["message"])
        platform_post_id = result.get("id")
        permalink = None
        if platform_post_id:
            try:
                detail = fb.get_post_permalink(platform_post_id)
                permalink = detail.get("permalink_url") if isinstance(detail, dict) else None
            except Exception:
                permalink = None
        db.mark_published(post_id, platform_post_id, permalink)
    except Exception as exc:
        db.mark_failed(post_id, str(exc))

    return _refresh_all(request)


@app.post("/reject/{post_id}", response_class=HTMLResponse)
async def reject(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")
    db.reject_post(post_id)
    return _refresh_all(request)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_all(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import uvicorn

    port = int(os.getenv("DASHBOARD_PORT", "7651"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
