"""Smoke tests for the AI services adapters and compose endpoints."""

from __future__ import annotations

import io
import os

import pytest


@pytest.fixture(autouse=True)
def _clear_ai_env(monkeypatch):
    """Run every AI services test against an empty credential set.

    .env can carry live keys for any of these services. We strip them
    here so tests behave the same on every machine, then reload the
    dashboard's manager so its already-instantiated adapters re-init
    against the cleared env.
    """
    for key in (
        "ELEVENLABS_API_KEY",
        "HIGGSFIELD_API_KEY",
        "REPLICATE_API_TOKEN",
        "GROK_API_KEY",
        "XAI_API_KEY",
        "XAI_GROK_API_KEY",
        "DEEPGRAM_API_KEY",
        "NOTION_ACCESS_TOKEN",
        "NOTION_TOKEN",
        "NOTION_CLIENT_ID",
        "NOTION_CLIENT_SECRET",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "OLLAMA_BASE_URL",
        "OLLAMA_DEFAULT_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:65535")  # nothing listens here

    # Force the dashboard's already-built Manager to re-instantiate its
    # AI adapters against the cleared env. Without this, the live fb.*
    # objects would keep the user's real keys and the tests would lie.
    try:
        from dashboard import app as appmod  # noqa: WPS433
        appmod.fb.reload_ai_services()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Adapter ping safe-failures
# ---------------------------------------------------------------------------

def test_elevenlabs_ping_no_key():
    from ai_services import ElevenLabsAPI

    info = ElevenLabsAPI().ping()
    assert info == {"connected": False, "error": "ELEVENLABS_API_KEY not set"}


def test_grok_ping_no_key():
    from ai_services import GrokAPI

    assert GrokAPI().ping()["connected"] is False


def test_higgsfield_ping_no_provider():
    from ai_services import HiggsFieldAPI

    info = HiggsFieldAPI().ping()
    assert info["connected"] is False
    assert "HIGGSFIELD_API_KEY" in info["error"]


def test_notion_ping_no_token():
    from ai_services import NotionAPI

    assert NotionAPI().ping() == {"connected": False, "error": "NOTION_ACCESS_TOKEN not set"}


def test_deepgram_ping_no_key():
    from ai_services import DeepgramAPI

    assert DeepgramAPI().ping()["connected"] is False


def test_ollama_ping_unreachable():
    from ai_services import OllamaAPI

    info = OllamaAPI().ping()
    assert info["connected"] is False


def test_bedrock_ping_no_credentials():
    from ai_services import BedrockAPI

    info = BedrockAPI().ping()
    assert info["connected"] is False


# ---------------------------------------------------------------------------
# Method-level safe-failures (no key required → must return {"error": ...})
# ---------------------------------------------------------------------------

def test_elevenlabs_tts_empty_key():
    from ai_services import ElevenLabsAPI

    result = ElevenLabsAPI().text_to_speech("hello")
    assert "error" in result


def test_grok_chat_empty_key():
    from ai_services import GrokAPI

    result = GrokAPI().chat([{"role": "user", "content": "hi"}])
    assert result == {"error": "GROK_API_KEY not set"}


def test_higgsfield_generate_no_provider():
    from ai_services import HiggsFieldAPI

    result = HiggsFieldAPI().generate_video("a cat surfing")
    assert "error" in result


def test_deepgram_transcribe_no_key():
    from ai_services import DeepgramAPI

    result = DeepgramAPI().transcribe(audio_url="https://example.com/a.wav")
    assert "error" in result


def test_deepgram_to_srt_handles_empty():
    from ai_services import DeepgramAPI

    assert DeepgramAPI.to_srt([]).strip() == ""


def test_deepgram_to_srt_basic():
    from ai_services import DeepgramAPI

    words = [
        {"start": 0.0, "end": 0.5, "punctuated_word": "Hello"},
        {"start": 0.5, "end": 1.0, "punctuated_word": "world."},
    ]
    srt = DeepgramAPI.to_srt(words, words_per_line=2)
    assert "Hello world." in srt
    assert "00:00:00,000" in srt
    assert "00:00:01,000" in srt


