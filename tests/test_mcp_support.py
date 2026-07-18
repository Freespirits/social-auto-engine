"""Tests for mcp_support.py, the MCP error envelope and flag helpers."""
from __future__ import annotations

import mcp_support


class TestDirectWritesEnabled:
    def test_false_when_unset(self, monkeypatch):
        monkeypatch.delenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", raising=False)
        assert mcp_support.direct_writes_enabled() is False

    def test_true_values(self, monkeypatch):
        for value in ("true", "True", "1", "yes"):
            monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", value)
            assert mcp_support.direct_writes_enabled() is True

    def test_false_for_other_values(self, monkeypatch):
        monkeypatch.setenv("SOCIALBLAST_ALLOW_DIRECT_WRITES", "false")
        assert mcp_support.direct_writes_enabled() is False


class TestRequireEnv:
    def test_none_when_all_set(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "value")
        assert mcp_support.require_env("SOME_KEY") is None

    def test_envelope_when_missing(self, monkeypatch):
        monkeypatch.delenv("SOME_MISSING_KEY", raising=False)
        result = mcp_support.require_env("SOME_MISSING_KEY")
        assert result["success"] is False
        assert "SOME_MISSING_KEY" in result["error"]["message"]
        assert result["error"]["code"] == "missing_config"


class TestEnvelope:
    def test_wraps_plain_return_as_success(self):
        @mcp_support.envelope
        def fn():
            return {"id": "123"}

        assert fn() == {"success": True, "data": {"id": "123"}}

    def test_rewraps_graph_error(self):
        @mcp_support.envelope
        def fn():
            return {"error": {"code": 190, "message": "Invalid OAuth access token"}}

        result = fn()
        assert result["success"] is False
        assert result["error"]["code"] == "190"
        assert "access token" in result["error"]["hint"].lower()

    def test_unmapped_error_code_gets_default_hint(self):
        @mcp_support.envelope
        def fn():
            return {"error": {"code": 999, "message": "Something weird"}}

        result = fn()
        assert result["success"] is False
        assert result["error"]["hint"] == mcp_support.DEFAULT_HINT

    def test_catches_exceptions(self):
        @mcp_support.envelope
        def fn():
            raise ValueError("boom")

        result = fn()
        assert result["success"] is False
        assert result["error"]["code"] == "internal_error"
        assert "boom" in result["error"]["message"]

    def test_passes_through_existing_envelope(self):
        @mcp_support.envelope
        def fn():
            return {"success": False, "error": {"code": "missing_config", "message": "x", "hint": "y"}}

        assert fn()["error"]["code"] == "missing_config"

    def test_rate_limit_codes_get_wait_hint(self):
        for code in (4, 17, 32):

            @mcp_support.envelope
            def fn(code=code):
                return {"error": {"code": code, "message": "rate limited"}}

            result = fn()
            assert "wait" in result["error"]["hint"].lower()
