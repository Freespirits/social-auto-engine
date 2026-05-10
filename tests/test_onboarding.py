"""Tests for the onboarding flow.

Covers: settings table, onboarding middleware redirect, route responses,
voice file generation, and the done-page completion flag.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(isolated_dashboard_db, monkeypatch):
    """Return a TestClient with onboarding NOT completed (fresh install)."""
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    from dashboard.app import app
    return TestClient(app, follow_redirects=False)


@pytest.fixture()
def onboarded_client(isolated_dashboard_db, monkeypatch):
    """Return a TestClient with onboarding already completed."""
    from dashboard import db
    db.set_setting("onboarding.completed", "true")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    from dashboard.app import app
    return TestClient(app, follow_redirects=False)


class TestSettingsTable:
    def test_get_setting_default(self, isolated_dashboard_db):
        from dashboard import db
        assert db.get_setting("nonexistent") is None
        assert db.get_setting("nonexistent", "fallback") == "fallback"

    def test_set_and_get_setting(self, isolated_dashboard_db):
        from dashboard import db
        db.set_setting("test.key", "hello")
        assert db.get_setting("test.key") == "hello"

    def test_set_setting_upsert(self, isolated_dashboard_db):
        from dashboard import db
        db.set_setting("test.key", "v1")
        db.set_setting("test.key", "v2")
        assert db.get_setting("test.key") == "v2"

    def test_is_onboarded_default_false(self, isolated_dashboard_db):
        from dashboard import db
        assert db.is_onboarded() is False

    def test_is_onboarded_after_set(self, isolated_dashboard_db):
        from dashboard import db
        db.set_setting("onboarding.completed", "true")
        assert db.is_onboarded() is True


class TestOnboardingMiddleware:
    def test_redirect_to_welcome_when_not_onboarded(self, client):
        resp = client.get("/")
        assert resp.status_code == 303
        assert "/onboarding/welcome" in resp.headers["location"]

    def test_no_redirect_when_onboarded(self, onboarded_client):
        resp = onboarded_client.get("/")
        assert resp.status_code == 200

    def test_static_not_redirected(self, client):
        resp = client.get("/static/styles.css")
        assert resp.status_code == 200

    def test_onboarding_pages_not_redirected(self, client):
        resp = client.get("/onboarding/welcome")
        assert resp.status_code == 200


class TestWelcomePage:
    def test_welcome_renders(self, client):
        resp = client.get("/onboarding/welcome")
        assert resp.status_code == 200
        assert b"five minutes" in resp.content

    def test_welcome_post_redirects_to_connect(self, client):
        resp = client.post("/onboarding/welcome", data={"platform": "facebook"})
        assert resp.status_code == 303
        assert "/onboarding/connect/facebook" in resp.headers["location"]


class TestConnectPage:
    def test_connect_facebook_renders(self, client):
        resp = client.get("/onboarding/connect/facebook")
        assert resp.status_code == 200
        assert b"Graph API Explorer" in resp.content

    def test_connect_instagram_renders(self, client):
        resp = client.get("/onboarding/connect/instagram")
        assert resp.status_code == 200
        assert b"Instagram" in resp.content

    def test_connect_facebook_empty_fields_returns_error(self, client):
        resp = client.post(
            "/onboarding/connect/facebook",
            data={"page_id": "", "access_token": ""},
        )
        assert resp.status_code == 200
        assert b"required" in resp.content.lower()

    def test_connect_unsupported_platform(self, client):
        resp = client.get("/onboarding/connect/tiktok")
        assert resp.status_code == 200
        assert b"not yet supported" in resp.content


class TestVoicePage:
    def test_voice_renders(self, client):
        resp = client.get("/onboarding/voice")
        assert resp.status_code == 200
        assert b"Clone your writing voice" in resp.content

    def test_voice_post_creates_files(self, client, tmp_path, monkeypatch):
        import dashboard.app as app_module
        voice_dir = tmp_path / "voice"
        monkeypatch.setattr(app_module, "VOICE_DIR", voice_dir)
        resp = client.post("/onboarding/voice", data={
            "step_1": "Founder",
            "step_2": "Founders/CEOs",
            "step_3": "AI/automation",
            "step_4": "Most advice is wrong",
            "step_5": "Practical",
            "step_6": "Politics",
            "extra": "",
        })
        assert resp.status_code == 303
        assert (voice_dir / "about-me.md").exists()
        assert (voice_dir / "voice.md").exists()
        about = (voice_dir / "about-me.md").read_text()
        assert "Founder" in about
        assert "AI/automation" in about


class TestFirstPostPage:
    def test_first_post_renders(self, client):
        resp = client.get("/onboarding/first-post")
        assert resp.status_code == 200
        assert b"first post" in resp.content.lower()

    def test_first_post_creates_pending_post(self, client):
        from dashboard import db
        resp = client.post("/onboarding/first-post", data={
            "message": "Hello world from onboarding!",
            "platform": "facebook",
            "image_url": "",
        })
        assert resp.status_code == 303
        posts = db.list_posts(status="pending")
        assert any("Hello world" in p["message"] for p in posts)


class TestDonePage:
    def test_done_sets_completion_flag(self, client):
        from dashboard import db
        assert db.is_onboarded() is False
        resp = client.get("/onboarding/done")
        assert resp.status_code == 200
        assert b"all set" in resp.content.lower()
        assert db.is_onboarded() is True

    def test_skip_sets_completion_flag(self, client):
        from dashboard import db
        resp = client.get("/onboarding/skip")
        assert resp.status_code == 303
        assert db.is_onboarded() is True
