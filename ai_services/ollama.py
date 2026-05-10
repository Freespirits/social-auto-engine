"""Ollama adapter: local large-language-model runner.

Ollama serves models over a plain HTTP API at
``http://localhost:11434`` by default. No authentication. Configure
with ``OLLAMA_BASE_URL`` for remote installs (eg. a tunnel to a home
GPU box) and ``OLLAMA_DEFAULT_MODEL`` to pin a model.

Used as the zero-cost alternative to Grok or Bedrock for prompt
enhancement and post rewriting. The dashboard prefers Ollama when it
is reachable and the user has not configured a paid provider.
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


class OllamaAPI:
    """HTTP client for a local or remote Ollama server."""

    def __init__(self) -> None:
        base = os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.base_url = base
        self.default_model = os.getenv("OLLAMA_DEFAULT_MODEL", DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        try:
            # Tight timeouts because the Settings page renders this synchronously
            # and Ollama is most often unreachable on a fresh install. Localhost
            # connects in <10 ms when running, so 0.8 s is generous.
            r = requests.get(f"{self.base_url}/api/tags", timeout=(0.8, 1.5))
        except requests.RequestException as exc:
            return {"connected": False, "error": str(exc)}
        if not r.ok:
            return {"connected": False, "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response"}
        models = [m.get("name", "") for m in payload.get("models", [])]
        return {
            "connected": True,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "models": models,
            "default_available": self.default_model in models,
        }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_models(self) -> list[str]:
        info = self.ping()
        return info.get("models", []) if info.get("connected") else []

    # ------------------------------------------------------------------
    # Generate / chat
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.7,
        num_predict: int = 512,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return {"error": "Prompt is empty"}
        body: dict[str, Any] = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        if system:
            body["system"] = system
        try:
            r = requests.post(f"{self.base_url}/api/generate", json=body, timeout=300)
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response"}
        return {
            "text": payload.get("response", "").strip(),
            "model": payload.get("model", body["model"]),
            "eval_count": payload.get("eval_count", 0),
            "total_duration": payload.get("total_duration", 0),
        }

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        body = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            r = requests.post(f"{self.base_url}/api/chat", json=body, timeout=300)
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response"}
        msg = payload.get("message") or {}
        return {
            "text": msg.get("content", "").strip(),
            "model": payload.get("model", body["model"]),
            "eval_count": payload.get("eval_count", 0),
        }
