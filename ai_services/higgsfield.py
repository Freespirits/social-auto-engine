"""HiggsField video generation adapter (with Replicate fallback).

The dashboard exposes a single ``generate_video(prompt, ...)`` interface.
Under the hood the adapter picks a backend in this order:

1. **HiggsField direct API.** Used when ``HIGGSFIELD_API_KEY`` is set.
   At time of writing the public REST surface is partial. The adapter
   speaks the documented shape and tolerates a 404 by surfacing a
   "service unavailable" error rather than crashing.
2. **Replicate.** Used when ``REPLICATE_API_TOKEN`` is set. Replicate
   hosts MiniMax Hailuo, Kling, Veo and many other video models so it
   acts as a reliable fallback even when HiggsField is unreachable.
   Configurable via ``REPLICATE_VIDEO_MODEL`` (default
   ``minimax/video-01``).

Generation is asynchronous on both backends. The adapter returns a job
id immediately and the dashboard polls ``get_job(job_id)`` until the
job reports ``status == "succeeded"``. The video URL surfaces in
``output``.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests


HIGGSFIELD_API_BASE = "https://api.higgsfield.ai/v1"
REPLICATE_API_BASE = "https://api.replicate.com/v1"
DEFAULT_REPLICATE_VIDEO_MODEL = "minimax/video-01"


class HiggsFieldAPI:
    """Provider-agnostic video generation client."""

    def __init__(self) -> None:
        self.higgsfield_key = os.getenv("HIGGSFIELD_API_KEY", "")
        self.replicate_token = os.getenv("REPLICATE_API_TOKEN", "")
        self.replicate_model = os.getenv(
            "REPLICATE_VIDEO_MODEL", DEFAULT_REPLICATE_VIDEO_MODEL
        )

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        if self.higgsfield_key:
            return "higgsfield"
        if self.replicate_token:
            return "replicate"
        return "none"

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        provider = self.provider
        if provider == "none":
            return {
                "connected": False,
                "error": "Set HIGGSFIELD_API_KEY or REPLICATE_API_TOKEN",
            }
        if provider == "higgsfield":
            return self._ping_higgsfield()
        return self._ping_replicate()

    def _ping_higgsfield(self) -> dict[str, Any]:
        try:
            r = requests.get(
                f"{HIGGSFIELD_API_BASE}/account",
                headers={"Authorization": f"Bearer {self.higgsfield_key}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            return {"connected": False, "provider": "higgsfield", "error": str(exc)}
        if r.status_code in (404, 405):
            # API surface not exposed yet; the key may still work for jobs
            return {
                "connected": True,
                "provider": "higgsfield",
                "note": "Account endpoint unavailable; key accepted at job submit",
            }
        if r.status_code == 401:
            return {"connected": False, "provider": "higgsfield", "error": "Invalid HiggsField key"}
        if not r.ok:
            return {"connected": False, "provider": "higgsfield", "error": f"HTTP {r.status_code}"}
        return {"connected": True, "provider": "higgsfield"}

    def _ping_replicate(self) -> dict[str, Any]:
        try:
            r = requests.get(
                f"{REPLICATE_API_BASE}/account",
                headers={"Authorization": f"Bearer {self.replicate_token}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            return {"connected": False, "provider": "replicate", "error": str(exc)}
        if r.status_code == 401:
            return {"connected": False, "provider": "replicate", "error": "Invalid Replicate token"}
        if not r.ok:
            return {"connected": False, "provider": "replicate", "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            payload = {}
        return {
            "connected": True,
            "provider": "replicate",
            "username": payload.get("username", ""),
            "model": self.replicate_model,
        }

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def generate_video(
        self,
        prompt: str,
        *,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        image_url: str | None = None,
    ) -> dict[str, Any]:
        """Submit a video generation job and return ``{"job_id": ..., "provider": ...}``.

        ``duration`` is in seconds. Supported values vary per provider.
        ``image_url`` enables image-to-video on backends that support it.
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return {"error": "Prompt is empty"}
        provider = self.provider
        if provider == "higgsfield":
            return self._submit_higgsfield(prompt, duration, aspect_ratio, seed, image_url)
        if provider == "replicate":
            return self._submit_replicate(prompt, duration, aspect_ratio, seed, image_url)
        return {"error": "No video provider configured"}

    def _submit_higgsfield(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        seed: int | None,
        image_url: str | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        if seed is not None:
            body["seed"] = seed
        if image_url:
            body["image_url"] = image_url
        try:
            r = requests.post(
                f"{HIGGSFIELD_API_BASE}/videos",
                headers={
                    "Authorization": f"Bearer {self.higgsfield_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60,
            )
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HiggsField HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response from HiggsField"}
        return {
            "provider": "higgsfield",
            "job_id": payload.get("id", ""),
            "status": payload.get("status", "queued"),
            "submitted_at": time.time(),
        }

    def _submit_replicate(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        seed: int | None,
        image_url: str | None,
    ) -> dict[str, Any]:
        # Replicate models accept slightly different inputs. We pass a
        # superset; Replicate ignores keys the model does not declare.
        inputs: dict[str, Any] = {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        if seed is not None:
            inputs["seed"] = seed
        if image_url:
            inputs["first_frame_image"] = image_url
            inputs["image"] = image_url
        body = {"input": inputs}
        try:
            r = requests.post(
                f"{REPLICATE_API_BASE}/models/{self.replicate_model}/predictions",
                headers={
                    "Authorization": f"Bearer {self.replicate_token}",
                    "Content-Type": "application/json",
                    "Prefer": "respond-async",
                },
                json=body,
                timeout=60,
            )
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"Replicate HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response from Replicate"}
        return {
            "provider": "replicate",
            "job_id": payload.get("id", ""),
            "status": payload.get("status", "starting"),
            "model": self.replicate_model,
            "submitted_at": time.time(),
        }

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    def get_job(self, job_id: str, *, provider: str | None = None) -> dict[str, Any]:
        """Return the current status of a previously submitted job.

        Result dict keys: ``status`` (queued|running|succeeded|failed),
        ``output`` (URL or list of URLs when succeeded), ``error`` when
        failed, ``progress`` (0-1 when reported by the backend).
        """
        prov = provider or self.provider
        if prov == "higgsfield":
            return self._get_higgsfield_job(job_id)
        if prov == "replicate":
            return self._get_replicate_job(job_id)
        return {"status": "failed", "error": "No video provider configured"}

    def _get_higgsfield_job(self, job_id: str) -> dict[str, Any]:
        try:
            r = requests.get(
                f"{HIGGSFIELD_API_BASE}/videos/{job_id}",
                headers={"Authorization": f"Bearer {self.higgsfield_key}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"status": "failed", "error": str(exc)}
        if not r.ok:
            return {"status": "failed", "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            return {"status": "failed", "error": "Non-JSON response"}
        return {
            "status": payload.get("status", "running"),
            "output": payload.get("video_url") or payload.get("output", ""),
            "progress": payload.get("progress"),
            "error": payload.get("error"),
        }

    def _get_replicate_job(self, job_id: str) -> dict[str, Any]:
        try:
            r = requests.get(
                f"{REPLICATE_API_BASE}/predictions/{job_id}",
                headers={"Authorization": f"Bearer {self.replicate_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"status": "failed", "error": str(exc)}
        if not r.ok:
            return {"status": "failed", "error": f"HTTP {r.status_code}"}
        try:
            payload = r.json()
        except ValueError:
            return {"status": "failed", "error": "Non-JSON response"}
        status_map = {
            "starting": "queued",
            "processing": "running",
            "succeeded": "succeeded",
            "failed": "failed",
            "canceled": "failed",
        }
        replicate_status = payload.get("status", "starting")
        output = payload.get("output", "")
        # Replicate sometimes returns a list of one URL.
        if isinstance(output, list) and output:
            output = output[0]
        return {
            "status": status_map.get(replicate_status, replicate_status),
            "output": output,
            "error": payload.get("error"),
            "logs": payload.get("logs", "")[-500:] if payload.get("logs") else "",
        }
