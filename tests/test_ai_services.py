"""AI service adapter smoke tests.

These never call out to a real API. They confirm:
  - every adapter module imports without errors
  - classes instantiate with no env vars set
  - ping() returns False when no key is configured
  - error classes exist and inherit correctly
  - the AI_SERVICES registry is complete and well-formed
"""
from __future__ import annotations

import pytest

AI_ENV_KEYS = [
    "ELEVENLABS_API_KEY",
    "GROK_API_KEY",
    "DEEPGRAM_API_KEY",
    "REPLICATE_API_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "NOTION_ACCESS_TOKEN",
    "NOTION_DATABASE_ID",
]


@pytest.fixture(autouse=True)
def _clear_ai_env(monkeypatch):
    """Ensure AI service env vars are absent so tests run in a clean state."""
    for key in AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_ai_services_registry_has_all_seven():
    from ai_services import AI_SERVICES

    expected = {"elevenlabs", "grok", "deepgram", "higgsfield", "bedrock", "ollama", "notion"}
    assert set(AI_SERVICES.keys()) == expected


def test_ai_services_registry_fields():
    from ai_services import AI_SERVICES

    for key, info in AI_SERVICES.items():
        assert "label" in info, f"{key} missing label"
        assert "description" in info, f"{key} missing description"
        assert "env_key" in info, f"{key} missing env_key"
        assert "category" in info, f"{key} missing category"
        assert info["category"] in {"audio", "text", "video", "sync"}, (
            f"{key} has unknown category: {info['category']}"
        )
        assert "fields" in info, f"{key} missing fields"
        assert len(info["fields"]) >= 1, f"{key} has empty fields"
        for f in info["fields"]:
            assert "key" in f and "label" in f, f"{key} field missing key/label"


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

def test_elevenlabs_imports():
    from ai_services.elevenlabs import ElevenLabsAdapter, ElevenLabsError, ElevenLabsAuthError

    assert issubclass(ElevenLabsAuthError, ElevenLabsError)
    assert issubclass(ElevenLabsError, RuntimeError)


def test_elevenlabs_instantiate_no_env():
    from ai_services.elevenlabs import ElevenLabsAdapter

    adapter = ElevenLabsAdapter()
    assert adapter.api_key == ""


def test_elevenlabs_ping_no_key():
    from ai_services.elevenlabs import ElevenLabsAdapter

    assert ElevenLabsAdapter().ping() is False


def test_elevenlabs_tts_raises_without_key():
    from ai_services.elevenlabs import ElevenLabsAdapter, ElevenLabsAuthError

    with pytest.raises(ElevenLabsAuthError):
        ElevenLabsAdapter().text_to_speech("hello")


def test_elevenlabs_list_voices_raises_without_key():
    from ai_services.elevenlabs import ElevenLabsAdapter, ElevenLabsAuthError

    with pytest.raises(ElevenLabsAuthError):
        ElevenLabsAdapter().list_voices()


# ---------------------------------------------------------------------------
# Grok
# ---------------------------------------------------------------------------

def test_grok_imports():
    from ai_services.grok import GrokAdapter, GrokError, GrokAuthError

    assert issubclass(GrokAuthError, GrokError)
    assert issubclass(GrokError, RuntimeError)


def test_grok_instantiate_no_env():
    from ai_services.grok import GrokAdapter

    adapter = GrokAdapter()
    assert adapter.api_key == ""
    assert adapter.model == "grok-3-latest"


def test_grok_ping_no_key():
    from ai_services.grok import GrokAdapter

    assert GrokAdapter().ping() is False


def test_grok_enhance_raises_without_key():
    from ai_services.grok import GrokAdapter, GrokAuthError

    with pytest.raises(GrokAuthError):
        GrokAdapter().enhance_prompt("test")


def test_grok_rewrite_raises_without_key():
    from ai_services.grok import GrokAdapter, GrokAuthError

    with pytest.raises(GrokAuthError):
        GrokAdapter().rewrite("test", style="casual")


# ---------------------------------------------------------------------------
# Deepgram
# ---------------------------------------------------------------------------

def test_deepgram_imports():
    from ai_services.deepgram import DeepgramAdapter, DeepgramError, DeepgramAuthError

    assert issubclass(DeepgramAuthError, DeepgramError)
    assert issubclass(DeepgramError, RuntimeError)


def test_deepgram_instantiate_no_env():
    from ai_services.deepgram import DeepgramAdapter

    adapter = DeepgramAdapter()
    assert adapter.api_key == ""


def test_deepgram_ping_no_key():
    from ai_services.deepgram import DeepgramAdapter

    assert DeepgramAdapter().ping() is False


def test_deepgram_transcribe_raises_without_key():
    from ai_services.deepgram import DeepgramAdapter, DeepgramAuthError

    with pytest.raises(DeepgramAuthError):
        DeepgramAdapter().transcribe_url("https://example.com/audio.mp3")


def test_deepgram_srt_empty():
    from ai_services.deepgram import DeepgramAdapter

    assert DeepgramAdapter().to_srt({}) == ""


