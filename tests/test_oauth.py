"""Tests for the OAuth callback flow shared by LinkedIn, TikTok, and YouTube.

These never call out to a real provider. They confirm:
  - /oauth/<platform>/start sets a state cookie and 303-redirects to the provider
  - the callback returns 400 for missing code, missing state cookie, or state mismatch
  - _store_tokens persists key=value pairs to ~/.social-auto-engine/tokens.env
    AND patches the live adapter instances
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard import app as dash_app


client = TestClient(dash_app.app)


# ---------------------------------------------------------------------------
# Start endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "platform,host_substring",
    [
        ("linkedin", "linkedin.com"),
        ("tiktok", "tiktok.com"),
        ("youtube", "google.com"),
    ],
)
def test_oauth_start_redirects_to_provider(platform, host_substring):
    r = client.get(f"/oauth/{platform}/start", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert host_substring in r.headers["location"]


@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_oauth_start_sets_state_cookie(platform):
    r = client.get(f"/oauth/{platform}/start", follow_redirects=False)
    cookies = r.cookies
    assert f"{platform}_oauth_state" in cookies
    state = cookies[f"{platform}_oauth_state"]
    assert state and len(state) >= 16


# ---------------------------------------------------------------------------
# Callback rejection paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_oauth_callback_rejects_missing_code(platform):
    r = client.get(f"/oauth/{platform}/callback")
    assert r.status_code == 400


@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_oauth_callback_rejects_missing_state_cookie(platform):
    """A code without a matching state cookie is a CSRF risk."""
    r = client.get(f"/oauth/{platform}/callback?code=abc&state=xyz")
    assert r.status_code == 400
    assert "state" in r.text.lower() or "oauth" in r.text.lower()


@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_oauth_callback_rejects_state_mismatch(platform):
    fresh_client = TestClient(dash_app.app)
    fresh_client.cookies.set(f"{platform}_oauth_state", "expected_value")
    r = fresh_client.get(f"/oauth/{platform}/callback?code=abc&state=different_value")
    assert r.status_code == 400


@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_oauth_callback_rejects_provider_error(platform):
    fresh_client = TestClient(dash_app.app)
    r = fresh_client.get(f"/oauth/{platform}/callback?error=access_denied")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# _store_tokens helper
# ---------------------------------------------------------------------------

def test_store_tokens_writes_to_disk_and_patches_adapter(tmp_path, monkeypatch):
    """_store_tokens should both persist to disk and update the running adapter."""
    fake_tokens = tmp_path / ".social-auto-engine" / "tokens.env"
    monkeypatch.setattr(dash_app, "TOKENS_PATH", fake_tokens)

    dash_app._store_tokens({"LINKEDIN_ACCESS_TOKEN": "secret-token-123"})

    # Disk
    assert fake_tokens.exists()
    contents = fake_tokens.read_text(encoding="utf-8")
    assert "LINKEDIN_ACCESS_TOKEN=secret-token-123" in contents

    # Live adapter
    assert dash_app.fb.linkedin.access_token == "secret-token-123"

    # Live env
    import os

    assert os.environ.get("LINKEDIN_ACCESS_TOKEN") == "secret-token-123"


def test_store_tokens_merges_with_existing_file(tmp_path, monkeypatch):
    """A second call should preserve unrelated keys from the first."""
    fake_tokens = tmp_path / ".social-auto-engine" / "tokens.env"
    monkeypatch.setattr(dash_app, "TOKENS_PATH", fake_tokens)

    dash_app._store_tokens({"LINKEDIN_ACCESS_TOKEN": "first"})
    dash_app._store_tokens({"TIKTOK_ACCESS_TOKEN": "second"})

    contents = fake_tokens.read_text(encoding="utf-8")
    assert "LINKEDIN_ACCESS_TOKEN=first" in contents
    assert "TIKTOK_ACCESS_TOKEN=second" in contents


def test_store_tokens_skips_empty_values(tmp_path, monkeypatch):
    """An empty value should not overwrite an existing key."""
    fake_tokens = tmp_path / ".social-auto-engine" / "tokens.env"
    monkeypatch.setattr(dash_app, "TOKENS_PATH", fake_tokens)

    dash_app._store_tokens({"LINKEDIN_ACCESS_TOKEN": "real"})
    dash_app._store_tokens({"LINKEDIN_ACCESS_TOKEN": ""})

    contents = fake_tokens.read_text(encoding="utf-8")
    assert "LINKEDIN_ACCESS_TOKEN=real" in contents


# ---------------------------------------------------------------------------
# Disconnect endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", ["linkedin", "tiktok", "youtube"])
def test_disconnect_redirects_to_settings(platform):
    r = client.post(f"/oauth/{platform}/disconnect", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/settings")


def test_disconnect_unknown_platform_404():
    r = client.post("/oauth/myspace/disconnect")
    assert r.status_code == 404


def test_disconnect_clears_token_from_disk_and_adapter(tmp_path, monkeypatch):
    fake_tokens = tmp_path / ".social-auto-engine" / "tokens.env"
    monkeypatch.setattr(dash_app, "TOKENS_PATH", fake_tokens)

    dash_app._store_tokens({"LINKEDIN_ACCESS_TOKEN": "should-be-cleared"})
    assert dash_app.fb.linkedin.access_token == "should-be-cleared"

    fresh_client = TestClient(dash_app.app)
    r = fresh_client.post("/oauth/linkedin/disconnect", follow_redirects=False)
    assert r.status_code == 303

    # Disk should no longer contain the cleared key
    if fake_tokens.exists():
        contents = fake_tokens.read_text(encoding="utf-8")
        assert "LINKEDIN_ACCESS_TOKEN=" not in contents

    # Adapter should be cleared
    assert dash_app.fb.linkedin.access_token is None
