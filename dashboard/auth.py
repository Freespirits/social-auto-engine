"""Simple cookie-based authentication for the dashboard.

If the env var DASHBOARD_PASSWORD is set, all routes (except /login, /static,
/favicon.ico) require a valid session cookie.  When it is *not* set the auth
layer is transparent and every request passes through.

Cookie signing uses hmac+hashlib (zero extra dependencies).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COOKIE_NAME = "sae_session"
SESSION_MAX_AGE = 60 * 60 * 24  # 24 hours

# Paths that never require auth
PUBLIC_PATHS: set[str] = {"/login", "/logout", "/favicon.ico"}
PUBLIC_PREFIXES: tuple[str, ...] = ("/static/",)


def _get_secret_key() -> str:
    """Return a stable secret key for cookie signing.

    Uses DASHBOARD_SECRET_KEY if set, otherwise generates a random one at
    import time.  (A random key means sessions don't survive server restarts,
    which is fine for a localhost tool.)
    """
    key = os.getenv("DASHBOARD_SECRET_KEY", "")
    if key:
        return key
    return secrets.token_hex(32)


SECRET_KEY = _get_secret_key()


# ---------------------------------------------------------------------------
# Cookie helpers (hmac + hashlib, zero dependencies)
# ---------------------------------------------------------------------------

def _sign(payload: str) -> str:
    """Return ``payload.signature`` where signature = HMAC-SHA256."""
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify(token: str) -> str | None:
    """Verify a signed token.  Returns the payload on success, None on failure."""
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return payload


def create_session_token() -> str:
    """Create a signed session token embedding the current timestamp."""
    ts = str(int(time.time()))
    return _sign(ts)


def validate_session_token(token: str) -> bool:
    """Check that *token* is validly signed and not expired."""
    payload = _verify(token)
    if payload is None:
        return False
    try:
        ts = int(payload)
    except ValueError:
        return False
    return (time.time() - ts) < SESSION_MAX_AGE


# ---------------------------------------------------------------------------
# Auth check (password)
# ---------------------------------------------------------------------------

def check_password(password: str) -> bool:
    """Compare *password* against the env var DASHBOARD_PASSWORD."""
    expected = os.getenv("DASHBOARD_PASSWORD", "")
    if not expected:
        return False
    return hmac.compare_digest(password.encode(), expected.encode())


def auth_required() -> bool:
    """Return True when the dashboard should enforce authentication."""
    return bool(os.getenv("DASHBOARD_PASSWORD", ""))


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def _is_public(path: str) -> bool:
    """Return True if *path* should skip auth."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users to /login.

    Completely transparent when DASHBOARD_PASSWORD is not set.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not auth_required():
            return await call_next(request)

        if _is_public(request.url.path):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if token and validate_session_token(token):
            return await call_next(request)

        # Unauthenticated -- redirect to login
        return RedirectResponse(url="/login", status_code=303)
