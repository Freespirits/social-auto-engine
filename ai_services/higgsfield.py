"""HiggsField / Replicate video generation adapter."""
from __future__ import annotations

import os


class HiggsFieldError(RuntimeError):
    pass


class HiggsFieldAuthError(HiggsFieldError):
    pass


class HiggsFieldAdapter:
    BASE_URL = "https://api.replicate.com/v1"

    def __init__(self) -> None:
        self.api_key = os.environ.get("REPLICATE_API_TOKEN", "")
        self.default_model = os.environ.get(
            "HIGGSFIELD_MODEL",
            "minimax/video-01-live",
        )

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/models/{self.default_model}",
            headers={"Authorization": f"Bearer {self.api_key}"},
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
    ) -> dict:
        if not self.api_key:
            raise HiggsFieldAuthError(
                "REPLICATE_API_TOKEN is not set. "
                "Get a key at https://replicate.com/account/api-tokens"
            )
        import urllib.request
        import json

        model_id = model or self.default_model
        input_data: dict = {"prompt": prompt}
        if first_frame_image:
            input_data["first_frame_image"] = first_frame_image

        payload = json.dumps({
            "version": None,
            "input": input_data,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/models/{model_id}/predictions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
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
            }
        except HiggsFieldError:
            raise
        except Exception as exc:
            if "401" in str(exc) or "Unauthorized" in str(exc):
                raise HiggsFieldAuthError(
                    "Your REPLICATE_API_TOKEN is invalid or expired."
                )
            raise HiggsFieldError(f"Video generation failed: {exc}") from exc

    def get_prediction(self, prediction_id: str) -> dict:
        if not self.api_key:
            raise HiggsFieldAuthError(
                "REPLICATE_API_TOKEN is not set. "
                "Get a key at https://replicate.com/account/api-tokens"
            )
        import urllib.request
        import json

        req = urllib.request.Request(
            f"{self.BASE_URL}/predictions/{prediction_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            output = data.get("output")
            if isinstance(output, list):
                output = output[0] if output else None
            return {
                "id": data.get("id"),
                "status": data.get("status"),
                "output_url": output,
            }
        except Exception as exc:
            raise HiggsFieldError(f"Failed to fetch prediction: {exc}") from exc