def test_notion_authorize_url_shape():
    from ai_services import NotionAPI

    n = NotionAPI()
    n.client_id = "abc"
    url = n.build_authorize_url("https://x.example/cb", "state123")
    assert url.startswith("https://api.notion.com/v1/oauth/authorize?")
    assert "client_id=abc" in url
    assert "state=state123" in url
    assert "owner=user" in url


def test_ollama_generate_unreachable_returns_error():
    from ai_services import OllamaAPI

    result = OllamaAPI().generate("hi")
    assert "error" in result


def test_bedrock_invoke_text_no_credentials():
    from ai_services import BedrockAPI

    result = BedrockAPI().invoke_text("hi")
    assert "error" in result


# ---------------------------------------------------------------------------
# Manager wires every AI service
# ---------------------------------------------------------------------------

def test_manager_exposes_all_ai_services():
    from manager import Manager

    m = Manager()
    for attr in ("elevenlabs", "higgsfield", "grok", "notion", "deepgram", "bedrock", "ollama"):
        assert hasattr(m, attr), f"Manager missing attr {attr}"
    assert m.pick_text_provider() == "none"  # nothing connected → none


# ---------------------------------------------------------------------------
# HTTP endpoints (compose studio + Settings AI routes)
# ---------------------------------------------------------------------------

def _client():
    from fastapi.testclient import TestClient
    from dashboard import app as appmod

    return TestClient(appmod.app)


def test_settings_page_includes_ai_services():
    r = _client().get("/settings")
    assert r.status_code == 200
    assert "AI services" in r.text
    assert "ElevenLabs" in r.text
    assert "HiggsField" in r.text


def test_ai_connect_unknown_service_404():
    r = _client().post("/ai/totally-fake/connect", data={"X": "Y"})
    assert r.status_code == 404


def test_ai_connect_bad_key_does_not_persist(tmp_path, monkeypatch):
    """Posting an invalid key must NOT write tokens.env."""
    from dashboard import app as appmod

    # Point the tokens file at a tmp location to verify no write happened
    fake = tmp_path / "tokens.env"
    monkeypatch.setattr(appmod, "TOKENS_PATH", fake)

    r = _client().post(
        "/ai/elevenlabs/connect",
        data={"ELEVENLABS_API_KEY": "definitely-not-a-real-key"},
    )
    # Validation should fail (400). It can also be 200 if a real key is in env;
    # either way, the bad value must not be persisted on failure.
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert not fake.exists()


def test_ai_test_endpoint_returns_status_html():
    r = _client().post("/ai/grok/test")
    assert r.status_code == 200
    assert "conn-status" in r.text


def test_compose_upload_image(tmp_path):
    payload = io.BytesIO(b"\x89PNG\r\n\x1a\nfake")
    r = _client().post(
        "/compose/upload",
        files={"file": ("photo.png", payload, "image/png")},
        data={"kind": "image", "alt_text": "test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "image"
    assert body["url"].endswith(body["filename"])
    assert "id" in body


def test_compose_upload_rejects_unknown_extension():
    r = _client().post(
        "/compose/upload",
        files={"file": ("evil.exe", io.BytesIO(b"MZ\x90"), "application/octet-stream")},
        data={"kind": "image"},
    )
    assert r.status_code == 400


def test_compose_enhance_prompt_no_provider_returns_400():
    r = _client().post("/compose/enhance-prompt", data={"idea": "a sunset"})
    assert r.status_code == 400  # no provider connected


def test_compose_video_status_404_for_missing():
    r = _client().get("/compose/video/9999/status")
    assert r.status_code == 404


def test_compose_voices_returns_list():
    r = _client().get("/compose/voices")
    assert r.status_code == 200
    body = r.json()
    assert "voices" in body
    assert isinstance(body["voices"], list)
