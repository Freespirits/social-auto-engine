"""ElevenLabs adapter: text-to-speech and voice cloning.

ElevenLabs uses simple API-key authentication. Get a key at
https://elevenlabs.io/app/settings/api-keys and paste it into the
Settings page (or set ``ELEVENLABS_API_KEY`` in ``.env``).

Free tier covers ~10k characters per month. Paid tiers unlock voice
cloning, professional voices and longer-form generation. The adapter
makes no assumption about tier. A 401 from any endpoint surfaces as a
disconnected state.
"""

from __future__ import annotations

import os
from typing import Any, Iterable

import requests


ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel, the public default voice
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


class ElevenLabsAPI:
    """Minimal wrapper around the ElevenLabs REST API."""

    def __init__(self) -> None:
        self.api_key = os.getenv("ELEVENLABS_API_KEY", "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, *, accept_json: bool = True) -> dict[str, str]:
        headers = {"xi-api-key": self.api_key}
        if accept_json:
            headers["accept"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        accept_json: bool = True,
        stream: bool = False,
    ) -> requests.Response:
        url = (
            endpoint
            if endpoint.startswith("https://")
            else f"{ELEVENLABS_API_BASE}/{endpoint}"
        )
        headers = self._headers(accept_json=accept_json)
        if files is None and json_body is not None:
            headers["content-type"] = "application/json"
        try:
            return requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                data=data,
                files=files,
                timeout=60,
                stream=stream,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"ElevenLabs request failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Connection check (used by Settings page)
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        """Return a small status dict describing whether the key works."""
        if not self.api_key:
            return {"connected": False, "error": "ELEVENLABS_API_KEY not set"}
        try:
            r = self._request("GET", "user")
        except RuntimeError as exc:
            return {"connected": False, "error": str(exc)}
        if r.status_code == 401:
            return {"connected": False, "error": "Invalid ElevenLabs API key"}
        if not r.ok:
            return {"connected": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        try:
            data = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response from /user"}
        sub = data.get("subscription") or {}
        return {
            "connected": True,
            "tier": sub.get("tier", "free"),
            "character_count": sub.get("character_count", 0),
            "character_limit": sub.get("character_limit", 0),
            "first_name": data.get("first_name", ""),
        }

    # ------------------------------------------------------------------
    # Voices
    # ------------------------------------------------------------------

    def list_voices(self) -> list[dict[str, Any]]:
        """Return every voice the user has access to (default + cloned)."""
        try:
            r = self._request("GET", "voices")
        except RuntimeError:
            return []
        if not r.ok:
            return []
        try:
            payload = r.json()
        except ValueError:
            return []
        voices = []
        for v in payload.get("voices", []):
            voices.append(
                {
                    "voice_id": v.get("voice_id", ""),
                    "name": v.get("name", ""),
                    "category": v.get("category", "premade"),
                    "preview_url": v.get("preview_url", ""),
                    "description": (v.get("description") or "").strip(),
                }
            )
        return voices

    # ------------------------------------------------------------------
    # Text to speech
    # ------------------------------------------------------------------

    def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        *,
        model_id: str | None = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        output_format: str = "mp3_44100_128",
    ) -> dict[str, Any]:
        """Generate audio bytes for ``text`` and return them as a payload.

        Returns ``{"audio": <bytes>, "mime_type": "audio/mpeg", ...}`` on
        success. On failure returns ``{"error": "..."}``.
        """
        if not self.api_key:
            return {"error": "ELEVENLABS_API_KEY not set"}
        text = (text or "").strip()
        if not text:
            return {"error": "Text is empty"}
        voice_id = voice_id or DEFAULT_VOICE_ID
        body = {
            "text": text,
            "model_id": model_id or DEFAULT_MODEL_ID,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
            },
        }
        try:
            r = self._request(
                "POST",
                f"text-to-speech/{voice_id}",
                params={"output_format": output_format},
                json_body=body,
                accept_json=False,
            )
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return {
            "audio": r.content,
            "mime_type": r.headers.get("content-type", "audio/mpeg"),
            "voice_id": voice_id,
            "characters": len(text),
        }

    # ------------------------------------------------------------------
    # Voice cloning (instant clone tier; NOT professional clone)
    # ------------------------------------------------------------------

    def clone_voice(
        self,
        name: str,
        samples: Iterable[tuple[str, bytes, str]],
        description: str = "",
    ) -> dict[str, Any]:
        """Create an instant voice clone from one or more audio samples.

        ``samples`` is an iterable of ``(filename, bytes, mime_type)``
        tuples. ElevenLabs accepts MP3, WAV, M4A and a few others. Total
        sample length should sit between thirty seconds and three
        minutes for best results.
        """
        if not self.api_key:
            return {"error": "ELEVENLABS_API_KEY not set"}
        files = []
        for filename, content, mime_type in samples:
            files.append(("files", (filename, content, mime_type)))
        if not files:
            return {"error": "No samples provided"}
        data = {"name": name, "description": description}
        try:
            r = self._request(
                "POST",
                "voices/add",
                files=files,
                data=data,
                accept_json=True,
            )
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response from /voices/add"}
        return {
            "voice_id": payload.get("voice_id", ""),
            "name": name,
            "requires_verification": payload.get("requires_verification", False),
        }
