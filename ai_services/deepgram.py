"""Deepgram adapter: speech-to-text with caption export.

Deepgram uses simple API-key auth. Get a key at
https://console.deepgram.com and paste it into the Settings page (or
set ``DEEPGRAM_API_KEY`` in ``.env``).

The dashboard uses two flows:

* ``transcribe(audio_url=...)`` — pre-hosted media. Submits the URL to
  Deepgram and waits for a synchronous response. Best for short audio
  (under five minutes); longer audio should switch to the async API.
* ``transcribe(audio_bytes=..., mime_type=...)`` — raw upload from the
  compose modal. Same synchronous endpoint, payload posted directly.

Captions are produced from the transcript by ``to_srt`` because
Deepgram's native SRT export requires the streaming API. The helper
walks the ``words`` array, batches into ~7-word lines and emits SRT
timestamps.
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEEPGRAM_API_BASE = "https://api.deepgram.com/v1"
DEFAULT_MODEL = "nova-3"


class DeepgramAPI:
    """Minimal Deepgram client."""

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPGRAM_API_KEY", "")

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        if not self.api_key:
            return {"connected": False, "error": "DEEPGRAM_API_KEY not set"}
        try:
            r = requests.get(
                f"{DEEPGRAM_API_BASE}/projects",
                headers={"Authorization": f"Token {self.api_key}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            return {"connected": False, "error": str(exc)}
        if r.status_code == 401:
            return {"connected": False, "error": "Invalid Deepgram key"}
        if not r.ok:
            return {"connected": False, "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response"}
        projects = payload.get("projects") or []
        return {
            "connected": True,
            "projects": len(projects),
            "default_model": DEFAULT_MODEL,
        }

    # ------------------------------------------------------------------
    # Transcribe
    # ------------------------------------------------------------------

    def transcribe(
        self,
        *,
        audio_url: str | None = None,
        audio_bytes: bytes | None = None,
        mime_type: str = "audio/wav",
        model: str | None = None,
        language: str | None = None,
        diarize: bool = False,
        punctuate: bool = True,
    ) -> dict[str, Any]:
        """Transcribe one of ``audio_url`` or ``audio_bytes``.

        Returns ``{"transcript": str, "words": list, "duration": float,
        "language": str}`` on success or ``{"error": str}``.
        """
        if not self.api_key:
            return {"error": "DEEPGRAM_API_KEY not set"}
        if not (audio_url or audio_bytes):
            return {"error": "Provide audio_url or audio_bytes"}
        params: dict[str, Any] = {
            "model": model or DEFAULT_MODEL,
            "smart_format": "true" if punctuate else "false",
            "diarize": "true" if diarize else "false",
        }
        if language:
            params["language"] = language
        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            if audio_url:
                headers["Content-Type"] = "application/json"
                r = requests.post(
                    f"{DEEPGRAM_API_BASE}/listen",
                    headers=headers,
                    params=params,
                    json={"url": audio_url},
                    timeout=300,
                )
            else:
                headers["Content-Type"] = mime_type
                r = requests.post(
                    f"{DEEPGRAM_API_BASE}/listen",
                    headers=headers,
                    params=params,
                    data=audio_bytes,
                    timeout=300,
                )
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response"}
        results = payload.get("results", {})
        channels = results.get("channels", []) or []
        if not channels:
            return {"error": "No transcript channels returned"}
        first = (channels[0].get("alternatives") or [{}])[0]
        return {
            "transcript": first.get("transcript", ""),
            "words": first.get("words", []),
            "duration": (payload.get("metadata") or {}).get("duration", 0.0),
            "language": (channels[0].get("detected_language") or language or ""),
        }

    # ------------------------------------------------------------------
    # SRT export
    # ------------------------------------------------------------------

    @staticmethod
    def to_srt(words: list[dict[str, Any]], *, words_per_line: int = 7) -> str:
        """Convert a Deepgram ``words`` array into SRT subtitle text."""

        def fmt(t: float) -> str:
            ms = int(round(t * 1000))
            hh, ms = divmod(ms, 3_600_000)
            mm, ms = divmod(ms, 60_000)
            ss, ms = divmod(ms, 1000)
            return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

        lines: list[str] = []
        idx = 0
        i = 0
        while i < len(words):
            chunk = words[i : i + words_per_line]
            if not chunk:
                break
            start = float(chunk[0].get("start", 0.0))
            end = float(chunk[-1].get("end", start + 1.0))
            text = " ".join(w.get("punctuated_word") or w.get("word", "") for w in chunk)
            idx += 1
            lines.append(f"{idx}\n{fmt(start)} --> {fmt(end)}\n{text}\n")
            i += words_per_line
        return "\n".join(lines).strip() + "\n"
