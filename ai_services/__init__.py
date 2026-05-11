"""AI service adapters for the compose studio.

Each adapter follows the same shape:
  - __init__(self) reads credentials from env
  - ping() -> bool validates the connection
  - One or more action methods (generate, transcribe, etc.)
  - ServiceError / ServiceAuthError for error handling

All SDKs are imported lazily so users only install what they use.
"""
from __future__ import annotations

AI_SERVICES: dict[str, dict] = {
    "elevenlabs": {
        "label": "ElevenLabs",
        "description": "Text-to-speech and voice cloning",
        "env_key": "ELEVENLABS_API_KEY",
        "category": "audio",
    },
    "grok": {
        "label": "Grok (xAI)",
        "description": "Prompt enhancement and post rewriting",
        "env_key": "GROK_API_KEY",
        "category": "text",
    },
    "deepgram": {
        "label": "Deepgram",
        "description": "Speech-to-text and SRT captions",
        "env_key": "DEEPGRAM_API_KEY",
        "category": "audio",
    },
    "higgsfield": {
        "label": "HiggsField / Replicate",
        "description": "AI video generation",
        "env_key": "REPLICATE_API_TOKEN",
        "category": "video",
    },
    "bedrock": {
        "label": "Amazon Bedrock",
        "description": "Claude, SDXL, and Titan on AWS",
        "env_key": "AWS_ACCESS_KEY_ID",
        "category": "text",
    },
    "ollama": {
        "label": "Ollama",
        "description": "Free local LLM fallback",
        "env_key": "",
        "category": "text",
    },
    "notion": {
        "label": "Notion",
        "description": "Sync drafts to a Notion database",
        "env_key": "NOTION_ACCESS_TOKEN",
        "category": "sync",
    },
}
