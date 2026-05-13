"""Read-only demo mode for the dashboard.

Enabled with the env var ``DEMO_MODE=1``. When enabled:

* The DB is wiped and re-seeded with a curated set of dummy posts on every
  boot so visitors land on a populated inbox, calendar, and published feed.
* All seven platform adapters report as connected with realistic fake
  account names, without any real Graph API calls or tokens.
* All write endpoints (publish, approve, reject, schedule, oauth/*, settings
  writes) return 403 with a friendly "clone the repo to try it for real"
  message. Read endpoints work normally.
* Onboarding is marked complete and the auth password is bypassed so
  visitors land directly on the inbox.

The demo lives at https://huggingface.co/spaces/Freespirits/social-auto-engine
(behind a small Dockerfile in the repo root). Nothing here can publish to
any real social platform, by design.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


def is_demo_mode() -> bool:
    """Truthy if DEMO_MODE env var is set to 1, true, yes, or on."""
    return os.environ.get("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Fake platform info
# ---------------------------------------------------------------------------

# Used by app._safe_*_info() when in demo mode so the sidebar shows every
# platform as connected without touching the real Graph API.
DEMO_PLATFORM_INFO = {
    "facebook": {
        "connected": True,
        "id": "demo_fb_page",
        "name": "Social Auto Demo Co.",
        "fan_count": 12480,
        "picture": {"data": {"url": "/static/landing-dashboard-inbox.png"}},
    },
    "instagram": {
        "connected": True,
        "id": "demo_ig_account",
        "username": "social.auto.demo",
        "followers_count": 8420,
        "media_count": 142,
    },
    "whatsapp": {
        "connected": True,
        "id": "demo_wa_account",
        "display_phone_number": "+44 20 7946 0958",
        "verified_name": "Social Auto Demo",
        "quality_rating": "GREEN",
    },
    "threads": {
        "connected": True,
        "id": "demo_threads_account",
        "username": "social.auto.demo",
        "name": "Social Auto Demo",
    },
    "linkedin": {
        "connected": True,
        "id": "demo_linkedin",
        "name": "Social Auto Demo Co.",
        "profile_url": "https://linkedin.com/in/demo",
    },
    "tiktok": {
        "connected": False,
        "error": "Awaiting full app review for direct-post tier (video.publish scope).",
    },
    "youtube": {
        "connected": False,
        "error": "Awaiting OAuth consent screen verification for Data API v3 publish scope.",
    },
}


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

# Realistic but obviously fake posts that show off every state and platform.
# Times are computed relative to the boot time so the "x ago" labels stay
# fresh on each restart.
def _seed_posts(now: datetime) -> list[dict]:
    """Build the list of seed posts. ``now`` is the reference timestamp."""

    def ago(**kwargs):
        return (now - timedelta(**kwargs)).isoformat()

    def ahead(**kwargs):
        return (now + timedelta(**kwargs)).isoformat()

    return [
        # ----- Pending (3) -----
        {
            "message": "Just shipped: every adapter now reports as connected. The "
                       "approval queue is the safety story we keep telling and we "
                       "are not bored of it yet.",
            "platform": "facebook",
            "account_name": "Social Auto Demo Co.",
            "status": "pending",
            "created_at": ago(minutes=4),
        },
        {
            "message": "Behind the scenes from the studio today. Eight platforms, "
                       "one composer, zero silent automation.",
            "platform": "instagram",
            "account_name": "social.auto.demo",
            "status": "pending",
            "created_at": ago(minutes=11),
            "image_url": "/static/landing-dashboard-inbox.png",
        },
        {
            "message": "Tuesday weekly digest is queued for 1,240 subscribers. "
                       "Hit Approve to send.",
            "platform": "whatsapp",
            "account_name": "Social Auto Demo",
            "status": "pending",
            "created_at": ago(minutes=22),
        },
        # ----- Published (5) -----
        {
            "message": "Releasing v0.1.0-alpha today. Five platforms live, two in "
                       "review, MIT licensed, self-hosted.",
            "platform": "facebook",
            "account_name": "Social Auto Demo Co.",
            "status": "published",
            "created_at": ago(hours=2),
            "published_at": ago(hours=2),
            "permalink_url": "https://facebook.com/demo/posts/1",
        },
        {
            "message": "Featured on Awesome MCP Servers. Tiny step, big motivation.",
            "platform": "threads",
            "account_name": "social.auto.demo",
            "status": "published",
            "created_at": ago(hours=5),
            "published_at": ago(hours=5),
            "permalink_url": "https://threads.net/@demo/post/1",
        },
        {
            "message": "Q4 numbers landed and the team is celebrating responsibly. "
                       "Thanks to everyone who shipped this quarter.",
            "platform": "linkedin",
            "account_name": "Social Auto Demo Co.",
            "status": "published",
            "created_at": ago(days=1, hours=3),
            "published_at": ago(days=1, hours=3),
            "permalink_url": "https://linkedin.com/feed/update/demo-1",
        },
        {
            "message": "Weekly digest sent to 1,240 contacts.",
            "platform": "whatsapp",
            "account_name": "Social Auto Demo",
            "status": "published",
            "created_at": ago(days=2),
            "published_at": ago(days=2),
        },
        {
            "message": "New product drop is live. Limited stock, no pre-orders.",
            "platform": "instagram",
            "account_name": "social.auto.demo",
            "status": "published",
            "created_at": ago(days=3, hours=4),
            "published_at": ago(days=3, hours=4),
            "permalink_url": "https://instagram.com/p/demo1",
            "image_url": "/static/landing-dashboard-settings.png",
        },
        # ----- Scheduled (3) -----
        {
            "message": "Thursday office hours at 3pm UK time. Bring your questions "
                       "about MCP, the approval queue, or anything else.",
            "platform": "linkedin",
            "account_name": "Social Auto Demo Co.",
            "status": "scheduled",
            "created_at": ago(minutes=40),
            "scheduled_for": ahead(hours=18),
        },
        {
            "message": "Friday recap going out at 5pm. Three shipped features, two "
                       "bugs found, one happy maintainer.",
            "platform": "facebook",
            "account_name": "Social Auto Demo Co.",
            "status": "scheduled",
            "created_at": ago(hours=1),
            "scheduled_for": ahead(days=2),
        },
        {
            "message": "Monday morning thread on the Q1 roadmap. Save it for later.",
            "platform": "threads",
            "account_name": "social.auto.demo",
            "status": "scheduled",
            "created_at": ago(hours=3),
            "scheduled_for": ahead(days=4),
        },
        # ----- Failed (2) -----
        {
            "message": "Reaction post on the Q4 earnings call. Needs legal review.",
            "platform": "linkedin",
            "account_name": "Social Auto Demo Co.",
            "status": "failed",
            "created_at": ago(hours=6),
            "error_message": "Rejected during review. Reason: needs legal sign-off.",
        },
        {
            "message": "Test post from the demo dashboard.",
            "platform": "facebook",
            "account_name": "Social Auto Demo Co.",
            "status": "failed",
            "created_at": ago(days=4),
            "error_message": "(#100) The post could not be created at this time. "
                             "Rate limit reached for application.",
        },
    ]


def seed_demo_data() -> None:
    """Wipe the post table and insert the curated demo posts.

    Called from app startup when ``is_demo_mode()`` returns True. Also marks
    onboarding as complete so visitors land on the inbox, not the welcome
    flow.
    """
    if not is_demo_mode():
        return

    from . import db

    now = datetime.now(timezone.utc)

    with db.connect() as conn:
        conn.execute("DELETE FROM post")
        for p in _seed_posts(now):
            conn.execute(
                "INSERT INTO post (message, platform, account_name, status, "
                "created_at, published_at, permalink_url, image_url, "
                "scheduled_for, error_message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    p["message"],
                    p["platform"],
                    p["account_name"],
                    p["status"],
                    p["created_at"],
                    p.get("published_at"),
                    p.get("permalink_url"),
                    p.get("image_url"),
                    p.get("scheduled_for"),
                    p.get("error_message"),
                ),
            )
        conn.commit()

    db.set_setting("onboarding.completed", "true")


# ---------------------------------------------------------------------------
# Write-block middleware
# ---------------------------------------------------------------------------

# Routes that can run in demo mode even though they technically POST.
# /login is needed if a password is set. /logout is harmless.
_DEMO_POST_ALLOWLIST = {"/login", "/logout"}

# GET routes with side effects that we also need to block.
_DEMO_GET_DENYLIST_PREFIXES = ("/oauth/",)


class DemoWriteBlockMiddleware(BaseHTTPMiddleware):
    """Reject every write endpoint with a friendly 403 in demo mode.

    The approval queue's safety story is "no silent automation" (CLAUDE.md
    section 5). On the public demo we make that literal: no request can
    publish, approve, reject, schedule, or reconfigure anything. Visitors
    who want the real thing get pointed at the README.
    """

    async def dispatch(self, request, call_next):
        if not is_demo_mode():
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()

        is_write = (
            method in {"POST", "PUT", "PATCH", "DELETE"}
            and path not in _DEMO_POST_ALLOWLIST
        ) or (
            method == "GET"
            and any(path.startswith(prefix) for prefix in _DEMO_GET_DENYLIST_PREFIXES)
        )

        if not is_write:
            return await call_next(request)

        message = (
            "Read-only demo. Actions are disabled here to keep the safety "
            "story honest. Clone the repo to take it live: "
            "https://github.com/Freespirits/social-auto-engine"
        )

        # HTMX requests want a small inline message; everything else gets JSON.
        if request.headers.get("HX-Request") == "true":
            return Response(
                content=(
                    '<div class="demo-block">'
                    'Read-only demo. <a href="https://github.com/Freespirits/social-auto-engine" '
                    'target="_blank" rel="noopener">Clone the repo</a> to take it live.'
                    '</div>'
                ),
                status_code=403,
                media_type="text/html; charset=utf-8",
            )
        return JSONResponse({"error": "demo_mode", "message": message}, status_code=403)
