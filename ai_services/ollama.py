"""Ollama local LLM adapter (free fallback, no API key required)."""
from __future__ import annotations

import os


class OllamaError(RuntimeError):
    pass


class OllamaAdapter:
    def __init__(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    def ping(self) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        import urllib.request
        import json

        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=10) as resp:
                data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. "
                f"Is it running? Error: {exc}"
            ) from exc

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        import urllib.request
        import json

        payload = json.dumps({
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data.get("response", "").strip()
        except Exception as exc:
            raise OllamaError(
                f"Ollama generation failed. Is the '{model or self.model}' "
                f"model pulled? Error: {exc}"
            ) from exc

    def enhance_prompt(self, text: str) -> str:
        return self.generate(
            f"Improve this social media post. Make it more engaging and "
            f"shareable while keeping the same meaning and tone. "
            f"Return only the improved text, nothing else.\n\n{text}"
        )

    def rewrite(self, text: str, style: str = "professional") -> str:
        return self.generate(
            f"Rewrite this social media post in a {style} style. "
            f"Return only the rewritten text, nothing else.\n\n{text}"
        )
