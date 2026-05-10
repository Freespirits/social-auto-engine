"""Grok (xAI) adapter for prompt enhancement and post rewriting."""
from __future__ import annotations

import os


class GrokError(RuntimeError):
    pass


class GrokAuthError(GrokError):
    pass


class GrokAdapter:
    BASE_URL = "https://api.x.ai/v1"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GROK_API_KEY", "")
        self.model = os.environ.get("GROK_DEFAULT_MODEL", "grok-3-latest")

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request
        import urllib.error
        import json

        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception:
            return False

    def enhance_prompt(self, text: str) -> str:
        return self._chat(
            f"Improve this social media post. Make it more engaging and "
            f"shareable while keeping the same meaning and tone. "
            f"Return only the improved text, nothing else.\n\n{text}"
        )

    def rewrite(self, text: str, style: str = "professional") -> str:
        return self._chat(
            f"Rewrite this social media post in a {style} style. "
            f"Return only the rewritten text, nothing else.\n\n{text}"
        )

    def _chat(self, prompt: str) -> str:
        if not self.api_key:
            raise GrokAuthError(
                "GROK_API_KEY is not set. "
                "Get a key at https://console.x.ai"
            )
        import urllib.request
        import json

        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            if "401" in str(exc) or "Unauthorized" in str(exc):
                raise GrokAuthError(
                    "Your GROK_API_KEY is invalid or expired."
                )
            raise GrokError(f"Grok request failed: {exc}") from exc
