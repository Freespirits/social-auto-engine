"""xAI Grok adapter.

Grok exposes an OpenAI-compatible chat completions API at
``https://api.x.ai/v1``. Get an API key from https://console.x.ai and
paste it into the Settings page (or set ``GROK_API_KEY`` /
``XAI_API_KEY`` in ``.env``).

Default model is ``grok-4-latest`` for high-quality prompt enhancement
work. Caller can override per call. The adapter exposes a generic
chat method plus three convenience wrappers used by the compose studio:
``enhance_video_prompt``, ``rewrite_post`` and ``generate_alt_text``.
"""

from __future__ import annotations

import os
from typing import Any

import requests


GROK_API_BASE = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4-latest"

VIDEO_PROMPT_SYSTEM = """You expand short user ideas into rich, cinematic
video prompts for AI video generation models such as HiggsField, Veo,
Kling and Runway Gen-3.

Rules:
* Stay faithful to the user's intent. Do not add unrelated subjects.
* Specify shot type, camera motion, lighting, mood, palette, lens.
* Specify motion of the subject and any environmental motion.
* Aim for 60 to 110 words. No bullet points. One paragraph of prose.
* Never reference brands, real people, copyrighted characters or text
  overlays unless the user explicitly asks for them.
* End with a single tag line of comma-separated style keywords.
"""

POST_REWRITE_SYSTEM = """You rewrite social media posts in the user's
voice for the requested platform. Match the platform's length norms:
LinkedIn 1100-1500 chars, X under 280, Threads under 500, Instagram
under 2200, TikTok caption under 150. British English. No em dashes.
No semicolons. Keep the user's punchlines and any specific facts.
Return only the rewritten post text. No commentary."""

ALT_TEXT_SYSTEM = """You write a single short, descriptive alt-text
sentence for the supplied image description. 100-140 characters. No
trailing period. Describe what is shown, not what it means."""


class GrokAPI:
    """Minimal Grok / xAI chat client."""

    def __init__(self) -> None:
        # Accept all three common names. XAI_GROK_API_KEY is what the
        # legacy .env.example used; the other two are what xAI's docs
        # currently recommend.
        self.api_key = (
            os.getenv("GROK_API_KEY")
            or os.getenv("XAI_API_KEY")
            or os.getenv("XAI_GROK_API_KEY")
            or ""
        )
        self.default_model = os.getenv("GROK_DEFAULT_MODEL", DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _request(self, endpoint: str, body: dict[str, Any]) -> requests.Response:
        url = f"{GROK_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            return requests.post(url, headers=headers, json=body, timeout=120)
        except requests.RequestException as exc:
            raise RuntimeError(f"Grok request failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        if not self.api_key:
            return {"connected": False, "error": "GROK_API_KEY not set"}
        try:
            r = requests.get(
                f"{GROK_API_BASE}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            return {"connected": False, "error": str(exc)}
        if r.status_code == 401:
            return {"connected": False, "error": "Invalid Grok API key"}
        if not r.ok:
            return {"connected": False, "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response from /models"}
        models = [m.get("id", "") for m in payload.get("data", [])]
        return {
            "connected": True,
            "default_model": self.default_model,
            "models": models[:20],
        }

    # ------------------------------------------------------------------
    # Generic chat
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send an OpenAI-style chat completion request.

        Returns ``{"text": "...", "model": "...", "usage": {...}}`` on
        success or ``{"error": "..."}`` on failure.
        """
        if not self.api_key:
            return {"error": "GROK_API_KEY not set"}
        body: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        try:
            r = self._request("chat/completions", body)
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response from /chat/completions"}
        choices = payload.get("choices") or []
        if not choices:
            return {"error": "Empty completion"}
        text = (choices[0].get("message") or {}).get("content", "").strip()
        return {
            "text": text,
            "model": payload.get("model", body["model"]),
            "usage": payload.get("usage", {}),
        }

    # ------------------------------------------------------------------
    # Convenience wrappers used by the compose studio
    # ------------------------------------------------------------------

    def enhance_video_prompt(self, idea: str, *, model: str | None = None) -> dict[str, Any]:
        idea = (idea or "").strip()
        if not idea:
            return {"error": "Idea is empty"}
        return self.chat(
            [
                {"role": "system", "content": VIDEO_PROMPT_SYSTEM},
                {"role": "user", "content": idea},
            ],
            model=model,
            temperature=0.8,
        )

    def rewrite_post(
        self,
        draft: str,
        platform: str,
        *,
        voice_notes: str = "",
        model: str | None = None,
    ) -> dict[str, Any]:
        draft = (draft or "").strip()
        if not draft:
            return {"error": "Draft is empty"}
        user_msg = f"Platform: {platform}\nVoice notes: {voice_notes or '(none)'}\n\nDraft:\n{draft}"
        return self.chat(
            [
                {"role": "system", "content": POST_REWRITE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            model=model,
            temperature=0.7,
        )

    def generate_alt_text(self, image_description: str) -> dict[str, Any]:
        image_description = (image_description or "").strip()
        if not image_description:
            return {"error": "Image description is empty"}
        return self.chat(
            [
                {"role": "system", "content": ALT_TEXT_SYSTEM},
                {"role": "user", "content": image_description},
            ],
            temperature=0.4,
            max_tokens=80,
        )
