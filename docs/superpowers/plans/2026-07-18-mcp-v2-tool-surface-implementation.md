# MCP v2 Tool Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `server.py` so it exposes 15 always-on MCP tools plus 4 flag-gated direct-write tools (19 total) instead of the current 46, with every Facebook-calling tool wrapped in a uniform `{"success": bool, "data"|"error": ...}` envelope, and fix the `FACEBOOK_ACCESS_TOKEN` / `FACEBOOK_PAGE_ACCESS_TOKEN` naming bug.

**Architecture:** A new `mcp_support.py` module owns the error envelope, Graph error-code hints, and the `SOCIALBLAST_ALLOW_DIRECT_WRITES` flag check. `manager.py` gains one new method (`get_post_engagement`) and loses 22 methods that become unreachable once their sole caller (an old single-purpose MCP tool) is deleted. `server.py` is rewritten in three sections: pipeline/queue tools (unchanged 6 + 5 new), Facebook read-only tools (4, consolidated from 12 old ones), and direct-write tools (4, flag-gated, consolidated from 17 old ones). `facebook_api.py` and the dashboard's own publish path (`dashboard/app.py`'s `fb = Manager()` calls) are untouched.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP) 1.27+, pytest, sqlite3 (via `dashboard/db.py`).

**Source spec:** `docs/specs/2026-07-17-mcp-v2-tool-surface-design.md` — read it before starting; this plan implements it section by section.

## Global Constraints

- Python 3.11+, `from __future__ import annotations` in new files.
- Type hints on public functions.
- British English, no em dashes, no semicolons in prose (user-facing copy and docstrings/comments — code punctuation is unaffected).
- No changes to `facebook_api.py` semantics (spec non-goal — every new call goes through existing `facebook_api.py` / `manager.py` methods, never a modified Graph call shape).
- No MCP tool may approve or publish a post from the approval queue. Approval stays human-only in the dashboard.
- Every commit is a working, test-passing state. Run `python -m pytest -q` before each commit in this plan.

## Assumptions made while turning the spec into tasks (flag if wrong)