def test_deepgram_srt_from_utterances():
    from ai_services.deepgram import DeepgramAdapter

    transcription = {
        "results": {
            "utterances": [
                {"start": 0.0, "end": 2.5, "transcript": "Hello world"},
                {"start": 3.0, "end": 5.0, "transcript": "How are you"},
            ]
        }
    }
    srt = DeepgramAdapter().to_srt(transcription)
    assert "1\n00:00:00,000 --> 00:00:02,500\nHello world" in srt
    assert "2\n00:00:03,000 --> 00:00:05,000\nHow are you" in srt


def test_deepgram_format_srt_time():
    from ai_services.deepgram import DeepgramAdapter

    assert DeepgramAdapter._format_srt_time(0) == "00:00:00,000"
    assert DeepgramAdapter._format_srt_time(61.5) == "00:01:01,500"
    assert DeepgramAdapter._format_srt_time(3661.123) == "01:01:01,123"


def test_deepgram_words_to_utterances():
    from ai_services.deepgram import DeepgramAdapter

    words = [
        {"start": 0.0, "end": 0.5, "word": "Hello"},
        {"start": 0.6, "end": 1.0, "word": "world"},
        {"start": 5.0, "end": 5.5, "word": "Goodbye"},
    ]
    groups = DeepgramAdapter._words_to_utterances(words, max_gap=1.5)
    assert len(groups) == 2
    assert groups[0]["transcript"] == "Hello world"
    assert groups[1]["transcript"] == "Goodbye"


# ---------------------------------------------------------------------------
# HiggsField / Replicate
# ---------------------------------------------------------------------------

def test_higgsfield_imports():
    from ai_services.higgsfield import HiggsFieldAdapter, HiggsFieldError, HiggsFieldAuthError

    assert issubclass(HiggsFieldAuthError, HiggsFieldError)
    assert issubclass(HiggsFieldError, RuntimeError)


def test_higgsfield_instantiate_no_env():
    from ai_services.higgsfield import HiggsFieldAdapter

    adapter = HiggsFieldAdapter()
    assert adapter.api_key == ""
    assert adapter.default_model == "minimax/video-01-live"


def test_higgsfield_ping_no_key():
    from ai_services.higgsfield import HiggsFieldAdapter

    assert HiggsFieldAdapter().ping() is False


def test_higgsfield_generate_raises_without_key():
    from ai_services.higgsfield import HiggsFieldAdapter, HiggsFieldAuthError

    with pytest.raises(HiggsFieldAuthError):
        HiggsFieldAdapter().generate_video("a cat dancing")


def test_higgsfield_get_prediction_raises_without_key():
    from ai_services.higgsfield import HiggsFieldAdapter, HiggsFieldAuthError

    with pytest.raises(HiggsFieldAuthError):
        HiggsFieldAdapter().get_prediction("fake-id")


# ---------------------------------------------------------------------------
# Bedrock
# ---------------------------------------------------------------------------

def test_bedrock_imports():
    from ai_services.bedrock import BedrockAdapter, BedrockError, BedrockAuthError

    assert issubclass(BedrockAuthError, BedrockError)
    assert issubclass(BedrockError, RuntimeError)


def test_bedrock_instantiate_no_env():
    from ai_services.bedrock import BedrockAdapter

    adapter = BedrockAdapter()
    assert adapter.access_key == ""
    assert adapter.secret_key == ""


def test_bedrock_ping_no_key():
    from ai_services.bedrock import BedrockAdapter

    assert BedrockAdapter().ping() is False


def test_bedrock_generate_text_raises_without_key():
    from ai_services.bedrock import BedrockAdapter, BedrockAuthError

    with pytest.raises(BedrockAuthError):
        BedrockAdapter().generate_text("test")


def test_bedrock_generate_image_raises_without_key():
    from ai_services.bedrock import BedrockAdapter, BedrockAuthError

    with pytest.raises(BedrockAuthError):
        BedrockAdapter().generate_image("test")


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def test_ollama_imports():
    from ai_services.ollama import OllamaAdapter, OllamaError

    assert issubclass(OllamaError, RuntimeError)


def test_ollama_instantiate_no_env():
    from ai_services.ollama import OllamaAdapter

    adapter = OllamaAdapter()
    assert adapter.base_url == "http://localhost:11434"
    assert adapter.model == "llama3.2"


def test_ollama_ping_no_server():
    from ai_services.ollama import OllamaAdapter
    import os

    adapter = OllamaAdapter()
    adapter.base_url = "http://127.0.0.1:1"
    assert adapter.ping() is False


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

def test_notion_imports():
    from ai_services.notion import NotionAdapter, NotionError, NotionAuthError

    assert issubclass(NotionAuthError, NotionError)
    assert issubclass(NotionError, RuntimeError)


def test_notion_instantiate_no_env():
    from ai_services.notion import NotionAdapter

    adapter = NotionAdapter()
    assert adapter.api_key == ""
    assert adapter.database_id == ""


def test_notion_ping_no_key():
    from ai_services.notion import NotionAdapter

    assert NotionAdapter().ping() is False


def test_notion_sync_raises_without_key():
    from ai_services.notion import NotionAdapter, NotionAuthError

    with pytest.raises(NotionAuthError):
        NotionAdapter().sync_draft("Title", "Body")


def test_notion_list_databases_raises_without_key():
    from ai_services.notion import NotionAdapter, NotionAuthError

    with pytest.raises(NotionAuthError):
        NotionAdapter().list_databases()
