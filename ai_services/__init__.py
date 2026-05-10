"""AI services adapters for social-auto-engine.

These adapters wrap external AI providers used by the compose studio:
text-to-speech (ElevenLabs), video generation (HiggsField with Replicate
fallback), text generation and prompt enhancement (Grok, Bedrock,
Ollama), speech-to-text (Deepgram), and content storage (Notion).

Every adapter follows the same contract:
    * Reads credentials from environment variables.
    * Exposes ``ping()`` returning ``{"connected": bool, ...}`` for the
      Settings page connect/disconnect flow. ``ping`` must never raise.
    * Public methods return dicts. Errors surface as
      ``{"error": "...", ...}`` instead of raising, so the dashboard
      never crashes on a misconfigured key.

Adapters are intentionally thin. They do not own retry policy, caching
or rate limiting — those concerns live one layer up in the manager.
"""

from .bedrock import BedrockAPI
from .deepgram import DeepgramAPI
from .elevenlabs import ElevenLabsAPI
from .grok import GrokAPI
from .higgsfield import HiggsFieldAPI
from .notion import NotionAPI
from .ollama import OllamaAPI

__all__ = [
    "BedrockAPI",
    "DeepgramAPI",
    "ElevenLabsAPI",
    "GrokAPI",
    "HiggsFieldAPI",
    "NotionAPI",
    "OllamaAPI",
]