1. **Envelope scope.** The spec says the envelope decorator wraps "every tool," but section 4.1 says the 6 pre-existing pipeline tools are "kept unchanged in behaviour," and section 8 says to *extend* `tests/test_mcp_socialblast_tools.py` "following its existing patterns" — those existing tests assert directly on flat return shapes (`result["count"]`, `result["ok"]`, `data["video"]`, etc.), which a blanket envelope would break. This plan applies `mcp_support.envelope` only to the 8 tools that call `facebook_api.py`/`manager.py` Graph methods (the 4 read tools + 4 direct-write tools) — the tools the spec's "Problem" section is actually about (raw Graph JSON, no error handling). The 11 pipeline/queue tools keep their existing `{"ok"|"count"|"group_id": ...}` shapes.
2. **`facebook_get_post_engagement` metric scope.** Section 4.4 explicitly folds the 6 reaction and 4 impression tools into this one call. `get_post_insights`, `get_post_engaged_users`, `get_post_clicks`, and `get_number_of_likes` aren't mentioned anywhere in section 4 (neither kept nor explicitly removed). This plan treats them as folded into `facebook_get_post_engagement` too (or dropped, for `get_number_of_likes`, which duplicates the `like` entry in the reaction breakdown) — the alternative reading (silently keeping 4 more single-purpose tools alive) contradicts the "15 core tools" success criterion.
3. **`after` pagination cursor.** `facebook_api.py` cannot be modified and its `get_posts()` method takes no paging params. `facebook_get_posts` accepts `after` for forward compatibility but does not yet wire it to a real Graph cursor; `limit` is applied as a client-side truncation of Graph's default page. This is documented honestly in the tool's docstring rather than faked.
4. **`socialblast_create_draft`'s `scheduled_time`.** The spec says this tool wraps `db.create_post(status="pending")` — status is always `pending`, never `scheduled`. So `scheduled_time` is stored as metadata (the `scheduled_for` column) but does **not** arm APScheduler via `dashboard/scheduler.schedule_post()`. Wiring it to the live scheduler would let an MCP tool call cause an unattended future publish with no approval click, which section 5 of CLAUDE.md forbids outright ("No exceptions").
5. **CHANGELOG entry placement.** The existing `## [Unreleased]` section already has unrelated pending entries (LinkedIn/TikTok/YouTube adapters). This plan does not touch or rename that section — it inserts a new `## [v0.7] - 2026-07-18` section between `[Unreleased]` and `[v0.6]`, containing only the MCP v2 changes. Bundling the pre-existing `[Unreleased]` content into v0.7 as well is a separate decision for whoever cuts that release.
6. **Out of scope, flagged, not fixed:** `docs/try-mcp.md` and `dashboard/app.py:380` (`_has("FACEBOOK_PAGE_ACCESS_TOKEN")` in the dashboard's own `/api/status` endpoint) have the same stale-tool-count / wrong-env-var-name problems this spec fixes elsewhere, but neither file is in the spec's file plan (section 7). Left alone per "don't silently widen scope." Worth a follow-up issue.

---

### Task 1: `mcp_support.py` — error envelope, Graph error hints, flag check

**Files:**
- Create: `mcp_support.py`
- Test: `tests/test_mcp_support.py`

**Interfaces:**
- Produces: `mcp_support.direct_writes_enabled() -> bool`, `mcp_support.require_env(*names: str) -> dict[str, Any] | None`, `mcp_support.envelope(fn) -> Callable[..., dict[str, Any]]`, `mcp_support.DEFAULT_HINT: str`, `mcp_support.DIRECT_WRITE_FLAG: str`. These are consumed by Task 4's `server.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_support.py`:

```python
"""Tests for mcp_support.py — the MCP error envelope and flag helpers."""
from __future__ import annotations

import mcp_support


class TestDirectWritesEnabled:
    def test_false_when_unset(self, monkeypatch):
        monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
        assert mcp_support.direct_writes_enabled() is False

    def test_true_values(self, monkeypatch):
        for value in ("true", "True", "1", "yes"):
            monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", value)
            assert mcp_support.direct_writes_enabled() is True

    def test_false_for_other_values(self, monkeypatch):
        monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", "false")
        assert mcp_support.direct_writes_enabled() is False


class TestRequireEnv:
    def test_none_when_all_set(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "value")
        assert mcp_support.require_env("SOME_KEY") is None

    def test_envelope_when_missing(self, monkeypatch):
        monkeypatch.delenv("SOME_MISSING_KEY", raising=False)
        result = mcp_support.require_env("SOME_MISSING_KEY")
        assert result["success"] is False
        assert "SOME_MISSING_KEY" in result["error"]["message"]
        assert result["error"]["code"] == "missing_config"


class TestEnvelope:
    def test_wraps_plain_return_as_success(self):
        @mcp_support.envelope
        def fn():
            return {"id": "123"}

        assert fn() == {"success": True, "data": {"id": "123"}}

    def test_rewraps_graph_error(self):
        @mcp_support.envelope
        def fn():
            return {"error": {"code": 190, "message": "Invalid OAuth access token"}}

        result = fn()
        assert result["success"] is False
        assert result["error"]["code"] == "190"
        assert "access token" in result["error"]["hint"].lower()

    def test_unmapped_error_code_gets_default_hint(self):
        @mcp_support.envelope
        def fn():
            return {"error": {"code": 999, "message": "Something weird"}}

        result = fn()
        assert result["success"] is False
        assert result["error"]["hint"] == mcp_support.DEFAULT_HINT

    def test_catches_exceptions(self):
        @mcp_support.envelope
        def fn():
            raise ValueError("boom")

        result = fn()
        assert result["success"] is False
        assert result["error"]["code"] == "internal_error"
        assert "boom" in result["error"]["message"]

    def test_passes_through_existing_envelope(self):
        @mcp_support.envelope
        def fn():
            return {"success": False, "error": {"code": "missing_config", "message": "x", "hint": "y"}}

        assert fn()["error"]["code"] == "missing_config"

    def test_rate_limit_codes_get_wait_hint(self):
        for code in (4, 17, 32):

            @mcp_support.envelope
            def fn(code=code):
                return {"error": {"code": code, "message": "rate limited"}}

            result = fn()
            assert "wait" in result["error"]["hint"].lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_mcp_support.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_support'`

- [ ] **Step 3: Write `mcp_support.py`**

```python
"""Shared support for the MCP tool surface in server.py.

Provides the uniform success/error envelope, Graph API error-code hints,
the SOCIALBLAST_ALLOW_DIRECT_WRITES flag check, and environment validation
used by the Facebook read and direct-write tools. See
docs/specs/2026-07-17-mcp-v2-tool-surface-design.md section 5.
"""
from __future__ import annotations

import functools
import os
from typing import Any, Callable

DIRECT_WRITE_FLAG = "SOCIALBLAST_ALLOW_DIRECT_WRITES"

GRAPH_ERROR_HINTS: dict[int, str] = {
    190: (
        "The Facebook access token is invalid or expired. Run "
        "`python -m scripts.refresh_token <SHORT_LIVED_USER_TOKEN>` or "
        "reconnect Facebook from the dashboard Settings page."
    ),
    100: (
        "This metric may have been deprecated by Meta. "
        "facebook_get_post_engagement lists the metrics still supported."
    ),
    4: "Facebook is rate-limiting this app. Wait a few minutes before retrying.",
    17: "Facebook is rate-limiting this app. Wait a few minutes before retrying.",
    32: "Facebook is rate-limiting this app. Wait a few minutes before retrying.",
}

DEFAULT_HINT = "See docs/meta-survival-guide.md if this keeps happening."


def direct_writes_enabled() -> bool:
    """True when SOCIALBLAST_ALLOW_DIRECT_WRITES opts into direct-write tools."""
    return os.environ.get(DIRECT_WRITE_FLAG, "").strip().lower() in {"1", "true", "yes"}


def require_env(*names: str) -> dict[str, Any] | None:
    """Return an error envelope if any `names` env var is unset, else None."""
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if not missing:
        return None
    return {
        "success": False,
        "error": {
            "code": "missing_config",
            "message": f"Missing required environment variable(s): {', '.join(missing)}",
            "hint": "Set these in .env or ~/.social-auto-engine/tokens.env, then restart the MCP server.",
        },
    }


def _graph_error_envelope(error: dict[str, Any]) -> dict[str, Any]:
    code = error.get("code")
    hint = GRAPH_ERROR_HINTS.get(code, DEFAULT_HINT)
    return {
        "success": False,
        "error": {
            "code": str(code) if code is not None else "unknown",
            "message": error.get("message", "Unknown Graph API error"),
            "hint": hint,
        },
    }


def envelope(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """Wrap a Graph-calling MCP tool so it always returns a
    {"success": bool, "data"|"error": ...} envelope. Never lets a raw
    Graph error dict or an unhandled exception reach the caller.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            return {
                "success": False,
                "error": {"code": "internal_error", "message": str(exc), "hint": DEFAULT_HINT},
            }
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            return _graph_error_envelope(result["error"])
        if isinstance(result, dict) and "success" in result:
            return result
        return {"success": True, "data": result}

    return wrapper
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_mcp_support.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add mcp_support.py tests/test_mcp_support.py
git commit -m "feat(mcp): add mcp_support.py — error envelope, Graph error hints, direct-write flag"
```

---

### Task 2: Fix the `FACEBOOK_ACCESS_TOKEN` env var bug in `dashboard/health.py`

**Files:**
- Modify: `dashboard/health.py:105`
- Test: `tests/test_health_cli.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_health_cli.py`, add `"FACEBOOK_ACCESS_TOKEN"` to the `ALL_KEYS` list (so `clean_env` also strips it, matching the existing isolation comment at the top of the file):

```python
ALL_KEYS = [
    "HF_API_KEY",
    "HF_API_SECRET",
    "HF_KEY",
    "HIGGSFIELD_API_KEY_ID",
    "HIGGSFIELD_API_KEY_SECRET",
    "REPLICATE_API_TOKEN",
    "ELEVENLABS_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "FACEBOOK_ACCESS_TOKEN",
    "FACEBOOK_PAGE_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "THREADS_ACCESS_TOKEN",
    "LINKEDIN_ACCESS_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "TIKTOK_ACCESS_TOKEN",
]
```

Then add two tests to the `TestCollect` class (after `test_detects_higgsfield_pair`, before `TestRender`):

```python
    def test_detects_facebook_via_documented_env_var(self, clean_env, monkeypatch):
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "token")
        assert health.collect()["platforms"]["facebook"] is True

    def test_detects_facebook_via_legacy_env_var_fallback(self, clean_env, monkeypatch):
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "token")
        assert health.collect()["platforms"]["facebook"] is True
```

- [ ] **Step 2: Run the tests to verify the new one fails**

Run: `python -m pytest tests/test_health_cli.py -k test_detects_facebook_via_documented_env_var -v`
Expected: FAIL — `collect()["platforms"]["facebook"]` is `False` because `health.py` only checks `FACEBOOK_PAGE_ACCESS_TOKEN`.

- [ ] **Step 3: Fix `dashboard/health.py`**

In `collect()`, change:

```python
        "platforms": {
            "facebook": _has("FACEBOOK_PAGE_ACCESS_TOKEN"),
```

to:

```python
        "platforms": {
            "facebook": _has("FACEBOOK_ACCESS_TOKEN") or _has("FACEBOOK_PAGE_ACCESS_TOKEN"),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_health_cli.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add dashboard/health.py tests/test_health_cli.py
git commit -m "fix(health): check FACEBOOK_ACCESS_TOKEN before the legacy FACEBOOK_PAGE_ACCESS_TOKEN name"
```

---

### Task 3: `manager.py` — add `get_post_engagement`, remove methods only the old MCP tools called

**Files:**
- Modify: `manager.py` (full rewrite of the file — see step 3 for complete content)
- Test: `tests/test_manager_engagement.py`

**Interfaces:**
- Produces: `Manager.get_post_engagement(post_id: str) -> dict[str, Any]` returning `{"reactions": dict[str, int|None], "comment_count": int, "share_count": int, "permalink_url": str|None, "impressions": dict[str, int|None], "deprecated_metrics": list[str]}` on success, or `{"error": {...}}` if the post itself can't be read (bad id, expired token). Consumed by Task 4's `facebook_get_post_engagement` tool.
- Consumes: `self.api.get_comments`, `self.api.get_post_permalink`, `self.api.get_insights`, `self.get_post_share_count` (all pre-existing).

**Why these 22 methods are removable:** each one's only caller was a single-purpose MCP tool in the old `server.py` (e.g. `get_post_reactions_like_total`, called only by the old `get_post_reactions_like_total` tool). A repo-wide grep (`grep -rn "manager\.<name>\|fb\.<name>" --include=*.py .`, run against every one of the 40 old Facebook tool names) confirms `dashboard/app.py` only calls `fb.post_to_facebook`, `fb.get_post_permalink`, and `fb.get_page_info` — nothing else. Those three, plus everything the new consolidated tools in Task 4 call, are kept.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manager_engagement.py`:

```python
"""Tests for Manager.get_post_engagement — the consolidated engagement
summary behind the facebook_get_post_engagement MCP tool.
"""
from __future__ import annotations

from manager import Manager


def _manager_with_stubbed_api(monkeypatch, **overrides):
    m = Manager()

    defaults = {
        "get_comments": lambda post_id: {"data": [{"id": "1"}, {"id": "2"}]},
        "get_post_permalink": lambda post_id: {"permalink_url": "https://facebook.com/p/1"},
        "get_post_share_count": lambda post_id: 5,
        "get_insights": lambda post_id, metric, period="lifetime": {
            "data": [{"name": metric, "values": [{"value": 10}]}]
        },
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(m.api, name, fn)
    return m


class TestGetPostEngagement:
    def test_happy_path_shape(self, monkeypatch):
        m = _manager_with_stubbed_api(monkeypatch)
        result = m.get_post_engagement("123")
        assert result["comment_count"] == 2
        assert result["share_count"] == 5
        assert result["permalink_url"] == "https://facebook.com/p/1"
        assert set(result["reactions"]) == {"like", "love", "wow", "haha", "sorry", "anger"}
        assert all(v == 10 for v in result["reactions"].values())
        assert set(result["impressions"]) == {"total", "unique", "paid", "organic"}
        assert result["deprecated_metrics"] == []

    def test_deprecated_metric_degrades_to_null(self, monkeypatch):
        def get_insights(post_id, metric, period="lifetime"):
            if metric == "post_impressions_paid":
                return {"error": {"code": 100, "message": "metric is deprecated"}}
            return {"data": [{"name": metric, "values": [{"value": 7}]}]}

        m = _manager_with_stubbed_api(monkeypatch, get_insights=get_insights)
        result = m.get_post_engagement("123")
        assert result["impressions"]["paid"] is None
        assert "post_impressions_paid" in result["deprecated_metrics"]
        assert result["impressions"]["total"] == 7
        assert "error" not in result

    def test_comment_fetch_error_short_circuits(self, monkeypatch):
        m = _manager_with_stubbed_api(
            monkeypatch,
            get_comments=lambda post_id: {"error": {"code": 190, "message": "expired token"}},
        )
        result = m.get_post_engagement("123")
        assert result == {"error": {"code": 190, "message": "expired token"}}

    def test_permalink_fetch_error_short_circuits(self, monkeypatch):
        m = _manager_with_stubbed_api(
            monkeypatch,
            get_post_permalink=lambda post_id: {"error": {"code": 190, "message": "expired token"}},
        )
        result = m.get_post_engagement("123")
        assert "error" in result
        assert result["error"]["code"] == 190
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_manager_engagement.py -v`
Expected: FAIL with `AttributeError: 'Manager' object has no attribute 'get_post_engagement'`

- [ ] **Step 3: Rewrite `manager.py`**

Replace the entire contents of `manager.py` with:

```python
import os
from pathlib import Path
from typing import Any

from facebook_api import FacebookAPI
from instagram_api import InstagramAPI
from whatsapp_api import WhatsAppAPI
from threads_api import ThreadsAPI
from linkedin_api import LinkedInAPI
from tiktok_api import TikTokAPI
from youtube_api import YouTubeAPI


class Manager:
    def __init__(self):
        self.api = FacebookAPI()
        self.ig = InstagramAPI()
        self.wa = WhatsAppAPI()
        self.threads = ThreadsAPI()
        self.linkedin = LinkedInAPI()
        self.tiktok = TikTokAPI()
        self.youtube = YouTubeAPI()

    def refresh_facebook_token(self, short_lived_user_token: str) -> str:
        """Refresh the Facebook Page access token from a short-lived user token.

        Reads `META_APP_ID`, `META_APP_SECRET`, and `FACEBOOK_PAGE_ID` from
        the environment. Exchanges `short_lived_user_token` for a long-lived
        user token, derives the Page access token via `/me/accounts`, writes
        the new token back to `.env`, and returns it.

        The dashboard can call this on a 401 response by surfacing a form
        that asks the user to paste a fresh Graph API Explorer token.
        """
        from scripts.refresh_token import (
            TokenRefreshError,
            refresh_page_token,
            write_token_to_env,
        )

        app_id = os.environ.get("META_APP_ID")
        app_secret = os.environ.get("META_APP_SECRET")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        missing = [
            name
            for name, value in (
                ("META_APP_ID", app_id),
                ("META_APP_SECRET", app_secret),
                ("FACEBOOK_PAGE_ID", page_id),
            )
            if not value
        ]
        if missing:
            raise TokenRefreshError(
                f"Missing required env vars: {', '.join(missing)}"
            )

        page_token = refresh_page_token(
            short_lived_user_token, app_id, app_secret, page_id
        )
        write_token_to_env(Path.cwd() / ".env", page_token)
        return page_token

    def post_to_facebook(self, message: str) -> dict[str, Any]:
        return self.api.post_message(message)

    # --- Instagram passthroughs (used by the dashboard) ---
    def get_instagram_account_info(self) -> dict[str, Any]:
        return self.ig.get_account_info()

    def post_to_instagram(self, image_url: str, caption: str = "") -> dict[str, Any]:
        return self.ig.publish_image(image_url, caption)

    def post_reel_to_instagram(self, video_url: str, caption: str = "") -> dict[str, Any]:
        return self.ig.publish_reel(video_url, caption)

    def get_instagram_media(self, limit: int = 10) -> dict[str, Any]:
        return self.ig.get_recent_media(limit)

    # --- Threads passthroughs ---
    def get_threads_account_info(self) -> dict[str, Any]:
        return self.threads.get_account_info()

    def post_text_to_threads(self, text: str, reply_control: str | None = None) -> dict[str, Any]:
        return self.threads.publish_text(text, reply_control)

    def post_image_to_threads(self, image_url: str, text: str = "") -> dict[str, Any]:
        return self.threads.publish_image(image_url, text)

    def post_video_to_threads(self, video_url: str, text: str = "") -> dict[str, Any]:
        return self.threads.publish_video(video_url, text)

    def get_recent_threads(self, limit: int = 10) -> dict[str, Any]:
        return self.threads.get_recent_threads(limit)

    def get_thread_insights(self, thread_id: str) -> dict[str, Any]:
        return self.threads.get_thread_insights(thread_id)

    def delete_thread(self, thread_id: str) -> dict[str, Any]:
        return self.threads.delete_thread(thread_id)

    # --- WhatsApp passthroughs ---
    def get_whatsapp_account_info(self) -> dict[str, Any]:
        return self.wa.get_account_info()

    def list_whatsapp_templates(self) -> list[dict[str, Any]]:
        return self.wa.list_templates()

    def send_whatsapp_template(self, to: str, template_name: str = "hello_world", language: str = "en_US") -> dict[str, Any]:
        return self.wa.send_template(to, template_name, language)

    def send_whatsapp_text(self, to: str, message: str) -> dict[str, Any]:
        return self.wa.send_text(to, message)

    def reply_to_comment(self, post_id: str, comment_id: str, message: str) -> dict[str, Any]:
        return self.api.reply_to_comment(comment_id, message)

    def get_page_posts(self) -> dict[str, Any]:
        return self.api.get_posts()

    def get_post_comments(self, post_id: str) -> dict[str, Any]:
        return self.api.get_comments(post_id)

    def delete_post(self, post_id: str) -> dict[str, Any]:
        return self.api.delete_post(post_id)

    def post_image_to_facebook(self, image_url: str, caption: str) -> dict[str, Any]:
        return self.api.post_image_to_facebook(image_url, caption)

    def send_dm_to_user(self, user_id: str, message: str) -> dict[str, Any]:
        return self.api.send_dm_to_user(user_id, message)

    def update_post(self, post_id: str, new_message: str) -> dict[str, Any]:
        return self.api.update_post(post_id, new_message)

    def schedule_post(self, message: str, publish_time: int) -> dict[str, Any]:
        return self.api.schedule_post(message, publish_time)

    def get_page_fan_count(self) -> int:
        return self.api.get_page_fan_count()

    def get_post_share_count(self, post_id: str) -> int:
        return self.api.get_post_share_count(post_id)

    def bulk_delete_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Delete multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.delete_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def bulk_hide_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Hide multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.hide_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def bulk_unhide_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Unhide multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.unhide_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def get_comment_replies(self, comment_id: str) -> dict[str, Any]:
        return self.api.get_comment_replies(comment_id)

    def get_post_permalink(self, post_id: str) -> dict[str, Any]:
        return self.api.get_post_permalink(post_id)

    def get_scheduled_posts(self) -> dict[str, Any]:
        return self.api.get_scheduled_posts()

    def get_page_info(self) -> dict[str, Any]:
        return self.api.get_page_info()

    _REACTION_METRICS = {
        "like": "post_reactions_like_total",
        "love": "post_reactions_love_total",
        "wow": "post_reactions_wow_total",
        "haha": "post_reactions_haha_total",
        "sorry": "post_reactions_sorry_total",
        "anger": "post_reactions_anger_total",
    }
    _IMPRESSION_METRICS = {
        "total": "post_impressions",
        "unique": "post_impressions_unique",
        "paid": "post_impressions_paid",
        "organic": "post_impressions_organic",
    }

    def get_post_engagement(self, post_id: str) -> dict[str, Any]:
        """Single-call engagement summary: reactions, comments, shares, permalink, impressions.

        Insight metrics Meta has deprecated degrade to null with a note in
        "deprecated_metrics" instead of failing the whole call — each metric
        is fetched individually so one bad metric can't take down the rest.
        A failure on the underlying post lookup itself (bad post_id, expired
        token) short-circuits and returns {"error": ...} so
        mcp_support.envelope can rewrap it as a hard failure.
        """
        comments = self.api.get_comments(post_id)
        if "error" in comments:
            return {"error": comments["error"]}
        permalink = self.api.get_post_permalink(post_id)
        if "error" in permalink:
            return {"error": permalink["error"]}

        reactions, reaction_notes = self._bulk_metric_values(post_id, self._REACTION_METRICS)
        impressions, impression_notes = self._bulk_metric_values(post_id, self._IMPRESSION_METRICS)

        return {
            "reactions": reactions,
            "comment_count": len(comments.get("data", [])),
            "share_count": self.get_post_share_count(post_id),
            "permalink_url": permalink.get("permalink_url"),
            "impressions": impressions,
            "deprecated_metrics": reaction_notes + impression_notes,
        }

    def _bulk_metric_values(
        self, post_id: str, metric_map: dict[str, str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Fetch each metric individually so one deprecated metric doesn't fail the rest."""
        values: dict[str, Any] = {}
        deprecated: list[str] = []
        for label, metric in metric_map.items():
            raw = self.api.get_insights(post_id, metric)
            if "error" in raw:
                values[label] = None
                deprecated.append(metric)
                continue
            data = raw.get("data", [{}])
            values[label] = data[0].get("values", [{}])[0].get("value") if data else None
        return values, deprecated

    # --- LinkedIn passthroughs ---
    def get_linkedin_profile(self) -> dict[str, Any]:
        return self.linkedin.get_profile()

    def post_to_linkedin(self, message: str, image_url: str | None = None, article_url: str | None = None) -> dict[str, Any]:
        if image_url:
            return self.linkedin.post_image(image_url, message)
        if article_url:
            return self.linkedin.post_article(article_url, message)
        return self.linkedin.post_text(message)

    def post_image_to_linkedin(self, image_url: str, text: str = "") -> dict[str, Any]:
        return self.linkedin.post_image(image_url, text)

    def post_article_to_linkedin(self, article_url: str, text: str = "") -> dict[str, Any]:
        return self.linkedin.post_article(article_url, text)

    def delete_linkedin_post(self, post_id: str) -> dict[str, Any]:
        return self.linkedin.delete_post(post_id)

    # --- TikTok passthroughs ---
    def get_tiktok_profile(self) -> dict[str, Any]:
        return self.tiktok.get_profile()

    def post_to_tiktok(
        self,
        video_url: str | None = None,
        video_path: str | None = None,
    ) -> dict[str, Any]:
        """Push a video to the user's TikTok inbox / drafts.

        The user finalises and publishes from the TikTok app itself.
        This is the inbox-upload tier; direct publishing requires the
        video.publish scope and full app review.
        """
        return self.tiktok.upload_to_inbox(video_url=video_url, video_path=video_path)

    def get_tiktok_publish_status(self, publish_id: str) -> dict[str, Any]:
        return self.tiktok.get_publish_status(publish_id)

    # --- YouTube passthroughs ---
    def get_youtube_channel_info(self) -> dict[str, Any]:
        return self.youtube.get_channel_info()

    def post_to_youtube(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy_status: str = "private",
    ) -> dict[str, Any]:
        """Upload a local video to the authenticated user's channel.

        Defaults privacy_status='private'. The user can switch to public
        from the dashboard once they have reviewed the upload.
        """
        return self.youtube.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
        )

    def delete_youtube_video(self, video_id: str) -> dict[str, Any]:
        return self.youtube.delete_video(video_id)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_manager_engagement.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite to confirm no other test relied on a removed method**

Run: `python -m pytest -q`
Expected: All tests pass except `tests/test_mcp_socialblast_tools.py`, which will fail in Task 4 (old `server.py` still imports the just-removed manager methods until Task 4 rewrites it). If anything else fails, stop and investigate before continuing — do not proceed into Task 4 with an unexplained failure.

Since `server.py` at this point still has `manager.get_post_reactions_like_total(...)` etc., importing `server` now raises `AttributeError` at call time (not import time — the decorator-registered functions don't execute their bodies until called). Confirm this is the only new failure category:

Run: `python -m pytest tests/test_mcp_socialblast_tools.py -q 2>&1 | tail -20`
Expected: Failures only in tests that call one of the 40 old single-purpose tools, not in `TestRegistration`/`TestSignatures`/`TestStatusTool`/`TestCampaignTool`/`TestEnrichTool`/`TestViralityTool`/`TestListPendingTool` (those exercise only the 6 unchanged pipeline tools). This confirms Task 3 removed exactly the methods Task 4 is about to stop calling.

- [ ] **Step 6: Commit**

```bash
git add manager.py tests/test_manager_engagement.py
git commit -m "feat(manager): add get_post_engagement, remove methods only removed MCP tools called"
```

---

### Task 4: Rewrite `server.py` around the new 19-tool surface

**Files:**
- Modify: `server.py` (full rewrite — see step 3)
- Modify: `tests/test_mcp_socialblast_tools.py` (extended — see step 1)
- Modify: `.env.example` (add the direct-write flag — see step 5)

**Interfaces:**
- Consumes: `mcp_support.envelope`, `mcp_support.direct_writes_enabled`, `mcp_support.require_env` (Task 1); `manager.get_post_engagement` and all kept `Manager` methods (Task 3); `dashboard.db` functions (`create_post`, `get_post`, `update_post`, `reject_post`, `search_posts`, `stats`, `list_scheduled`, `list_posts` — all pre-existing, unmodified).
- Produces: the final tool surface consumed by MCP clients — no other module calls into `server.py`.

- [ ] **Step 1: Replace `tests/test_mcp_socialblast_tools.py` with the extended test file**

Replace the entire contents of `tests/test_mcp_socialblast_tools.py` with:

```python
"""Tests for the MCP tools defined in server.py, the 15 always-on tools
(11 pipeline/queue + 4 Facebook read-only) plus the 4 flag-gated
direct-write tools. See docs/specs/2026-07-17-mcp-v2-tool-surface-design.md.
"""
from __future__ import annotations

import importlib
import inspect

import pytest


SOCIALBLAST_TOOLS = [
    "socialblast_generate_campaign",
    "socialblast_enrich_post",
    "socialblast_enrich_campaign",
    "socialblast_predict_virality",
    "socialblast_status",
    "socialblast_list_pending",
]

NEW_QUEUE_TOOLS = [
    "socialblast_create_draft",
    "socialblast_edit_pending",
    "socialblast_reject_pending",
    "socialblast_search_posts",
    "socialblast_queue_stats",
]

READ_TOOLS = [
    "facebook_get_posts",
    "facebook_get_post_engagement",
    "facebook_get_comments",
    "facebook_get_page_info",
]

DIRECT_WRITE_TOOLS = [
    "facebook_publish_now",
    "facebook_manage_post",
    "facebook_moderate_comment",
    "facebook_send_dm",
]

REMOVED_TOOLS = [
    "post_to_facebook", "reply_to_comment", "get_page_posts", "get_post_comments",
    "delete_post", "delete_comment", "hide_comment", "unhide_comment",
    "delete_comment_from_post", "filter_negative_comments", "get_number_of_comments",
    "get_number_of_likes", "get_post_insights", "get_post_impressions",
    "get_post_impressions_unique", "get_post_impressions_paid", "get_post_impressions_organic",
    "get_post_engaged_users", "get_post_clicks", "get_post_reactions_like_total",
    "get_post_reactions_love_total", "get_post_reactions_wow_total", "get_post_reactions_haha_total",
    "get_post_reactions_sorry_total", "get_post_reactions_anger_total", "get_post_top_commenters",
    "post_image_to_facebook", "send_dm_to_user", "update_post", "schedule_post",
    "get_page_fan_count", "get_post_share_count", "get_post_reactions_breakdown",
    "bulk_delete_comments", "bulk_hide_comments", "bulk_unhide_comments",
    "get_comment_replies", "get_post_permalink", "get_scheduled_posts", "get_page_info",
]


@pytest.fixture
def fb_env(monkeypatch):
    """Satisfy _require_facebook_config() so read/direct-write tool tests
    reach their mocked manager calls instead of short-circuiting."""
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "1234567890")
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "test-token")


