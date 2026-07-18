"""Tests for Manager.get_post_engagement, the consolidated engagement
summary behind the facebook_get_post_engagement MCP tool.
"""
from __future__ import annotations

from manager import Manager


def _manager_with_stubbed_api(monkeypatch, **overrides):
    m = Manager()

    defaults = {
        "get_comments": lambda post_id: {"data": [{"id": "1"}, {"id": "2"}]},
        "get_post_permalink": lambda post_id: {"permalink_url": "https://facebook.com/p/1"},
        "get_post_share_count": lambda post_id: 5,
        "get_insights": lambda post_id, metric, period="lifetime": {
            "data": [{"name": metric, "values": [{"value": 10}]}]
        },
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(m.api, name, fn)
    return m


class TestGetPostEngagement:
    def test_happy_path_shape(self, monkeypatch):
        m = _manager_with_stubbed_api(monkeypatch)
        result = m.get_post_engagement("123")
        assert result["comment_count"] == 2
        assert result["share_count"] == 5
        assert result["permalink_url"] == "https://facebook.com/p/1"
        assert set(result["reactions"]) == {"like", "love", "wow", "haha", "sorry", "anger"}
        assert all(v == 10 for v in result["reactions"].values())
        assert set(result["impressions"]) == {"total", "unique", "paid", "organic"}
        assert result["deprecated_metrics"] == []

    def test_deprecated_metric_degrades_to_null(self, monkeypatch):
        def get_insights(post_id, metric, period="lifetime"):
            if metric == "post_impressions_paid":
                return {"error": {"code": 100, "message": "metric is deprecated"}}
            return {"data": [{"name": metric, "values": [{"value": 7}]}]}

        m = _manager_with_stubbed_api(monkeypatch, get_insights=get_insights)
        result = m.get_post_engagement("123")
        assert result["impressions"]["paid"] is None
        assert "post_impressions_paid" in result["deprecated_metrics"]
        assert result["impressions"]["total"] == 7
        assert "error" not in result

    def test_comment_fetch_error_short_circuits(self, monkeypatch):
        m = _manager_with_stubbed_api(
            monkeypatch,
            get_comments=lambda post_id: {"error": {"code": 190, "message": "expired token"}},
        )
        result = m.get_post_engagement("123")
        assert result == {"error": {"code": 190, "message": "expired token"}}

    def test_permalink_fetch_error_short_circuits(self, monkeypatch):
        m = _manager_with_stubbed_api(
            monkeypatch,
            get_post_permalink=lambda post_id: {"error": {"code": 190, "message": "expired token"}},
        )
        result = m.get_post_engagement("123")
        assert "error" in result
        assert result["error"]["code"] == 190
