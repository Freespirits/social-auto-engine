"""Tests for the CLI health check (dashboard/health.py)."""
from __future__ import annotations

import subprocess
import sys

import pytest


# ---------------------------------------------------------------------------
# Helpers — keep tests isolated from the dev's tokens.env
# ---------------------------------------------------------------------------

ALL_KEYS = [
    "HIGGSFIELD_API_KEY_ID",
    "HIGGSFIELD_API_KEY_SECRET",
    "REPLICATE_API_TOKEN",
    "ELEVENLABS_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "FACEBOOK_PAGE_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "THREADS_ACCESS_TOKEN",
    "LINKEDIN_ACCESS_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "TIKTOK_ACCESS_TOKEN",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every backend key the CLI looks at."""
    for k in ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield


# ---------------------------------------------------------------------------
# collect()
# ---------------------------------------------------------------------------

class TestCollect:
    def test_shape_matches_status_endpoint(self, clean_env, monkeypatch):
        # Block .env loading inside collect() so the test stays isolated.
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        data = health.collect()
        assert set(data.keys()) == {"video", "voice", "captions", "images", "platforms"}
        assert data["video"]["active_backend"] == "none"
        assert data["video"]["higgsfield_native"] is False
        assert data["video"]["replicate_fallback"] is False
        assert data["voice"]["elevenlabs"] is False

    def test_detects_higgsfield_pair(self, clean_env, monkeypatch):
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "id")
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "secret")
        data = health.collect()
        assert data["video"]["higgsfield_native"] is True
        assert data["video"]["active_backend"] == "higgsfield"

    def test_detects_replicate_only(self, clean_env, monkeypatch):
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        monkeypatch.setenv("REPLICATE_API_TOKEN", "rep")
        data = health.collect()
        assert data["video"]["higgsfield_native"] is False
        assert data["video"]["replicate_fallback"] is True
        assert data["video"]["active_backend"] == "replicate"

    def test_detects_voice(self, clean_env, monkeypatch):
        from dashboard import health

        monkeypatch.setattr(health, "_load_env", lambda: None)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "el")
        assert health.collect()["voice"]["elevenlabs"] is True


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------

class TestRender:
    def _data(self) -> dict:
        return {
            "video": {"higgsfield_native": True, "replicate_fallback": False, "active_backend": "higgsfield"},
            "voice": {"elevenlabs": True},
            "captions": {"openai": False, "anthropic": False},
            "images": {"replicate": False, "openai": False},
            "platforms": {
                "facebook": True, "instagram": False, "threads": False,
                "linkedin": False, "whatsapp": False, "tiktok": False,
            },
        }

    def test_no_color_output(self):
        from dashboard import health

        out = health.render(self._data(), color=False)
        assert "SocialBlast AI" in out
        assert "HiggsField" in out
        assert "ElevenLabs" in out
        assert "ready" in out
        assert "not set" in out
        assert "Active video backend:" in out
        # No ANSI escapes
        assert "\033" not in out

    def test_color_output_has_ansi(self):
        from dashboard import health

        out = health.render(self._data(), color=True)
        # Some ANSI escape should be present when color is on
        assert "\033" in out

    def test_summary_count(self):
        from dashboard import health

        out = health.render(self._data(), color=False)
        # 3 services ready: HiggsField, ElevenLabs, Facebook (the OR-counter
        # treats video as one slot via higgsfield OR replicate)
        # Summary line shows N/total
        import re
        m = re.search(r"(\d+)/(\d+) services configured", out)
        assert m is not None
        ready, total = int(m.group(1)), int(m.group(2))
        assert 0 < ready < total

    def test_render_no_secrets_in_output(self):
        from dashboard import health

        out = health.render(self._data(), color=False)
        # The render function never sees raw keys, but double-check
        for marker in ("sk-", "sk_", "Bearer", "Basic "):
            assert marker not in out

    def test_no_em_dash_in_title(self):
        """CLAUDE.md: no em dashes in prose."""
        from dashboard import health

        out = health.render(self._data(), color=False)
        # The title line must use ASCII punctuation only
        title_line = out.splitlines()[1] if out.startswith("\n") else out.splitlines()[0]
        assert "—" not in title_line, "Em dash leaked into title"
        assert "–" not in title_line, "En dash leaked into title"


# ---------------------------------------------------------------------------
# End-to-end CLI invocation
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_python_module_health_runs(self):
        """`python -m dashboard.health` exits 0 and prints expected sections."""
        result = subprocess.run(
            [sys.executable, "-m", "dashboard.health"],
            capture_output=True,
            text=True,
            env={"NO_COLOR": "1", "PATH": ""},
            timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        for needle in ("Video", "Voice", "Captions", "Images", "Platform tokens",
                       "services configured"):
            assert needle in result.stdout, f"Missing in output: {needle}"
