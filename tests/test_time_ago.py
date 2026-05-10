"""Unit tests for the dashboard's _time_ago Jinja filter.

The filter formats an ISO timestamp as a relative human string:
'just now', '30s ago', '5m ago', '2h ago', '3d ago', or a date prefix
for anything older than a week.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dashboard.app import _time_ago


def _iso_seconds_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def test_none_returns_empty():
    assert _time_ago(None) == ""


def test_empty_string_returns_empty():
    assert _time_ago("") == ""


def test_one_second_ago_is_just_now():
    assert _time_ago(_iso_seconds_ago(1)) == "just now"


def test_one_minute_ago():
    assert _time_ago(_iso_seconds_ago(60)) == "1m ago"


def test_one_hour_ago():
    assert _time_ago(_iso_seconds_ago(3600)) == "1h ago"


def test_one_day_ago():
    assert _time_ago(_iso_seconds_ago(86400)) == "1d ago"


def test_one_week_ago_returns_iso_date_prefix():
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    iso = week_ago.isoformat()
    assert _time_ago(iso) == iso[:10]


def test_z_suffix_treated_as_utc():
    iso = _iso_seconds_ago(300).replace("+00:00", "Z")
    assert _time_ago(iso) == "5m ago"


def test_naive_iso_treated_as_utc():
    iso = _iso_seconds_ago(300).replace("+00:00", "")
    assert _time_ago(iso) == "5m ago"


def test_unparseable_long_string_returns_first_16_with_t_to_space():
    assert _time_ago("2026-05-10T15:42:invalid") == "2026-05-10 15:42"


def test_unparseable_short_string_returns_as_is():
    assert _time_ago("garbage") == "garbage"
