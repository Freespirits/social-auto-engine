"""AI service adapters for the compose studio.

Each adapter follows the same shape:
  - __init__(self) reads credentials from env
  - ping() -> bool validates the connection
  - One or more action methods (generate, transcribe, etc.)
  - ServiceError / ServiceAuthError for error handling

All SDKs are imported lazily so users only install what they use.
"""
from __future__ import annotations

from typing import Any


# ------------------------------------------------------------------
# Text AI cascade: try Grok -> Bedrock -> Ollama, use first available
# ------------------------------------------------------------------

_TEXT_PROVIDERS = ("grok", "bedrock", "ollama")


def _get_text_adapter() -> tuple[str, Any]:
    """Return (provider_name, adapter_instance) for the first reachable text AI.

    Tries Grok, then Amazon Bedrock, then Ollama.
    Raises RuntimeError if none are available.
    """
    from ai_services.grok import GrokAdapter
    grok = GrokAdapter()
    if grok.api_key and grok.ping():
        return ("grok", grok)

    from ai_services.bedrock import BedrockAdapter
    bedrock = BedrockAdapter()
    if bedrock.access_key and bedrock.secret_key and bedrock.ping():
        return ("bedrock", bedrock)

    from ai_services.ollama import OllamaAdapter
    ollama = OllamaAdapter()
    if ollama.ping():
        return ("ollama", ollama)

    raise RuntimeError(
        "No text AI provider is available. "
        "Configure at least one of: Grok (xAI), Amazon Bedrock, or Ollama "
        "in Settings > AI services."
    )


def cascade_enhance(text: str) -> tuple[str, str]:
    """Enhance text using the first available AI provider.

    Returns (provider_name, enhanced_text).
    """
    name, adapter = _get_text_adapter()
    return name, adapter.enhance_prompt(text)


def cascade_rewrite(text: str, style: str = "professional") -> tuple[str, str]:
    """Rewrite text using the first available AI provider.

    Returns (provider_name, rewritten_text).
    """
    name, adapter = _get_text_adapter()
    return name, adapter.rewrite(text, style=style)


def cascade_generate(prompt: str) -> tuple[str, str]:
    """Generate free-form text using the first available AI provider.

    Returns (provider_name, generated_text).
    """
    name, adapter = _get_text_adapter()
    if hasattr(adapter, "generate_text"):
        return name, adapter.generate_text(prompt)
    if hasattr(adapter, "generate"):
        return name, adapter.generate(prompt)
    return name, adapter.enhance_prompt(prompt)


AI_SERVICES: dict[str, dict] = {
    "elevenlabs": {
        "label": "ElevenLabs",
        "description": "Text-to-speech and voice cloning",
        "env_key": "ELEVENLABS_API_KEY",
        "category": "audio",
        "fields": [
            {"key": "ELEVENLABS_API_KEY", "label": "API key", "secret": True},
        ],
    },
    "grok": {
        "label": "Grok (xAI)",
        "description": "Prompt enhancement and post rewriting",
        "env_key": "GROK_API_KEY",
        "category": "text",
        "fields": [
            {"key": "GROK_API_KEY", "label": "API key", "secret": True},
        ],
    },
    "deepgram": {
        "label": "Deepgram",
        "description": "Speech-to-text and SRT captions",
        "env_key": "DEEPGRAM_API_KEY",
        "category": "audio",
        "fields": [
            {"key": "DEEPGRAM_API_KEY", "label": "API key", "secret": True},
        ],
    },
    "higgsfield": {
        "label": "HiggsField / Replicate",
        "description": "AI video generation",
        "env_key": "REPLICATE_API_TOKEN",
        "category": "video",
        "fields": [
            {"key": "REPLICATE_API_TOKEN", "label": "API token", "secret": True},
        ],
    },
    "bedrock": {
        "label": "Amazon Bedrock",
        "description": "Claude, SDXL, and Titan on AWS",
        "env_key": "AWS_ACCESS_KEY_ID",
        "category": "text",
        "fields": [
            {"key": "AWS_ACCESS_KEY_ID", "label": "Access key ID", "secret": False},
            {"key": "AWS_SECRET_ACCESS_KEY", "label": "Secret access key", "secret": True},
            {"key": "AWS_REGION", "label": "Region", "secret": False, "placeholder": "us-east-1"},
        ],
    },
    "ollama": {
        "label": "Ollama",
        "description": "Free local LLM fallback",
        "env_key": "",
        "category": "text",
        "fields": [
            {"key": "OLLAMA_BASE_URL", "label": "Base URL", "secret": False, "placeholder": "http://localhost:11434"},
            {"key": "OLLAMA_MODEL", "label": "Model", "secret": False, "placeholder": "llama3.2"},
        ],
    },
    "notion": {
        "label": "Notion",
        "description": "Sync drafts to a Notion database",
        "env_key": "NOTION_ACCESS_TOKEN",
        "category": "sync",
        "fields": [
            {"key": "NOTION_ACCESS_TOKEN", "label": "Access token", "secret": True},
            {"key": "NOTION_DATABASE_ID", "label": "Database ID", "secret": False},
        ],
    },
}