class TestRegistration:
    def test_all_six_pipeline_tools_registered(self):
        import server
        for name in SOCIALBLAST_TOOLS:
            assert hasattr(server, name), f"Missing MCP tool: {name}"
            assert callable(getattr(server, name)), f"Not callable: {name}"

    def test_each_pipeline_tool_has_docstring(self):
        import server
        for name in SOCIALBLAST_TOOLS:
            fn = getattr(server, name)
            assert fn.__doc__, f"{name} has no docstring"
            assert len(fn.__doc__.strip()) > 10, f"{name} docstring too short"

    def test_five_new_queue_tools_registered(self):
        import server
        for name in NEW_QUEUE_TOOLS:
            assert hasattr(server, name), f"Missing MCP tool: {name}"
            assert callable(getattr(server, name)), f"Not callable: {name}"

    def test_four_read_tools_registered(self):
        import server
        for name in READ_TOOLS:
            assert hasattr(server, name), f"Missing MCP tool: {name}"
            assert callable(getattr(server, name)), f"Not callable: {name}"


class TestOldToolsRemoved:
    def test_all_forty_old_tools_gone(self):
        import server
        assert len(REMOVED_TOOLS) == 40
        for name in REMOVED_TOOLS:
            assert not hasattr(server, name), f"{name} should have been removed"


