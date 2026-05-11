"""ElevenLabs text-to-speech and voice cloning adapter."""
from __future__ import annotations

import os


class ElevenLabsError(RuntimeError):
    pass


class ElevenLabsAuthError(ElevenLabsError):
    pass


class ElevenLabsAdapter:
    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            f"{self.BASE_URL}/user",
            headers={"xi-api-key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_voices(self) -> list[dict]:
        if not self.api_key:
            raise ElevenLabsAuthError(
                "ELEVENLABS_API_KEY is not set. "
                "Get a key at https://elevenlabs.io/app/settings/api-keys"
            )
        import urllib.request
        import json

        req = urllib.request.Request(
            f"{self.BASE_URL}/voices",
            headers={"xi-api-key": self.api_key},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return [
            {"voice_id": v["voice_id"], "name": v["name"]}
            for v in data.get("voices", [])
        ]

    def text_to_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_multilingual_v2",
    ) -> bytes:
        if not self.api_key:
            raise ElevenLabsAuthError(
                "ELEVENLABS_API_KEY is not set. "
                "Get a key at https://elevenlabs.io/app/settings/api-keys"
            )
        import urllib.request
        import json

        payload = json.dumps({
            "text": text,
            "model_id": model_id,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/text-to-speech/{voice_id}",
            data=payload,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as exc:
            if "401" in str(exc):
                raise ElevenLabsAuthError(
                    "Your ELEVENLABS_API_KEY is invalid or expired."
                )
            raise ElevenLabsError(f"ElevenLabs TTS failed: {exc}") from exc
