"""Refresh the Facebook Page access token in `.env`.

Graph API Explorer hands out short-lived user tokens that expire in about
an hour. Once the user provides `META_APP_ID` and `META_APP_SECRET` in
their `.env`, this script exchanges any short-lived user token for a
long-lived (60-day) user token, then derives the never-expiring Page
access token from `/me/accounts` and writes it back to `.env`.

CLI:

    python -m scripts.refresh_token <SHORT_LIVED_USER_TOKEN>

After this completes the dashboard works again without further input.
The same exchange logic is exposed as `Manager.refresh_facebook_token`
so the dashboard can offer a "refresh token" form on a 401 response.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class TokenRefreshError(RuntimeError):
    """Raised when the Meta Graph API returns an error during token refresh."""


def exchange_short_lived_for_long_lived(
    short_lived_token: str,
    app_id: str,
    app_secret: str,
) -> str:
    """Exchange a short-lived user token for a long-lived (60-day) one.

    Returns the new user access token. Raises `TokenRefreshError` if the
    exchange call fails or the response does not include a token.
    """
    response = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=15,
    )
    payload = response.json()
    if "error" in payload:
        raise TokenRefreshError(
            f"Token exchange failed: {payload['error'].get('message', payload['error'])}"
        )
    if "access_token" not in payload:
        raise TokenRefreshError(
            f"Token exchange returned no access_token: {payload}"
        )
    return payload["access_token"]


def fetch_page_token(long_lived_user_token: str, page_id: str) -> str:
    """Fetch the never-expiring Page access token for `page_id`.

    Calls `/me/accounts` with the long-lived user token and returns the
    Page token whose entry matches `page_id`. Raises `TokenRefreshError`
    if the API errors or the page is not in the returned list.
    """
    response = requests.get(
        f"{GRAPH_API_BASE}/me/accounts",
        params={"access_token": long_lived_user_token},
        timeout=15,
    )
    payload = response.json()
    if "error" in payload:
        raise TokenRefreshError(
            f"/me/accounts failed: {payload['error'].get('message', payload['error'])}"
        )
    pages = payload.get("data", [])
    for page in pages:
        if str(page.get("id")) == str(page_id):
            token = page.get("access_token")
            if not token:
                raise TokenRefreshError(
                    f"Page {page_id} entry has no access_token field"
                )
            return token
    available = [str(p.get("id")) for p in pages]
    raise TokenRefreshError(
        f"Page {page_id} not found in /me/accounts. Available pages: {available}"
    )


def refresh_page_token(
    short_lived_token: str,
    app_id: str,
    app_secret: str,
    page_id: str,
) -> str:
    """Run the full short-lived to Page token refresh in one call."""
    long_lived = exchange_short_lived_for_long_lived(
        short_lived_token, app_id, app_secret
    )
    return fetch_page_token(long_lived, page_id)


def write_token_to_env(env_path: Path, page_token: str) -> None:
    """Replace `FACEBOOK_ACCESS_TOKEN` in `.env`, or append it if absent.

    Preserves all other lines (comments, other variables) untouched.
    Creates the file if it does not exist.
    """
    line = f"FACEBOOK_ACCESS_TOKEN={page_token}\n"
    if not env_path.exists():
        env_path.write_text(line, encoding="utf-8")
        return

    existing_lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    replaced = False
    new_lines: list[str] = []
    for raw in existing_lines:
        stripped = raw.lstrip()
        if stripped.startswith("FACEBOOK_ACCESS_TOKEN="):
            new_lines.append(line)
            replaced = True
        else:
            new_lines.append(raw)
    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(line)
    env_path.write_text("".join(new_lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a Unix-style exit code."""
    args = sys.argv[1:] if argv is None else argv
    usage = (
        "Usage: python -m scripts.refresh_token <SHORT_LIVED_USER_TOKEN>\n"
        "\n"
        "Reads META_APP_ID, META_APP_SECRET, and FACEBOOK_PAGE_ID from\n"
        ".env, exchanges the short-lived user token for a long-lived\n"
        "Page access token, then writes the result back to .env as\n"
        "FACEBOOK_ACCESS_TOKEN."
    )
    if not args or args[0] in {"-h", "--help"}:
        print(usage)
        return 0
    if len(args) != 1:
        print(usage)
        return 1

    load_dotenv()
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
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print(
            "Add them to .env. See .env.example for the Facebook section.",
            file=sys.stderr,
        )
        return 2

    try:
        page_token = refresh_page_token(args[0], app_id, app_secret, page_id)
    except TokenRefreshError as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 3

    env_path = Path.cwd() / ".env"
    write_token_to_env(env_path, page_token)
    print(f"Wrote refreshed FACEBOOK_ACCESS_TOKEN to {env_path}")
    return 0


def _entry_point() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