class TestToolCount:
    def test_exactly_fifteen_tools_without_flag(self, monkeypatch):
        import server
        monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
        importlib.reload(server)
        names = {t.name for t in server.mcp._tool_manager.list_tools()}
        assert len(names) == 15
        for direct_write_tool in DIRECT_WRITE_TOOLS:
            assert direct_write_tool not in names

    def test_nineteen_tools_with_flag(self, monkeypatch):
        import server
        monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", "true")
        importlib.reload(server)
        try:
            names = {t.name for t in server.mcp._tool_manager.list_tools()}
            assert len(names) == 19
        finally:
            monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
            importlib.reload(server)


class TestDirectWriteFlag:
    def test_absent_by_default(self, monkeypatch):
        import server
        monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
        importlib.reload(server)
        for name in DIRECT_WRITE_TOOLS:
            assert not hasattr(server, name), f"{name} should not be registered without the flag"

    def test_present_when_flag_set(self, monkeypatch):
        import server
        monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", "true")
        importlib.reload(server)
        try:
            for name in DIRECT_WRITE_TOOLS:
                assert hasattr(server, name), f"{name} should be registered with the flag set"
        finally:
            monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
            importlib.reload(server)


class TestSignatures:
    def test_generate_campaign_signature(self):
        import server
        sig = inspect.signature(server.socialblast_generate_campaign)
        params = list(sig.parameters.keys())
        assert "business_description" in params
        assert "platforms" in params

    def test_enrich_post_signature(self):
        import server
        sig = inspect.signature(server.socialblast_enrich_post)
        params = list(sig.parameters.keys())
        assert "post_id" in params
        assert "with_video" in params
        assert sig.parameters["with_video"].default is False

    def test_predict_virality_signature(self):
        import server
        sig = inspect.signature(server.socialblast_predict_virality)
        params = list(sig.parameters.keys())
        assert "prompt" in params
        assert "platform" in params

    def test_status_takes_no_args(self):
        import server
        sig = inspect.signature(server.socialblast_status)
        assert len(sig.parameters) == 0


class TestStatusTool:
    def test_returns_full_shape(self):
        import server
        data = server.socialblast_status()
        assert set(data.keys()) >= {"video", "voice", "captions", "images", "platforms"}

    def test_active_backend_is_one_of_known(self):
        import server
        backend = server.socialblast_status()["video"]["active_backend"]
        assert backend in {"higgsfield", "replicate", "none"}

    def test_no_secrets_in_output(self, monkeypatch):
        import json
        import server

        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "secret-id-do-not-leak")
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "secret-secret-shhh")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-this-must-stay-private")
        text = json.dumps(server.socialblast_status())
        assert "secret-id-do-not-leak" not in text
        assert "secret-secret-shhh" not in text
        assert "sk-this-must-stay-private" not in text

    def test_facebook_true_via_documented_env_var(self, monkeypatch):
        import server
        monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "token")
        assert server.socialblast_status()["platforms"]["facebook"] is True

    def test_facebook_true_via_legacy_env_var_fallback(self, monkeypatch):
        import server
        monkeypatch.delenv("FACEBOOK_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "token")
        assert server.socialblast_status()["platforms"]["facebook"] is True


class TestCampaignTool:
    def test_default_platforms_when_none(self):
        import server
        result = server.socialblast_generate_campaign("Vet clinic in Tel Aviv")
        assert result["count"] == 35
        assert len(result["preview"]) == 3

    def test_custom_platforms(self):
        import server
        result = server.socialblast_generate_campaign("Bakery in Paris", ["facebook"])
        assert result["count"] == 7
        assert "group_id" in result
        assert len(result["post_ids"]) == 7


class TestEnrichTool:
    def test_enrich_nonexistent_post(self):
        import server
        result = server.socialblast_enrich_post(999_999)
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_enrich_runs_steps_on_pending(self):
        import server
        from dashboard import db

        pid = db.create_post(message="Test caption", account_name="Test", platform="facebook")
        result = server.socialblast_enrich_post(pid, with_video=False)
        assert result["ok"] is True
        assert "steps" in result
        assert any(s["step"] == "image" for s in result["steps"])

    def test_with_video_flag_attempts_video_step(self):
        import server
        from dashboard import db

        pid = db.create_post(message="x", account_name="Test", platform="facebook")
        result = server.socialblast_enrich_post(pid, with_video=True)
        steps = [s["step"] for s in result.get("steps", [])]
        assert "image" in steps or "video" in steps


_HF_ENV_VARS = (
    "HF_API_KEY", "HF_API_SECRET", "HF_KEY",
    "HIGGSFIELD_API_KEY_ID", "HIGGSFIELD_API_KEY_SECRET",
)


class TestViralityTool:
    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch):
        for var in _HF_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    def test_stub_without_higgsfield(self):
        import server
        result = server.socialblast_predict_virality("a great caption")
        assert result["score"] is None
        assert "HiggsField" in result["reason"]

    def test_platform_argument_accepted(self):
        import server
        for plat in ["instagram", "tiktok", "facebook", "linkedin"]:
            result = server.socialblast_predict_virality("test", platform=plat)
            assert "score" in result


