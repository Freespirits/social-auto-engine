"""Tests for the Facebook token refresh helper.

All HTTP calls are mocked so the tests never reach Meta's real API.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.refresh_token import (
    TokenRefreshError,
    exchange_short_lived_for_long_lived,
    fetch_page_token,
    main,
    refresh_page_token,
    write_token_to_env,
)


class _MockResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_exchange_returns_long_lived_token():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse(
            {"access_token": "LONG_LIVED_USER_TOKEN", "token_type": "bearer"}
        )
        token = exchange_short_lived_for_long_lived("SHORT", "APP_ID", "APP_SECRET")
        assert token == "LONG_LIVED_USER_TOKEN"


def test_exchange_raises_on_meta_error_payload():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse(
            {"error": {"message": "Invalid OAuth access token", "code": 190}}
        )
        with pytest.raises(TokenRefreshError, match="Invalid OAuth"):
            exchange_short_lived_for_long_lived("BAD", "APP_ID", "APP_SECRET")


def test_exchange_raises_on_missing_access_token_key():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse({"unexpected": "shape"})
        with pytest.raises(TokenRefreshError, match="no access_token"):
            exchange_short_lived_for_long_lived("SHORT", "APP_ID", "APP_SECRET")


def test_fetch_page_token_finds_matching_page():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse(
            {
                "data": [
                    {"id": "111", "access_token": "PAGE_TOKEN_OTHER"},
                    {"id": "999", "access_token": "PAGE_TOKEN_TARGET"},
                ]
            }
        )
        token = fetch_page_token("LONG_LIVED", "999")
        assert token == "PAGE_TOKEN_TARGET"


def test_fetch_page_token_raises_when_page_not_in_list():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse(
            {"data": [{"id": "111", "access_token": "OTHER"}]}
        )
        with pytest.raises(TokenRefreshError, match="not found"):
            fetch_page_token("LONG_LIVED", "999")


def test_fetch_page_token_raises_on_meta_error():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.return_value = _MockResponse(
            {"error": {"message": "Token expired"}}
        )
        with pytest.raises(TokenRefreshError, match="/me/accounts failed"):
            fetch_page_token("EXPIRED", "999")


def test_refresh_page_token_chains_exchange_then_fetch():
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.side_effect = [
            _MockResponse({"access_token": "LONG_LIVED"}),
            _MockResponse({"data": [{"id": "999", "access_token": "PAGE_TOKEN"}]}),
        ]
        token = refresh_page_token("SHORT", "APP_ID", "APP_SECRET", "999")
        assert token == "PAGE_TOKEN"
        assert mock_get.call_count == 2


def test_write_token_creates_env_when_missing(tmp_path: Path):
    env_path = tmp_path / ".env"
    write_token_to_env(env_path, "NEW_TOKEN")
    assert env_path.read_text(encoding="utf-8") == "FACEBOOK_ACCESS_TOKEN=NEW_TOKEN\n"


def test_write_token_replaces_existing_facebook_access_token(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "FACEBOOK_PAGE_ID=12345\n"
        "FACEBOOK_ACCESS_TOKEN=OLD_TOKEN\n"
        "OPENAI_API_KEY=sk-test\n",
        encoding="utf-8",
    )
    write_token_to_env(env_path, "NEW_TOKEN")
    contents = env_path.read_text(encoding="utf-8")
    assert "FACEBOOK_ACCESS_TOKEN=NEW_TOKEN" in contents
    assert "FACEBOOK_ACCESS_TOKEN=OLD_TOKEN" not in contents
    assert "FACEBOOK_PAGE_ID=12345" in contents
    assert "OPENAI_API_KEY=sk-test" in contents


def test_write_token_appends_when_facebook_access_token_missing(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("FACEBOOK_PAGE_ID=12345\n", encoding="utf-8")
    write_token_to_env(env_path, "FRESH_TOKEN")
    contents = env_path.read_text(encoding="utf-8")
    assert contents.startswith("FACEBOOK_PAGE_ID=12345\n")
    assert contents.endswith("FACEBOOK_ACCESS_TOKEN=FRESH_TOKEN\n")


def test_write_token_appends_newline_when_existing_file_has_no_trailing_newline(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("FACEBOOK_PAGE_ID=12345", encoding="utf-8")
    write_token_to_env(env_path, "FRESH_TOKEN")
    contents = env_path.read_text(encoding="utf-8")
    assert contents == "FACEBOOK_PAGE_ID=12345\nFACEBOOK_ACCESS_TOKEN=FRESH_TOKEN\n"


def test_main_with_no_args_prints_help_and_exits_zero(capsys):
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Usage:" in captured.out


def test_main_with_help_flag_prints_help(capsys):
    rc = main(["--help"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Usage:" in captured.out


def test_main_with_too_many_args_prints_help_and_exits_nonzero(capsys):
    rc = main(["TOKEN_A", "TOKEN_B"])
    captured = capsys.readouterr()
    assert rc != 0
    assert "Usage:" in captured.out


def test_main_exits_with_code_2_when_required_env_vars_missing(monkeypatch, capsys):
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    monkeypatch.delenv("FACEBOOK_PAGE_ID", raising=False)
    with patch("scripts.refresh_token.load_dotenv"):
        rc = main(["SHORT_LIVED"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Missing required env vars" in captured.err


def test_main_exits_with_code_3_on_token_refresh_error(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("META_APP_ID", "APP_ID")
    monkeypatch.setenv("META_APP_SECRET", "APP_SECRET")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "999")
    monkeypatch.chdir(tmp_path)
    with (
        patch("scripts.refresh_token.load_dotenv"),
        patch("scripts.refresh_token.requests.get") as mock_get,
    ):
        mock_get.return_value = _MockResponse(
            {"error": {"message": "Invalid OAuth access token"}}
        )
        rc = main(["BAD_TOKEN"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "Refresh failed" in captured.err


def test_main_writes_token_and_exits_zero_on_success(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("META_APP_ID", "APP_ID")
    monkeypatch.setenv("META_APP_SECRET", "APP_SECRET")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "999")
    monkeypatch.chdir(tmp_path)
    with (
        patch("scripts.refresh_token.load_dotenv"),
        patch("scripts.refresh_token.requests.get") as mock_get,
    ):
        mock_get.side_effect = [
            _MockResponse({"access_token": "LONG_LIVED"}),
            _MockResponse({"data": [{"id": "999", "access_token": "PAGE_TOKEN"}]}),
        ]
        rc = main(["SHORT_LIVED"])
    captured = capsys.readouterr()
    assert rc == 0
    env_contents = (tmp_path / ".env").read_text(encoding="utf-8")
    assert env_contents == "FACEBOOK_ACCESS_TOKEN=PAGE_TOKEN\n"
    assert "Wrote refreshed FACEBOOK_ACCESS_TOKEN" in captured.out


def test_manager_refresh_facebook_token_calls_through(monkeypatch, tmp_path):
    monkeypatch.setenv("META_APP_ID", "APP_ID")
    monkeypatch.setenv("META_APP_SECRET", "APP_SECRET")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "999")
    monkeypatch.chdir(tmp_path)

    from manager import Manager

    mgr = Manager()
    with patch("scripts.refresh_token.requests.get") as mock_get:
        mock_get.side_effect = [
            _MockResponse({"access_token": "LONG_LIVED"}),
            _MockResponse({"data": [{"id": "999", "access_token": "PAGE_TOKEN"}]}),
        ]
        token = mgr.refresh_facebook_token("SHORT_LIVED")

    assert token == "PAGE_TOKEN"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == (
        "FACEBOOK_ACCESS_TOKEN=PAGE_TOKEN\n"
    )


def test_manager_refresh_facebook_token_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    monkeypatch.delenv("FACEBOOK_PAGE_ID", raising=False)

    from manager import Manager

    mgr = Manager()
    with pytest.raises(TokenRefreshError, match="Missing required env vars"):
        mgr.refresh_facebook_token("SHORT_LIVED")
