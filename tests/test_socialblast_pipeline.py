"""Tests for the SocialBlast AI pipeline: HiggsField, ElevenLabs, campaign enrichment."""
from __future__ import annotations

import os
import pytest

from ai_services.elevenlabs import (
    ElevenLabsAdapter,
    ElevenLabsAuthError,
    ElevenLabsError,
)
from ai_services.higgsfield import (
    HiggsFieldAdapter,
    HiggsFieldAuthError,
    HiggsFieldError,
)


# ---------------------------------------------------------------------------
# HiggsField adapter
# ---------------------------------------------------------------------------

class TestHiggsFieldAdapter:
    def test_selects_higgsfield_when_key_pair_set(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "id-123")
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "secret-456")
        monkeypatch.setenv("REPLICATE_API_TOKEN", "also-set")
        a = HiggsFieldAdapter()
        assert a.backend == "higgsfield"
        assert a.is_configured

    def test_higgsfield_needs_both_id_and_secret(self, monkeypatch):
        """Only ID set must NOT activate HiggsField."""
        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "id-only")
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        a = HiggsFieldAdapter()
        assert a.backend == "none"

    def test_higgsfield_needs_secret_too(self, monkeypatch):
        """Only secret set must NOT activate HiggsField."""
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "secret-only")
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        a = HiggsFieldAdapter()
        assert a.backend == "none"

    def test_falls_back_to_replicate(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.setenv("REPLICATE_API_TOKEN", "test-key")
        a = HiggsFieldAdapter()
        assert a.backend == "replicate"
        assert a.is_configured

    def test_none_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        a = HiggsFieldAdapter()
        assert a.backend == "none"
        assert not a.is_configured

    def test_ping_returns_false_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        assert HiggsFieldAdapter().ping() is False

    def test_generate_video_raises_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        with pytest.raises(HiggsFieldAuthError):
            HiggsFieldAdapter().generate_video("test prompt")

    def test_virality_stub_on_non_higgsfield(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.setenv("REPLICATE_API_TOKEN", "test-key")
        result = HiggsFieldAdapter().predict_virality("a caption")
        assert result["score"] is None
        assert "HiggsField" in result["reason"]

    def test_basic_auth_header_format(self, monkeypatch):
        """Auth header must be base64-encoded id:secret in Basic form."""
        import base64
        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "myid")
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "mysecret")
        a = HiggsFieldAdapter()
        header = a._higgsfield_auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header[6:]).decode()
        assert decoded == "myid:mysecret"

    def test_backwards_compat_api_key_property(self, monkeypatch):
        """The api_key property exposes the active credential for legacy tests."""
        monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", "id-x")
        monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "secret-x")
        a = HiggsFieldAdapter()
        assert a.api_key == "id-x"

        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        monkeypatch.setenv("REPLICATE_API_TOKEN", "rep-key")
        b = HiggsFieldAdapter()
        assert b.api_key == "rep-key"

        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        c = HiggsFieldAdapter()
        assert c.api_key == ""

    def test_default_model_ids(self):
        a = HiggsFieldAdapter()
        assert a.higgsfield_model == "veo3_1"
        assert "minimax" in a.replicate_model

    def test_custom_model_via_env(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_MODEL_ID", "kling3_0")
        a = HiggsFieldAdapter()
        assert a.higgsfield_model == "kling3_0"


# ---------------------------------------------------------------------------
# ElevenLabs adapter
# ---------------------------------------------------------------------------

class TestElevenLabsAdapter:
    def test_no_key_means_no_ping(self, monkeypatch):
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        assert ElevenLabsAdapter().ping() is False

    def test_unconfigured_raises_on_list_voices(self, monkeypatch):
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        with pytest.raises(ElevenLabsAuthError):
            ElevenLabsAdapter().list_voices()

    def test_clone_voice_rejects_empty_paths(self):
        with pytest.raises(ElevenLabsError):
            ElevenLabsAdapter().clone_voice("test", [])

    def test_clone_voice_rejects_missing_file(self, tmp_path):
        os.environ["ELEVENLABS_API_KEY"] = "test-key-for-validation-path"
        try:
            with pytest.raises(ElevenLabsError, match="not found"):
                ElevenLabsAdapter().clone_voice(
                    "test",
                    [tmp_path / "does-not-exist.mp3"],
                )
        finally:
            del os.environ["ELEVENLABS_API_KEY"]

    def test_default_voice_id(self):
        assert ElevenLabsAdapter().DEFAULT_VOICE_ID == "21m00Tcm4TlvDq8ikWAM"

    def test_default_model_is_multilingual(self):
        assert ElevenLabsAdapter().DEFAULT_MODEL == "eleven_multilingual_v2"


# ---------------------------------------------------------------------------
# Campaign pipeline
# ---------------------------------------------------------------------------

class TestCampaignPipeline:
    def test_caption_to_image_prompt(self):
        from dashboard import campaign
        prompt = campaign._caption_to_image_prompt('Hello, "world"!')
        assert "Professional social media photo" in prompt
        assert "Hello" in prompt
        assert '"' not in prompt  # quotes stripped

    def test_caption_to_video_prompt(self):
        from dashboard import campaign
        prompt = campaign._caption_to_video_prompt("Multi\nline caption")
        assert "Cinematic" in prompt
        assert "\n" not in prompt  # newlines stripped

    def test_enrich_nonexistent_post(self):
        from dashboard import campaign
        result = campaign.enrich_post(999999)
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_enrich_rejected_post_blocked(self):
        from dashboard import campaign, db
        pid = db.create_post(message="x", account_name="t", platform="facebook")
        db.reject_post(pid)
        result = campaign.enrich_post(pid)
        assert result["ok"] is False
        assert "pending" in result["error"].lower()

    def test_enrich_post_with_empty_message(self):
        from dashboard import campaign, db
        pid = db.create_post(message="   ", account_name="t", platform="facebook")
        result = campaign.enrich_post(pid)
        assert result["ok"] is False
        assert "caption" in result["error"].lower()

    def test_enrich_image_gracefully_handles_missing_replicate(self, monkeypatch):
        from dashboard import campaign, db
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        pid = db.create_post(message="Coffee shop hook", account_name="t", platform="facebook")
        result = campaign.enrich_post(pid, with_video=False)
        # The orchestration succeeds even when image step fails
        assert result["ok"] is True
        # Image step should have failed gracefully
        steps = result["steps"]
        assert any(s["step"] == "image" and not s["ok"] for s in steps)

    def test_generate_campaign_creates_pending_posts(self):
        from dashboard import campaign, db
        result = campaign.generate_campaign("Bakery in Paris", ["facebook"])
        assert result["count"] == 7
        assert len(result["preview"]) == 3
        # All posts should be pending
        posts = db.list_group(result["group_id"])
        assert len(posts) == 7
        assert all(p["status"] == "pending" for p in posts)
        # All posts share the group_id
        assert all(p["group_id"] == result["group_id"] for p in posts)

    def test_premium_captions_in_template_fallback(self, monkeypatch):
        """No OpenAI key means template captions should be the premium hand-tuned ones."""
        from dashboard import campaign
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        captions = campaign._generate_captions_template("Pizza place in Rome")
        assert len(captions) == 7
        # The first premium caption uses the "Three things" hook
        assert "Three things" in captions[0]["text"]
        assert "Pizza place in Rome" in captions[0]["text"]


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    def test_status_returns_sections(self):
        from fastapi.testclient import TestClient
        from dashboard.app import app

        c = TestClient(app)
        r = c.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"video", "voice", "captions", "images", "platforms"}

    def test_status_active_backend_is_known(self):
        from fastapi.testclient import TestClient
        from dashboard.app import app

        c = TestClient(app)
        r = c.get("/api/status")
        assert r.json()["video"]["active_backend"] in {"higgsfield", "replicate", "none"}

    def test_status_does_not_leak_secrets(self, monkeypatch):
        from fastapi.testclient import TestClient
        from dashboard.app import app
        import json

        monkeypatch.setenv("HIGGSFIELD_API_KEY", "sk-supersecret-shouldnotleak-1234567890")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-also-secret")
        c = TestClient(app)
        text = json.dumps(c.get("/api/status").json())
        assert "supersecret" not in text
        assert "sk-also-secret" not in text