class TestListPendingTool:
    def test_returns_count_and_posts(self):
        import server
        result = server.socialblast_list_pending()
        assert "count" in result
        assert "posts" in result
        assert isinstance(result["posts"], list)
        assert isinstance(result["count"], int)

    def test_post_shape(self):
        import server
        from dashboard import db

        db.create_post(message="Listed post", account_name="Test", platform="facebook")
        result = server.socialblast_list_pending()
        assert result["count"] >= 1
        sample = result["posts"][0]
        for field in ("id", "message", "platform", "account_name", "image_url", "video_url", "group_id", "created_at"):
            assert field in sample, f"Missing field: {field}"


class TestCreateDraftTool:
    def test_creates_pending_post(self):
        import server
        from dashboard import db

        result = server.socialblast_create_draft("Hello world", "facebook")
        assert result["ok"] is True
        post = db.get_post(result["post_id"])
        assert post["status"] == "pending"
        assert post["message"] == "Hello world"

    def test_rejects_unknown_platform(self):
        import server
        result = server.socialblast_create_draft("Hello", "myspace")
        assert result["ok"] is False
        assert "platform" in result["error"].lower()

    def test_rejects_bad_scheduled_time(self):
        import server
        result = server.socialblast_create_draft("Hello", "facebook", scheduled_time="not-a-date")
        assert result["ok"] is False

    def test_accepts_valid_scheduled_time_without_auto_scheduling(self):
        import server
        from dashboard import db

        result = server.socialblast_create_draft(
            "Hello", "facebook", scheduled_time="2026-08-01T10:00:00+00:00"
        )
        assert result["ok"] is True
        post = db.get_post(result["post_id"])
        assert post["scheduled_for"] == "2026-08-01T10:00:00+00:00"
        assert post["status"] == "pending"


class TestEditPendingTool:
    def test_edits_pending_post(self):
        import server
        from dashboard import db

        pid = db.create_post(message="Old", platform="facebook")
        result = server.socialblast_edit_pending(pid, message="New")
        assert result["ok"] is True
        assert db.get_post(pid)["message"] == "New"

    def test_refuses_nonexistent_post(self):
        import server
        result = server.socialblast_edit_pending(999_999, message="x")
        assert result["ok"] is False

    def test_refuses_non_pending_post(self):
        import server
        from dashboard import db

        pid = db.create_post(message="Old", platform="facebook")
        db.reject_post(pid)
        result = server.socialblast_edit_pending(pid, message="New")
        assert result["ok"] is False
        assert "pending" in result["error"].lower()


class TestRejectPendingTool:
    def test_rejects_pending_post(self):
        import server
        from dashboard import db

        pid = db.create_post(message="X", platform="facebook")
        result = server.socialblast_reject_pending(pid)
        assert result["ok"] is True
        assert db.get_post(pid)["status"] == "rejected"

    def test_refuses_already_rejected_post(self):
        import server
        from dashboard import db

        pid = db.create_post(message="X", platform="facebook")
        db.reject_post(pid)
        result = server.socialblast_reject_pending(pid)
        assert result["ok"] is False


class TestSearchPostsTool:
    def test_finds_by_substring(self):
        import server
        from dashboard import db

        db.create_post(message="Unique needle here", platform="facebook")
        result = server.socialblast_search_posts(q="needle")
        assert result["count"] >= 1
        assert any("needle" in p["message"] for p in result["posts"])

    def test_filters_by_status(self):
        import server
        from dashboard import db

        pid = db.create_post(message="Filtered post", platform="facebook")
        db.reject_post(pid)
        result = server.socialblast_search_posts(status="rejected")
        assert all(p["status"] == "rejected" for p in result["posts"])


class TestQueueStatsTool:
    def test_returns_by_status_and_scheduled(self):
        import server
        from dashboard import db

        db.create_post(message="X", platform="facebook")
        result = server.socialblast_queue_stats()
        assert "by_status" in result
        assert "scheduled" in result
        assert result["by_status"].get("pending", 0) >= 1


class TestFacebookConfigGuard:
    def test_get_posts_missing_config(self, monkeypatch):
        import server
        monkeypatch.delenv("FACEBOOK_PAGE_ID", raising=False)
        monkeypatch.delenv("FACEBOOK_ACCESS_TOKEN", raising=False)
        result = server.facebook_get_posts()
        assert result["success"] is False
        assert result["error"]["code"] == "missing_config"


