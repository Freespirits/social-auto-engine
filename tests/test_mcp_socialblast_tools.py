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
