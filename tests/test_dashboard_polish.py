"""Tests for the dashboard polish PR: auth error UX, empty state, i18n, image gen.

Covers issues #28, #7, multi-language i18n, and AI ad creative.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(isolated_dashboard_db, monkeypatch):
    """Onboarded client with no password."""
    from dashboard import db
    db.set_setting("onboarding.completed", "true")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    from dashboard import app as dash_app
    return TestClient(dash_app.app)


# ── Issue #28: Auth error UX ───────────────────────────────────────────


class TestAuthErrorUX:
    def test_generate_missing_key_returns_401(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.setenv("AI_PROVIDER", "claude")
        resp = client.post("/generate", data={"topic": "test topic"})
        assert resp.status_code == 401
        assert "ANTHROPIC_API_KEY" in resp.text

    def test_generate_missing_openai_key(self, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("AI_PROVIDER", "openai")
        resp = client.post("/generate", data={"topic": "test topic"})
        assert resp.status_code == 401
        assert "OPENAI_API_KEY" in resp.text

    def test_generate_missing_gemini_key(self, client, monkeypatch):
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        resp = client.post("/generate", data={"topic": "test topic"})
        assert resp.status_code == 401
        assert "GOOGLE_AI_API_KEY" in resp.text

    def test_auth_error_is_subclass(self):
        from content.generator import AuthError, GeneratorError
        assert issubclass(AuthError, GeneratorError)

    def test_generate_empty_topic_still_400(self, client):
        resp = client.post("/generate", data={"topic": ""})
        assert resp.status_code == 400


# ── Issue #7: Empty state ──────────────────────────────────────────────


class TestEmptyState:
    def test_first_run_shows_empty_state_card(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "first-run-card" in resp.text
        assert "Ready to publish" in resp.text

    def test_first_run_shows_three_steps(self, client):
        resp = client.get("/")
        assert "Connect your accounts" in resp.text
        assert "Clone your writing voice" in resp.text
        assert "Compose your first post" in resp.text

    def test_no_first_run_after_post_exists(self, client):
        from dashboard import db
        db.create_post("Hello world", "facebook", "Test Page")
        resp = client.get("/")
        assert resp.status_code == 200
        assert "first-run-card" not in resp.text


# ── i18n ───────────────────────────────────────────────────────────────


class TestI18n:
    def test_translate_returns_english_by_default(self):
        from dashboard.i18n import translate
        assert translate("inbox.title") == "Inbox"

    def test_translate_returns_hebrew(self):
        from dashboard.i18n import translate
        result = translate("inbox.title", "he")
        assert result == "דואר נכנס"

    def test_translate_falls_back_to_english(self):
        from dashboard.i18n import translate
        result = translate("app.title", "he")
        assert result == "Social Auto Engine"

    def test_translate_returns_key_for_missing(self):
        from dashboard.i18n import translate
        assert translate("nonexistent.key") == "nonexistent.key"

    def test_locale_dir_ltr(self):
        from dashboard.i18n import locale_dir
        assert locale_dir("en") == "ltr"

    def test_locale_dir_rtl(self):
        from dashboard.i18n import locale_dir
        assert locale_dir("he") == "rtl"

    def test_set_language_route(self, client):
        resp = client.post(
            "/settings/language",
            data={"locale": "he"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from dashboard import db
        assert db.get_setting("dashboard.locale") == "he"

    def test_set_language_invalid(self, client):
        resp = client.post(
            "/settings/language",
            data={"locale": "xx"},
        )
        assert resp.status_code == 400

    def test_html_dir_attribute(self, client):
        from dashboard import db
        db.set_setting("dashboard.locale", "he")
        resp = client.get("/")
        assert 'dir="rtl"' in resp.text

    def test_settings_shows_language_picker(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "English" in resp.text
        assert "עברית" in resp.text


# ── Image generation ───────────────────────────────────────────────────


class TestImageGen:
    def test_generate_image_missing_token(self, client, monkeypatch):
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        resp = client.post(
            "/compose/generate-image",
            data={"prompt": "a cat in space"},
        )
        assert resp.status_code == 401
        assert "REPLICATE_API_TOKEN" in resp.text

    def test_generate_image_empty_prompt(self, client):
        resp = client.post(
            "/compose/generate-image",
            data={"prompt": ""},
        )
        assert resp.status_code == 400

    def test_image_gen_error_classes(self):
        from content.image_gen import ImageAuthError, ImageGenError
        assert issubclass(ImageAuthError, ImageGenError)

    def test_compose_has_image_gen_button(self, client):
        resp = client.get("/")
        assert "AI image" in resp.text
        assert "bImgGenRow" in resp.text

    def test_generate_image_openai_missing(self, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("IMAGE_PROVIDER", "openai")
        resp = client.post(
            "/compose/generate-image",
            data={"prompt": "sunset over mountains"},
        )
        assert resp.status_code == 401
        assert "OPENAI_API_KEY" in resp.text