class TestFacebookGetPosts:
    def test_success_shape(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_posts", lambda: {"data": [{"id": "1"}, {"id": "2"}]})
        result = server.facebook_get_posts()
        assert result["success"] is True
        assert result["data"]["posts"] == [{"id": "1"}, {"id": "2"}]

    def test_respects_limit(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_posts", lambda: {"data": [{"id": str(i)} for i in range(5)]})
        result = server.facebook_get_posts(limit=2)
        assert len(result["data"]["posts"]) == 2

    def test_include_scheduled(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_posts", lambda: {"data": []})
        monkeypatch.setattr(server.manager, "get_scheduled_posts", lambda: {"data": [{"id": "s1"}]})
        result = server.facebook_get_posts(include_scheduled=True)
        assert result["data"]["scheduled"] == [{"id": "s1"}]

    def test_graph_error_envelope(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_posts", lambda: {"error": {"code": 190, "message": "expired"}})
        result = server.facebook_get_posts()
        assert result["success"] is False
        assert result["error"]["code"] == "190"


class TestFacebookGetComments:
    def test_success_shape(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_post_comments", lambda pid: {"data": [{"id": "c1"}]})
        result = server.facebook_get_comments("post1")
        assert result["success"] is True
        assert result["data"]["count"] == 1

    def test_include_replies(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_post_comments", lambda pid: {"data": [{"id": "c1"}]})
        monkeypatch.setattr(server.manager, "get_comment_replies", lambda cid: {"data": [{"id": "r1"}]})
        result = server.facebook_get_comments("post1", include_replies=True)
        assert result["data"]["comments"][0]["replies"] == [{"id": "r1"}]

    def test_graph_error_envelope(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_post_comments", lambda pid: {"error": {"code": 100, "message": "bad"}})
        result = server.facebook_get_comments("post1")
        assert result["success"] is False


class TestFacebookGetPageInfo:
    def test_includes_fan_count(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_info", lambda: {"name": "Test Page"})
        monkeypatch.setattr(server.manager, "get_page_fan_count", lambda: 42)
        result = server.facebook_get_page_info()
        assert result["success"] is True
        assert result["data"]["fan_count"] == 42
        assert result["data"]["name"] == "Test Page"

    def test_graph_error_envelope(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_page_info", lambda: {"error": {"code": 190, "message": "expired"}})
        result = server.facebook_get_page_info()
        assert result["success"] is False


class TestFacebookGetPostEngagement:
    def test_delegates_to_manager(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(
            server.manager,
            "get_post_engagement",
            lambda pid: {
                "reactions": {}, "comment_count": 0, "share_count": 0,
                "permalink_url": None, "impressions": {}, "deprecated_metrics": [],
            },
        )
        result = server.facebook_get_post_engagement("post1")
        assert result["success"] is True
        assert "reactions" in result["data"]

    def test_graph_error_envelope(self, monkeypatch, fb_env):
        import server
        monkeypatch.setattr(server.manager, "get_post_engagement", lambda pid: {"error": {"code": 190, "message": "x"}})
        result = server.facebook_get_post_engagement("post1")
        assert result["success"] is False


class TestDirectWriteTools:
    def _server_with_flag(self, monkeypatch):
        import server
        monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", "true")
        importlib.reload(server)
        return server

    def _reset(self, monkeypatch):
        import server
        monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
        importlib.reload(server)

    def test_publish_now_text(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "post_to_facebook", lambda msg: {"id": "p1"})
            result = server.facebook_publish_now("hello")
            assert result["success"] is True
            assert result["data"]["id"] == "p1"
        finally:
            self._reset(monkeypatch)

    def test_publish_now_with_image(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "post_image_to_facebook", lambda url, caption: {"id": "p2"})
            result = server.facebook_publish_now("caption", image_url="http://x/img.png")
            assert result["data"]["id"] == "p2"
        finally:
            self._reset(monkeypatch)

    def test_publish_now_with_schedule(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "schedule_post", lambda msg, ts: {"id": "p3"})
            result = server.facebook_publish_now("caption", scheduled_publish_time=1893456000)
            assert result["data"]["id"] == "p3"
        finally:
            self._reset(monkeypatch)

    def test_manage_post_update_requires_message(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            result = server.facebook_manage_post("post1", "update")
            assert result["success"] is False
            assert result["error"]["code"] == "bad_request"
        finally:
            self._reset(monkeypatch)

    def test_manage_post_delete(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "delete_post", lambda pid: {"success": True})
            result = server.facebook_manage_post("post1", "delete")
            assert result["success"] is True
        finally:
            self._reset(monkeypatch)

    def test_manage_post_unknown_action(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            result = server.facebook_manage_post("post1", "explode")
            assert result["success"] is False
        finally:
            self._reset(monkeypatch)

    def test_moderate_comment_reply(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "reply_to_comment", lambda pid, cid, msg: {"id": "r1"})
            result = server.facebook_moderate_comment(["c1"], "reply", post_id="p1", message="hi")
            assert result["success"] is True
        finally:
            self._reset(monkeypatch)

    def test_moderate_comment_reply_requires_single_id(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            result = server.facebook_moderate_comment(["c1", "c2"], "reply", post_id="p1", message="hi")
            assert result["success"] is False
        finally:
            self._reset(monkeypatch)

    def test_moderate_comment_hide_bulk(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(
                server.manager, "bulk_hide_comments",
                lambda ids: [{"comment_id": i, "result": {}} for i in ids],
            )
            result = server.facebook_moderate_comment(["c1", "c2"], "hide")
            assert result["success"] is True
            assert len(result["data"]["results"]) == 2
        finally:
            self._reset(monkeypatch)

    def test_moderate_comment_unknown_action(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            result = server.facebook_moderate_comment(["c1"], "explode")
            assert result["success"] is False
        finally:
            self._reset(monkeypatch)

    def test_send_dm(self, monkeypatch, fb_env):
        server = self._server_with_flag(monkeypatch)
        try:
            monkeypatch.setattr(server.manager, "send_dm_to_user", lambda uid, msg: {"success": True})
            result = server.facebook_send_dm("u1", "hi")
            assert result["success"] is True
        finally:
            self._reset(monkeypatch)
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `python -m pytest tests/test_mcp_socialblast_tools.py -q`
Expected: FAIL — `server` still has the old 40-tool surface, no `socialblast_create_draft`/`facebook_get_posts`/etc. yet.

- [ ] **Step 3: Rewrite `server.py`**

Replace the entire contents of `server.py` with:

```python
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

import mcp_support
from manager import Manager

mcp = FastMCP("FacebookMCP")
manager = Manager()

# Kept in sync by hand with dashboard.app.SUPPORTED_PLATFORMS, duplicated
# here so this module never has to import the FastAPI app just for one set.
KNOWN_PLATFORMS = {"facebook", "instagram", "whatsapp", "threads", "linkedin", "tiktok"}


def _require_facebook_config() -> dict[str, Any] | None:
    return mcp_support.require_env("FACEBOOK_PAGE_ID", "FACEBOOK_ACCESS_TOKEN")


# ---------------------------------------------------------------------------
# Pipeline and approval-queue tools (11), always registered.
#
# No tool in this section can approve or publish a post. Approval stays
# human-only in the dashboard (CLAUDE.md section 5).
# ---------------------------------------------------------------------------

@mcp.tool()
def socialblast_status() -> dict[str, Any]:
    """Report which AI backends and platforms are configured. No secrets exposed.

    Returns:
        Nested dict with booleans for video, voice, captions, images, platforms.
    """
    from ai_services.higgsfield import HiggsFieldAdapter

    def has(key: str) -> bool:
        return bool(os.environ.get(key, "").strip())

    def hf_configured() -> bool:
        if has("HF_API_KEY") and has("HF_API_SECRET"):
            return True
        combined = os.environ.get("HF_KEY", "").strip()
        if combined and ":" in combined:
            return True
        if has("HIGGSFIELD_API_KEY_ID") and has("HIGGSFIELD_API_KEY_SECRET"):
            return True
        return False

    higgsfield_backend = "none"
    try:
        higgsfield_backend = HiggsFieldAdapter().backend
    except Exception:
        pass

    return {
        "video": {
            "higgsfield_native": hf_configured(),
            "replicate_fallback": has("REPLICATE_API_TOKEN"),
            "active_backend": higgsfield_backend,
        },
        "voice": {"elevenlabs": has("ELEVENLABS_API_KEY")},
        "captions": {
            "openai": has("OPENAI_API_KEY"),
            "anthropic": has("ANTHROPIC_API_KEY"),
        },
        "images": {
            "replicate": has("REPLICATE_API_TOKEN"),
            "openai": has("OPENAI_API_KEY"),
        },
        "platforms": {
            "facebook": has("FACEBOOK_ACCESS_TOKEN") or has("FACEBOOK_PAGE_ACCESS_TOKEN"),
            "instagram": has("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
            "threads": has("THREADS_ACCESS_TOKEN"),
            "linkedin": has("LINKEDIN_ACCESS_TOKEN"),
            "whatsapp": has("WHATSAPP_ACCESS_TOKEN"),
            "tiktok": has("TIKTOK_ACCESS_TOKEN"),
        },
    }


@mcp.tool()
def socialblast_generate_campaign(
    business_description: str,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a 7-day social media campaign for a business.

    Creates 7 pending posts per platform in the approval queue. Uses OpenAI
    if available, falls back to hand-tuned premium templates otherwise.

    Args:
        business_description: One-sentence description (e.g. "Coffee shop in London")
        platforms: List of target platforms. Defaults to all five broadcast platforms.

    Returns:
        {"group_id": str, "post_ids": list[int], "count": int, "preview": list[str]}
    """
    from dashboard import campaign

    if not platforms:
        platforms = ["facebook", "instagram", "threads", "linkedin", "tiktok"]
    return campaign.generate_campaign(business_description, platforms)


@mcp.tool()
def socialblast_enrich_post(post_id: int, with_video: bool = False) -> dict[str, Any]:
    """Run the AI media pipeline on a pending post.

    Generates an image (and optionally a video) from the post's caption,
    attaching them to the post in the approval queue. The post stays in
    pending status, a human must still approve.

    Args:
        post_id: The pending post's database id.
        with_video: If True, also generate a 6s video (slow, costs more credits).

    Returns:
        {"ok": bool, "post_id": int, "steps": list[{"step", "ok", "url"|"error"}]}
    """
    from dashboard import campaign

    return campaign.enrich_post(post_id, with_video=with_video)


@mcp.tool()
def socialblast_enrich_campaign(group_id: str, with_video: bool = False) -> dict[str, Any]:
    """Enrich every pending post in a campaign group.

    Args:
        group_id: The campaign's group_id (returned by generate_campaign).
        with_video: If True, also generate videos (slow).

    Returns:
        {"group_id": str, "enriched": int, "total": int, "results": list}
    """
    from dashboard import campaign

    return campaign.enrich_campaign(group_id, with_video=with_video)


@mcp.tool()
def socialblast_predict_virality(prompt: str, platform: str = "instagram") -> dict[str, Any]:
    """Score how likely a caption is to go viral on a given platform.

    Requires HiggsField credentials (HF_API_KEY + HF_API_SECRET).
    Returns a stub on other backends.

    Args:
        prompt: The caption text to score.
        platform: instagram, tiktok, facebook, etc.

    Returns:
        {"score": float | None, "engagement_prediction": dict, "reason": str}
    """
    from ai_services.higgsfield import HiggsFieldAdapter

    return HiggsFieldAdapter().predict_virality(prompt, platform=platform)


@mcp.tool()
def socialblast_list_pending() -> dict[str, Any]:
    """List all pending posts in the approval queue with their caption + metadata.

    Useful for Claude to review the queue and suggest which posts to approve,
    edit, or enrich. Read-only, does not change any state.

    Returns:
        {"count": int, "posts": list[{id, message, platform, account_name,
        image_url, video_url, group_id, created_at}]}
    """
    from dashboard import db

    posts = db.list_posts(status="pending")
    return {
        "count": len(posts),
        "posts": [
            {
                "id": p["id"],
                "message": p["message"],
                "platform": p["platform"],
                "account_name": p["account_name"],
                "image_url": p.get("image_url"),
                "video_url": p.get("video_url"),
                "group_id": p.get("group_id"),
                "created_at": p["created_at"],
            }
            for p in posts
        ],
    }


@mcp.tool()
def socialblast_create_draft(
    message: str,
    platform: str,
    image_url: str | None = None,
    video_url: str | None = None,
    scheduled_time: str | None = None,
) -> dict[str, Any]:
    """Create a new pending post in the approval queue.

    This tool never auto-publishes or auto-schedules the post. It
    lands with status='pending' exactly like every other draft, and a
    human must approve it from the dashboard before anything is sent to
    a platform. scheduled_time is stored as metadata only. Arming the
    scheduler happens when a human approves from the dashboard.

    Args:
        message: The post body.
        platform: One of "facebook", "instagram", "whatsapp", "threads", "linkedin", "tiktok".
        image_url: Optional image to attach.
        video_url: Optional video to attach.
        scheduled_time: Optional ISO 8601 timestamp to display alongside the draft.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    if platform not in KNOWN_PLATFORMS:
        return {
            "ok": False,
            "error": f"Unknown platform '{platform}'. Choose one of: {', '.join(sorted(KNOWN_PLATFORMS))}",
        }
    if scheduled_time is not None:
        try:
            datetime.fromisoformat(scheduled_time)
        except ValueError:
            return {"ok": False, "error": f"scheduled_time '{scheduled_time}' is not valid ISO 8601"}

    post_id = db.create_post(message=message, platform=platform, image_url=image_url, video_url=video_url)
    if scheduled_time is not None:
        db.update_post(post_id, scheduled_for=scheduled_time)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_edit_pending(
    post_id: int,
    message: str | None = None,
    image_url: str | None = None,
    video_url: str | None = None,
    scheduled_time: str | None = None,
) -> dict[str, Any]:
    """Edit a pending post's fields. Refuses to touch non-pending posts.

    Args:
        post_id: The post's database id.
        message: New caption text, if changing.
        image_url: New image URL, if changing.
        video_url: New video URL, if changing.
        scheduled_time: New ISO 8601 scheduled time, if changing.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": f"Post {post_id} not found"}
    if post["status"] != "pending":
        return {
            "ok": False,
            "error": (
                f"Post {post_id} is '{post['status']}', not 'pending'. "
                "Approved and published posts are managed from the dashboard."
            ),
        }

    fields: dict[str, Any] = {}
    if message is not None:
        fields["message"] = message
    if image_url is not None:
        fields["image_url"] = image_url
    if video_url is not None:
        fields["video_url"] = video_url
    if scheduled_time is not None:
        try:
            datetime.fromisoformat(scheduled_time)
        except ValueError:
            return {"ok": False, "error": f"scheduled_time '{scheduled_time}' is not valid ISO 8601"}
        fields["scheduled_for"] = scheduled_time

    if not fields:
        return {"ok": False, "error": "No fields to update"}

    db.update_post(post_id, **fields)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_reject_pending(post_id: int) -> dict[str, Any]:
    """Reject a pending post. Refuses to touch non-pending posts.

    Args:
        post_id: The post's database id.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": f"Post {post_id} not found"}
    if post["status"] != "pending":
        return {
            "ok": False,
            "error": (
                f"Post {post_id} is '{post['status']}', not 'pending'. "
                "Approved and published posts are managed from the dashboard."
            ),
        }
    db.reject_post(post_id)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_search_posts(q: str = "", status: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Full-text search over post messages, optionally filtered by status. Read-only.

    Args:
        q: Substring to search for in the message body. Empty matches all.
        status: Optional status filter (pending, published, rejected, failed, scheduled).
        limit: Maximum rows to return.

    Returns:
        {"count": int, "posts": list[dict]}
    """
    from dashboard import db

    posts = db.search_posts(q=q, status=status or "", limit=limit)
    return {"count": len(posts), "posts": posts}


@mcp.tool()
def socialblast_queue_stats() -> dict[str, Any]:
    """Counts of posts per status, plus the upcoming scheduled queue. Read-only.

    Returns:
        {"by_status": dict[str, int], "scheduled": list[dict]}
    """
    from dashboard import db

    return {"by_status": db.stats(), "scheduled": db.list_scheduled()}


# ---------------------------------------------------------------------------
# Facebook read-only tools (4), always registered.
# ---------------------------------------------------------------------------

@mcp.tool()
@mcp_support.envelope
def facebook_get_posts(limit: int = 25, after: str | None = None, include_scheduled: bool = False) -> dict[str, Any]:
    """List recent Facebook Page posts. Read-only.

    Args:
        limit: Max posts to return (client-side truncation of Graph's
            default page. The adapter does not yet request custom page
            sizes from Graph itself).
        after: Reserved for a future paging cursor. Not yet wired to the
            underlying adapter. Accepted for forward compatibility only.
        include_scheduled: When True, also return unpublished scheduled
            posts (the old get_scheduled_posts tool) under "scheduled".

    Returns:
        {"success": True, "data": {"posts": [...], "scheduled": [...] | None}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    posts = manager.get_page_posts()
    if "error" in posts:
        return posts
    result: dict[str, Any] = {"posts": posts.get("data", [])[:limit]}
    if include_scheduled:
        scheduled = manager.get_scheduled_posts()
        if "error" in scheduled:
            return scheduled
        result["scheduled"] = scheduled.get("data", [])
    return result


@mcp.tool()
@mcp_support.envelope
def facebook_get_post_engagement(post_id: str) -> dict[str, Any]:
    """One-call engagement summary: reactions, comments, shares, permalink, impressions.

    Individual insight metrics Meta has deprecated degrade to null with a
    note in "deprecated_metrics" instead of failing the whole call.

    Args:
        post_id: The Facebook post id.

    Returns:
        {"success": True, "data": {"reactions": dict, "comment_count": int,
        "share_count": int, "permalink_url": str | None, "impressions": dict,
        "deprecated_metrics": list[str]}} or {"success": False, "error": {...}}
        if the post itself can't be read.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    return manager.get_post_engagement(post_id)


@mcp.tool()
@mcp_support.envelope
def facebook_get_comments(post_id: str, include_replies: bool = False) -> dict[str, Any]:
    """List comments on a post, optionally with each comment's reply thread. Read-only.

    Args:
        post_id: The Facebook post id.
        include_replies: When True, fetch and attach each top-level
            comment's replies (one extra Graph API call per comment).

    Returns:
        {"success": True, "data": {"comments": list[dict], "count": int}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    comments = manager.get_post_comments(post_id)
    if "error" in comments:
        return comments
    data = comments.get("data", [])
    if include_replies:
        for comment in data:
            replies = manager.get_comment_replies(comment["id"])
            comment["replies"] = replies.get("data", []) if "error" not in replies else []
    return {"comments": data, "count": len(data)}


@mcp.tool()
@mcp_support.envelope
def facebook_get_page_info() -> dict[str, Any]:
    """Extended Page metadata including fan_count. Read-only.

    Returns:
        {"success": True, "data": {..., "fan_count": int}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    info = manager.get_page_info()
    if "error" in info:
        return info
    info["fan_count"] = manager.get_page_fan_count()
    return info


# ---------------------------------------------------------------------------
# Direct-write tools (4), registered only when SOCIALBLAST_ALLOW_DIRECT_WRITES
# is set. Every tool here bypasses the approval queue. See CLAUDE.md section 5.
# ---------------------------------------------------------------------------

if mcp_support.direct_writes_enabled():

    @mcp.tool()
    @mcp_support.envelope
    def facebook_publish_now(
        message: str,
        image_url: str | None = None,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Publishes to Facebook immediately.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true. Prefer
        socialblast_create_draft for anything a human should review first.

        Args:
            message: Post text.
            image_url: Optional image to post as a photo instead of a text post.
            scheduled_publish_time: Optional Unix timestamp for Graph-native
                future publishing. The post WILL go live at that time with
                no further review. This is Graph's own scheduling, not
                the dashboard's approval queue.

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if image_url:
            return manager.post_image_to_facebook(image_url, message)
        if scheduled_publish_time is not None:
            return manager.schedule_post(message, scheduled_publish_time)
        return manager.post_to_facebook(message)

    @mcp.tool()
    @mcp_support.envelope
    def facebook_manage_post(post_id: str, action: str, new_message: str | None = None) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Update or delete a live post.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            post_id: The Facebook post id.
            action: "update" or "delete".
            new_message: Required when action="update".

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if action == "update":
            if not new_message:
                return {
                    "success": False,
                    "error": {
                        "code": "bad_request",
                        "message": "new_message is required for action='update'",
                        "hint": "Pass new_message with the updated text.",
                    },
                }
            return manager.update_post(post_id, new_message)
        if action == "delete":
            return manager.delete_post(post_id)
        return {
            "success": False,
            "error": {
                "code": "bad_request",
                "message": f"Unknown action '{action}'",
                "hint": "action must be 'update' or 'delete'.",
            },
        }

    @mcp.tool()
    @mcp_support.envelope
    def facebook_moderate_comment(
        comment_ids: list[str],
        action: str,
        post_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Moderate one or more comments.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            comment_ids: One or more comment ids to act on.
            action: "reply" (single id only, requires message + post_id),
                "hide", "unhide", or "delete".
            post_id: Required when action="reply".
            message: Required when action="reply".

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if action == "reply":
            if len(comment_ids) != 1 or not post_id or not message:
                return {
                    "success": False,
                    "error": {
                        "code": "bad_request",
                        "message": "action='reply' needs exactly one comment id plus post_id and message",
                        "hint": "Call again with a single comment id.",
                    },
                }
            return manager.reply_to_comment(post_id, comment_ids[0], message)
        if action == "hide":
            return {"results": manager.bulk_hide_comments(comment_ids)}
        if action == "unhide":
            return {"results": manager.bulk_unhide_comments(comment_ids)}
        if action == "delete":
            return {"results": manager.bulk_delete_comments(comment_ids)}
        return {
            "success": False,
            "error": {
                "code": "bad_request",
                "message": f"Unknown action '{action}'",
                "hint": "action must be one of reply, hide, unhide, delete.",
            },
        }

    @mcp.tool()
    @mcp_support.envelope
    def facebook_send_dm(user_id: str, message: str) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Sends a Messenger DM immediately.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            user_id: The Messenger-scoped user id.
            message: DM text.

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        return manager.send_dm_to_user(user_id, message)
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -q`
Expected: All tests pass. If `TestToolCount` or `TestDirectWriteFlag` fail because a developer's shell already has `SOCIALBLAST_ALLOW_DIRECT_WRITES` set, that's a real environment leak worth fixing (the tests already `monkeypatch.delenv` defensively, so this should not happen).

- [ ] **Step 5: Document the flag in `.env.example`**

In `.env.example`, immediately after the `META_APP_ID=` / `META_APP_SECRET=` lines (end of the Facebook + Instagram section, before the WhatsApp section), add:

```env

# Direct-write MCP tools (optional, default OFF) ─────────────────────
# When true, four extra MCP tools (facebook_publish_now, facebook_manage_post,
# facebook_moderate_comment, facebook_send_dm) register alongside the normal
# read-only and approval-queue tools. Each one publishes, edits, or deletes
# directly on Facebook with NO human approval step. Leave this unset/false
# unless you have a specific reason an LLM should be able to write to
# Facebook without a review step in the dashboard.
SOCIALBLAST_ALLOW_DIRECT_WRITES=false
```

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_mcp_socialblast_tools.py .env.example
git commit -m "feat(mcp): rewrite server.py around the 15+4 tool surface"
```

---

### Task 5: README.md — rewrite the MCP section

**Files:**
- Modify: `README.md:77` (hero blurb tool count)
- Modify: `README.md:207-271` (MCP section heading, description, and tool table)

- [ ] **Step 1: Update the hero blurb**

At `README.md:77`, change:

```
Five-minute setup to plug the 37-tool MCP server into Claude Desktop or Claude Code. Read tools work immediately. Write tools land in your local approval queue.
```

to:

```
Five-minute setup to plug the 15-tool MCP server into Claude Desktop or Claude Code. Every write goes through your local approval queue by default, and four extra direct-write tools are available behind an opt-in flag.
```

- [ ] **Step 2: Replace the MCP section**

Replace `README.md:207-271` (from `### MCP server — 37 tools for Claude` through the closing `</details>`) with:

```markdown
### MCP server: 15 tools for Claude, 4 more behind an opt-in flag

`server.py` exposes the approval queue and a consolidated set of Facebook Graph API tools. Drop it into Claude Desktop, Claude Code, Cursor, or any MCP-compatible client. Every tool that talks to the Facebook Graph API returns a uniform `{"success": bool, "data"|"error": {...}}` envelope, so a rate limit or an expired token comes back as an actionable hint, never a raw traceback.

<details>
<summary><b>All 15 always-on tools</b> (click to expand)</summary>
<br/>

**Pipeline and approval queue (11)**
| Tool | What it does |
|---|---|
| `socialblast_status` | Which AI backends and platforms are configured |
| `socialblast_generate_campaign` | Generate a 7-day multi-platform campaign into the queue |
| `socialblast_enrich_post` | Run the AI media pipeline on one pending post |
| `socialblast_enrich_campaign` | Enrich every pending post in a campaign |
| `socialblast_predict_virality` | Score a caption's viral potential |
| `socialblast_list_pending` | List posts awaiting approval |
| `socialblast_create_draft` | Create a new pending post |
| `socialblast_edit_pending` | Edit a pending post's fields |
| `socialblast_reject_pending` | Reject a pending post |
| `socialblast_search_posts` | Full-text search across the queue |
| `socialblast_queue_stats` | Counts by status, plus the scheduled queue |

None of these tools can approve or publish a post. Approval stays human-only, from the dashboard.

**Facebook read-only (4)**
| Tool | What it does |
|---|---|
| `facebook_get_posts` | Recent Page posts, optionally including scheduled |
| `facebook_get_post_engagement` | Reactions, comments, shares, permalink, impressions in one call |
| `facebook_get_comments` | Comments on a post, optionally with reply threads |
| `facebook_get_page_info` | Extended Page metadata including fan count |

</details>

<details>
<summary><b>4 direct-write tools</b>, opt-in only, bypass the approval queue (click to expand)</summary>
<br/>

Registered only when `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` is set in the environment. Every tool below writes to Facebook immediately, with no human review step. This is the one place in the project where "no silent automation" is an opt-in you choose, not the default.

| Tool | What it does |
|---|---|
| `facebook_publish_now` | Publish text or image immediately, or via Graph's native scheduling |
| `facebook_manage_post` | Update or delete a live post |
| `facebook_moderate_comment` | Reply, hide, unhide, or delete one or more comments |
| `facebook_send_dm` | Send a Messenger DM immediately |

</details>

Upgrading from the old 46-tool surface? See the migration table in [CHANGELOG.md](CHANGELOG.md#v07).

</td>
</tr>
</table>
```

Note: the final `</td></tr></table>` closes the same table the section opened with in the original file — check the surrounding markup after `python -m pytest` isn't relevant here (README isn't tested), but do read the rendered section on GitHub or a local markdown previewer to confirm the table/details nesting still closes correctly, since this section sits inside the larger "Features" table structure from `README.md:140` onward.

- [ ] **Step 3: Verify no stale tool-count references remain in README.md**

Run: `grep -n "37" README.md`
Expected: No output referring to the MCP tool count (a "37" appearing in an unrelated context, e.g. a percentage or port number, is fine — check each hit).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): rewrite MCP section for the 15+4 tool surface"
```

---

### Task 6: CHANGELOG.md — add the v0.7 entry

**Files:**
- Modify: `CHANGELOG.md` (insert a new section between `## [Unreleased]` and `## [v0.6]`)

- [ ] **Step 1: Insert the v0.7 section**

In `CHANGELOG.md`, immediately before the `## [v0.6] - 2026-05-15` line, insert:

```markdown
## [v0.7] - 2026-07-18

### Added
- **MCP v2 tool surface.** `server.py` redesigned around the approval queue: 46 tools become 15 core tools plus 4 flag-gated direct-write tools. ([design](docs/specs/2026-07-17-mcp-v2-tool-surface-design.md))
- **`mcp_support.py`.** Uniform `{"success": bool, "data"|"error": ...}` envelope for every Facebook-calling tool, with Graph error-code hints for expired tokens, deprecated metrics, and rate limits.
- **Five new queue tools**: `socialblast_create_draft`, `socialblast_edit_pending`, `socialblast_reject_pending`, `socialblast_search_posts`, `socialblast_queue_stats`. All operate only on `pending` posts, none can approve or publish.
- **Four consolidated read tools**: `facebook_get_posts`, `facebook_get_post_engagement`, `facebook_get_comments`, `facebook_get_page_info`.
- **Four flag-gated direct-write tools**: `facebook_publish_now`, `facebook_manage_post`, `facebook_moderate_comment`, `facebook_send_dm`. Registered only when `SOCIALBLAST_ALLOW_DIRECT_WRITES=true`.
- **`Manager.get_post_engagement()`.** Degrades individual deprecated Graph insight metrics to `null` with a note instead of failing the whole call.

### Fixed
- **`FACEBOOK_ACCESS_TOKEN` bug.** `socialblast_status` and `dashboard/health.py` checked the undocumented `FACEBOOK_PAGE_ACCESS_TOKEN` name and always reported Facebook as unconfigured even when publishing worked. Both now check `FACEBOOK_ACCESS_TOKEN` first, falling back to the legacy name.

### Removed (BREAKING)
- 40 single-purpose Facebook MCP tools, consolidated into the 8 tools above. `filter_negative_comments` and `get_post_top_commenters` have no replacement. The calling LLM computes both trivially from `facebook_get_comments` output.

### Migration table

| Old tool(s) | New tool |
|---|---|
| `post_to_facebook`, `post_image_to_facebook`, `schedule_post` | `facebook_publish_now` (flag-gated) |
| `update_post`, `delete_post` | `facebook_manage_post` (flag-gated) |
| `reply_to_comment`, `hide_comment`, `unhide_comment`, `delete_comment`, `delete_comment_from_post`, `bulk_delete_comments`, `bulk_hide_comments`, `bulk_unhide_comments` | `facebook_moderate_comment` (flag-gated) |
| `send_dm_to_user` | `facebook_send_dm` (flag-gated) |
| `get_page_posts`, `get_scheduled_posts` | `facebook_get_posts` |
| `get_post_comments`, `get_comment_replies`, `get_number_of_comments` | `facebook_get_comments` |
| `get_page_info`, `get_page_fan_count` | `facebook_get_page_info` |
| `get_post_permalink`, `get_post_share_count`, `get_post_reactions_breakdown`, the six `get_post_reactions_*_total` tools, `get_post_insights`, `get_post_impressions*`, `get_post_engaged_users`, `get_post_clicks`, `get_number_of_likes` | `facebook_get_post_engagement` |
| `filter_negative_comments` | *(removed, ask Claude to read the comments and judge sentiment)* |
| `get_post_top_commenters` | *(removed, ask Claude to rank commenters from `facebook_get_comments` output)* |

Set `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` to restore direct-write capability through the four consolidated write tools.

```

(Leave the existing `## [Unreleased]` section exactly as it is — see Assumption 5 above.)

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add v0.7 entry with MCP tool migration table"
```

---

### Task 7: Final verification against the spec's success criteria

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: All tests pass, zero failures, zero errors.

- [ ] **Step 2: Verify each success criterion from spec section 10**

Run each check and confirm the stated result:

```bash
# 1. socialblast_status reports Facebook as configured when FACEBOOK_ACCESS_TOKEN is set
python -c "
import os
os.environ['FACEBOOK_ACCESS_TOKEN'] = 'x'
os.environ.pop('FACEBOOK_PAGE_ACCESS_TOKEN', None)
import server
assert server.socialblast_status()['platforms']['facebook'] is True
print('OK: criterion 1')
"

# 2. With no flag set, the registered tool list contains exactly 15 tools
python -c "
import os
os.environ.pop('SOCIALBLAST_ALLOW_DIRECT_WRITES', None)
import server
names = {t.name for t in server.mcp._tool_manager.list_tools()}
assert len(names) == 15, names
print('OK: criterion 2 —', sorted(names))
"

# 3. A Graph API failure returns a {'success': False} envelope, never raw JSON or a traceback
python -c "
import os
os.environ['FACEBOOK_PAGE_ID'] = '1'
os.environ['FACEBOOK_ACCESS_TOKEN'] = 'bad-token'
import server
result = server.facebook_get_posts()
assert result.get('success') is False, result
assert 'error' in result and 'hint' in result['error'], result
print('OK: criterion 3 —', result)
"
```

Note: criterion 3's script makes a real network call to the Graph API with an invalid token — it should come back as a Graph error (code 190) within a few seconds. If the machine has no network access, skip this script and instead re-run `tests/test_mcp_support.py::TestEnvelope` and `tests/test_mcp_socialblast_tools.py::TestFacebookGetPosts::test_graph_error_envelope`, which cover the same behaviour with a mocked Graph response.

- [ ] **Step 3: Confirm the flagged out-of-scope items are still tracked**

Re-read Assumption 6 above (`docs/try-mcp.md` and `dashboard/app.py:380` still have the old tool count / env var bug). Confirm with the user whether to open a follow-up issue or fold them into this branch before merging.

- [ ] **Step 4: Review the full diff**

```bash
git diff main...feat/mcp-v2-tool-surface --stat
```

Read through every changed file once more end to end before opening a PR — this plan's tasks were executed and reviewed individually, but a final whole-diff read is what CLAUDE.md section 10 asks of every AI-assisted contribution.
