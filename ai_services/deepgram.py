"""Deepgram speech-to-text and SRT caption adapter."""
from __future__ import annotations

import os


class DeepgramError(RuntimeError):
    pass


class DeepgramAuthError(DeepgramError):
    pass


class DeepgramAdapter:
    BASE_URL = "https://api.deepgram.com/v1"

    def __init__(self) -> None:
        self.api_key = os.environ.get("DEEPGRAM_API_KEY", "")

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/projects",
            headers={"Authorization": f"Token {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def transcribe_url(self, audio_url: str, language: str = "en") -> dict:
        if not self.api_key:
            raise DeepgramAuthError(
                "DEEPGRAM_API_KEY is not set. "
                "Get a key at https://console.deepgram.com"
            )
        import urllib.request
        import json

        payload = json.dumps({"url": audio_url}).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/listen?language={language}&punctuate=true&utterances=true",
            data=payload,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if "401" in str(exc) or "Unauthorized" in str(exc):
                raise DeepgramAuthError(
                    "Your DEEPGRAM_API_KEY is invalid or expired."
                )
            raise DeepgramError(f"Deepgram transcription failed: {exc}") from exc

    def to_srt(self, transcription: dict) -> str:
        utterances = (
            transcription.get("results", {})
            .get("utterances", [])
        )
        if not utterances:
            words = (
                transcription.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("words", [])
            )
            if not words:
                return ""
            utterances = self._words_to_utterances(words)

        lines: list[str] = []
        for i, utt in enumerate(utterances, 1):
            start = self._format_srt_time(utt.get("start", 0))
            end = self._format_srt_time(utt.get("end", 0))
            text = utt.get("transcript", utt.get("text", ""))
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    @staticmethod
    def _words_to_utterances(words: list[dict], max_gap: float = 1.5) -> list[dict]:
        if not words:
            return []
        groups: list[dict] = []
        current = {"start": words[0]["start"], "end": words[0]["end"], "words": [words[0]["word"]]}
        for w in words[1:]:
            if w["start"] - current["end"] > max_gap or len(current["words"]) >= 12:
                current["transcript"] = " ".join(current["words"])
                groups.append(current)
                current = {"start": w["start"], "end": w["end"], "words": [w["word"]]}
            else:
                current["end"] = w["end"]
                current["words"].append(w["word"])
        current["transcript"] = " ".join(current["words"])
        groups.append(current)
        return groups

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
