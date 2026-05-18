"""ElevenLabs text-to-speech and voice cloning adapter.

Provides TTS, voice listing, voice cloning, and account info. Used by the
compose toolbar (voiceover button) and the Brand Kit (voice section).
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path


class ElevenLabsError(RuntimeError):
    pass


class ElevenLabsAuthError(ElevenLabsError):
    pass


class ElevenLabsAdapter:
    BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel, the default
    DEFAULT_MODEL = "eleven_multilingual_v2"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    def _headers(self, *, accept: str = "application/json") -> dict[str, str]:
        if not self.api_key:
            raise ElevenLabsAuthError(
                "ELEVENLABS_API_KEY is not set. "
                "Get a key at https://elevenlabs.io/app/settings/api-keys"
            )
        return {"xi-api-key": self.api_key, "Accept": accept}

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/user",
            headers={"xi-api-key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_user(self) -> dict:
        """Return account info including credits remaining."""
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/user",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        sub = data.get("subscription", {})
        return {
            "tier": sub.get("tier"),
            "character_count": sub.get("character_count"),
            "character_limit": sub.get("character_limit"),
            "voice_limit": sub.get("voice_limit"),
            "can_extend_character_limit": sub.get("can_extend_character_limit"),
        }

    def list_voices(self) -> list[dict]:
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/voices",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return [
            {
                "voice_id": v["voice_id"],
                "name": v["name"],
                "category": v.get("category"),
                "preview_url": v.get("preview_url"),
            }
            for v in data.get("voices", [])
        ]

    def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        model_id: str | None = None,
    ) -> bytes:
        import urllib.request

        voice_id = voice_id or self.DEFAULT_VOICE_ID
        model_id = model_id or self.DEFAULT_MODEL
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

    def clone_voice(
        self,
        name: str,
        audio_paths: list[str | Path],
        description: str | None = None,
    ) -> dict:
        """Clone a voice from one or more audio samples.

        Returns {voice_id, name} on success. Samples should be 1-3 minutes
        each, clear speech, no background music. Up to 25 files.
        """
        import urllib.request

        if not audio_paths:
            raise ElevenLabsError("clone_voice requires at least one audio sample.")

        boundary = f"----elevenlabs{uuid.uuid4().hex}"
        body_parts: list[bytes] = []

        def add_field(field_name: str, value: str) -> None:
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'
                f"{value}\r\n".encode()
            )

        def add_file(field_name: str, path: Path) -> None:
            filename = path.name
            content_type = mimetypes.guess_type(filename)[0] or "audio/mpeg"
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n".encode()
            )
            body_parts.append(path.read_bytes())
            body_parts.append(b"\r\n")

        add_field("name", name)
        if description:
            add_field("description", description)
        for p in audio_paths:
            path = Path(p)
            if not path.exists():
                raise ElevenLabsError(f"Audio file not found: {p}")
            add_file("files", path)
        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)

        req = urllib.request.Request(
            f"{self.BASE_URL}/voices/add",
            data=body,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            if "401" in str(exc):
                raise ElevenLabsAuthError(
                    "Your ELEVENLABS_API_KEY is invalid or expired."
                )
            if "402" in str(exc) or "403" in str(exc):
                raise ElevenLabsError(
                    "Voice cloning is not available on your plan. "
                    "Upgrade at https://elevenlabs.io/pricing"
                )
            raise ElevenLabsError(f"Voice cloning failed: {exc}") from exc
        return {"voice_id": data.get("voice_id"), "name": name}

    def delete_voice(self, voice_id: str) -> bool:
        """Delete a cloned voice. Returns True on success."""
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/voices/{voice_id}",
            headers=self._headers(),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception:
            return False
