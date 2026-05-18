"""Video generation adapter with HiggsField native first, Replicate fallback.

HiggsField is a multi-model aggregator (Veo 3.1, Kling 3.0, Seedance 2.0,
Minimax Hailuo, Wan, Grok Imagine, etc.) with virality prediction. We talk to
their REST API when HIGGSFIELD_API_KEY is set, otherwise we fall back to
Replicate via REPLICATE_API_TOKEN for backwards compatibility.

Auth precedence: HIGGSFIELD_API_KEY > REPLICATE_API_TOKEN.
Backend is selected at adapter init and cached.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class HiggsFieldError(RuntimeError):
    pass


class HiggsFieldAuthError(HiggsFieldError):
    pass


class HiggsFieldAdapter:
    HIGGSFIELD_BASE_URL = "https://higgsfield.ai/api/v1"
    REPLICATE_BASE_URL = "https://api.replicate.com/v1"

    def __init__(self) -> None:
        self.higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "")
        self.replicate_key = os.environ.get("REPLICATE_API_TOKEN", "")
        self.higgsfield_model = os.environ.get("HIGGSFIELD_MODEL_ID", "veo3_1")
        self.replicate_model = os.environ.get(
            "HIGGSFIELD_MODEL",
            "minimax/video-01-live",
        )
        self.backend = self._select_backend()

    def _select_backend(self) -> str:
        if self.higgsfield_key:
            return "higgsfield"
        if self.replicate_key:
            return "replicate"
        return "none"

    @property
    def is_configured(self) -> bool:
        return self.backend != "none"

    def ping(self) -> bool:
        if self.backend == "higgsfield":
            return self._ping_higgsfield()
        if self.backend == "replicate":
            return self._ping_replicate()
        return False

    def _ping_higgsfield(self) -> bool:
        req = urllib.request.Request(
            f"{self.HIGGSFIELD_BASE_URL}/balance",
            headers={"Authorization": f"Bearer {self.higgsfield_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _ping_replicate(self) -> bool:
        req = urllib.request.Request(
            f"{self.REPLICATE_BASE_URL}/models/{self.replicate_model}",
            headers={"Authorization": f"Bearer {self.replicate_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate_video(
        self,
        prompt: str,
        *,
        first_frame_image: str | None = None,
        model: str | None = None,
        aspect_ratio: str = "9:16",
        duration: int = 6,
    ) -> dict:
        if self.backend == "none":
            raise HiggsFieldAuthError(
                "No video backend configured. Set HIGGSFIELD_API_KEY "
                "(preferred, get one at https://higgsfield.ai) or "
                "REPLICATE_API_TOKEN (fallback)."
            )
        if self.backend == "higgsfield":
            return self._generate_higgsfield(
                prompt,
                first_frame_image=first_frame_image,
                model_id=model or self.higgsfield_model,
                aspect_ratio=aspect_ratio,
                duration=duration,
            )
        return self._generate_replicate(
            prompt,
            first_frame_image=first_frame_image,
            model_id=model or self.replicate_model,
        )

    def _generate_higgsfield(
        self,
        prompt: str,
        *,
        first_frame_image: str | None,
        model_id: str,
        aspect_ratio: str,
        duration: int,
    ) -> dict:
        body: dict = {
            "model_id": model_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        if first_frame_image:
            body["medias"] = [
                {"role": "start_image", "url": first_frame_image},
            ]
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.HIGGSFIELD_BASE_URL}/generations/video",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.higgsfield_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise HiggsFieldAuthError(
                    "HIGGSFIELD_API_KEY is invalid or expired."
                )
            raise HiggsFieldError(
                f"HiggsField video generation failed: HTTP {exc.code}"
            )
        except Exception as exc:
            raise HiggsFieldError(f"HiggsField video generation failed: {exc}") from exc
        return {
            "id": data.get("id") or data.get("generation_id"),
            "status": data.get("status", "processing"),
            "output_url": data.get("output_url") or data.get("video_url"),
            "backend": "higgsfield",
            "model": model_id,
        }

    def _generate_replicate(
        self,
        prompt: str,
        *,
        first_frame_image: str | None,
        model_id: str,
    ) -> dict:
        input_data: dict = {"prompt": prompt}
        if first_frame_image:
            input_data["first_frame_image"] = first_frame_image
        payload = json.dumps({"version": None, "input": input_data}).encode()
        req = urllib.request.Request(
            f"{self.REPLICATE_BASE_URL}/models/{model_id}/predictions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.replicate_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise HiggsFieldAuthError(
                    "REPLICATE_API_TOKEN is invalid or expired."
                )
            raise HiggsFieldError(
                f"Replicate video generation failed: HTTP {exc.code}"
            )
        except Exception as exc:
            raise HiggsFieldError(f"Replicate video generation failed: {exc}") from exc
        if data.get("status") == "failed":
            raise HiggsFieldError(
                f"Video generation failed: {data.get('error', 'unknown')}"
            )
        output = data.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        return {
            "id": data.get("id"),
            "status": data.get("status"),
            "output_url": output,
            "backend": "replicate",
            "model": model_id,
        }

    def get_prediction(self, prediction_id: str) -> dict:
        if self.backend == "higgsfield":
            return self._poll_higgsfield(prediction_id)
        if self.backend == "replicate":
            return self._poll_replicate(prediction_id)
        raise HiggsFieldAuthError("No video backend configured.")

    def _poll_higgsfield(self, generation_id: str) -> dict:
        req = urllib.request.Request(
            f"{self.HIGGSFIELD_BASE_URL}/generations/{generation_id}",
            headers={"Authorization": f"Bearer {self.higgsfield_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise HiggsFieldError(f"Failed to fetch generation: {exc}") from exc
        return {
            "id": data.get("id") or generation_id,
            "status": data.get("status"),
            "output_url": data.get("output_url") or data.get("video_url"),
            "backend": "higgsfield",
        }

    def _poll_replicate(self, prediction_id: str) -> dict:
        req = urllib.request.Request(
            f"{self.REPLICATE_BASE_URL}/predictions/{prediction_id}",
            headers={"Authorization": f"Bearer {self.replicate_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise HiggsFieldError(f"Failed to fetch prediction: {exc}") from exc
        output = data.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        return {
            "id": data.get("id"),
            "status": data.get("status"),
            "output_url": output,
            "backend": "replicate",
        }

    def predict_virality(self, prompt: str, *, platform: str = "instagram") -> dict:
        """Score how likely a caption is to go viral, if backend supports it.

        Only HiggsField backend implements this. Replicate returns a stub.
        """
        if self.backend != "higgsfield":
            return {"score": None, "reason": "Virality prediction requires HiggsField."}
        body = json.dumps({"prompt": prompt, "platform": platform}).encode()
        req = urllib.request.Request(
            f"{self.HIGGSFIELD_BASE_URL}/virality/predict",
            data=body,
            headers={
                "Authorization": f"Bearer {self.higgsfield_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            return {"score": None, "reason": f"Prediction failed: {exc}"}
        return {
            "score": data.get("score"),
            "engagement_prediction": data.get("engagement_prediction"),
            "reason": data.get("reason"),
        }
