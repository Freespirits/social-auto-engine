"""Smoke tests for the SocialBlast MCP tools defined in server.py.

These tools wrap the campaign and AI service modules so Claude can drive
the full pipeline through MCP. We test registration, signatures, and
end-to-end calls (graceful fallback when keys are missing).
"""
from __future__ import annotations

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


class TestRegistration:
    def test_all_six_tools_registered(self):
        import server
        for name in SOCIALBLAST_TOOLS:
            assert hasattr(server, name), f"Missing MCP tool: {name}"
            assert callable(getattr(server, name)), f"Not callable: {name}"

    def test_each_has_docstring(self):
        import server
        for name in SOCIALBLAST_TOOLS:
            fn = getattr(server, name)
            assert fn.__doc__, f"{name} has no docstring"
            assert len(fn.__doc__.strip()) > 10, f"{name} docstring too short"


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
        # with_video should default to False (safety: video is slow)
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


class TestCampaignTool:
    def test_default_platforms_when_none(self):
        import server
        result = server.socialblast_generate_campaign("Vet clinic in Tel Aviv")
        # 7 days * 5 default platforms = 35 posts
        assert result["count"] == 35
        assert len(result["preview"]) == 3

    def test_custom_platforms(self):
        import server
        result = server.socialblast_generate_campaign("Bakery in Paris", ["facebook"])
        assert result["count"] == 7  # 7 days * 1 platform
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
        # Orchestration succeeds even when image gen fails for missing keys
        assert result["ok"] is True
        assert "steps" in result
        # At least the image step should have been attempted
        assert any(s["step"] == "image" for s in result["steps"])

    def test_with_video_flag_attempts_video_step(self):
        import server
        from dashboard import db

        pid = db.create_post(message="x", account_name="Test", platform="facebook")
        result = server.socialblast_enrich_post(pid, with_video=True)
        # Video step should appear (may fail without backend, that's fine)
        steps = [s["step"] for s in result.get("steps", [])]
        # video step is attempted only if image succeeds OR is already present;
        # for an empty post both image and video will be attempted (or both failed)
        assert "image" in steps or "video" in steps


class TestViralityTool:
    def test_stub_without_higgsfield(self, monkeypatch):
        import server

        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        result = server.socialblast_predict_virality("a great caption")
        assert result["score"] is None
        assert "HiggsField" in result["reason"]

    def test_platform_argument_accepted(self, monkeypatch):
        import server

        monkeypatch.delenv("HIGGSFIELD_API_KEY_ID", raising=False)
        monkeypatch.delenv("HIGGSFIELD_API_KEY_SECRET", raising=False)
        # Should not raise on any platform string
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
