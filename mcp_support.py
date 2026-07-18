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
