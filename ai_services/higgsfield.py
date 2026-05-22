"""Video generation adapter — HiggsField via official SDK, Replicate fallback.

HiggsField ships an official Python SDK at:
    https://github.com/higgsfield-ai/higgsfield-client
    pip install higgsfield-client

This adapter uses that SDK when HF credentials are present, and falls back
to the Replicate adapter when not. The SDK handles auth, retries, polling,
and the actual base URL (`platform.higgsfield.ai`).

Credentials — set EITHER:
    HF_API_KEY=<your-key>
    HF_API_SECRET=<your-secret>
OR the combined form:
    HF_KEY=<key>:<secret>

Get them at https://cloud.higgsfield.ai/.

Backwards compatibility:
- The historical env vars `HIGGSFIELD_API_KEY_ID` and
  `HIGGSFIELD_API_KEY_SECRET` are still read and mapped to the new HF_*
  vars at adapter init. Users who set up SocialBlast under v0.6.0 do not
  need to migrate their tokens.env.
- The `api_key` and `default_model` properties are preserved for legacy
  callers and tests.
"""
from __future__ import annotations

import os


class HiggsFieldError(RuntimeError):
    pass


class HiggsFieldAuthError(HiggsFieldError):
    pass


# Sensible default video model. Override via HIGGSFIELD_MODEL_ID.
# Confirmed from github.com/higgsfield-ai/cli MODELS.md as of 2026-05.
DEFAULT_VIDEO_MODEL = "seedance_2_0"


def _resolve_hf_credentials() -> tuple[str, str]:
    """Read HF credentials with backwards-compat for old env var names.

    Returns (api_key, api_secret). Empty strings when not configured.
    """
    api_key = os.environ.get("HF_API_KEY", "").strip()
    api_secret = os.environ.get("HF_API_SECRET", "").strip()
    if api_key and api_secret:
        return api_key, api_secret

    # Combined form: HF_KEY=key:secret
    combined = os.environ.get("HF_KEY", "").strip()
    if combined and ":" in combined:
        key, _, secret = combined.partition(":")
        if key and secret:
            return key.strip(), secret.strip()

    # Backwards-compat with v0.6.0 env vars
    legacy_key = os.environ.get("HIGGSFIELD_API_KEY_ID", "").strip()
    legacy_secret = os.environ.get("HIGGSFIELD_API_KEY_SECRET", "").strip()
    if legacy_key and legacy_secret:
        return legacy_key, legacy_secret

    return "", ""


class HiggsFieldAdapter:
    REPLICATE_BASE_URL = "https://api.replicate.com/v1"

    def __init__(self) -> None:
        self.higgsfield_key_id, self.higgsfield_key_secret = _resolve_hf_credentials()
        self.replicate_key = os.environ.get("REPLICATE_API_TOKEN", "")
        self.higgsfield_model = os.environ.get("HIGGSFIELD_MODEL_ID", DEFAULT_VIDEO_MODEL)
        self.replicate_model = os.environ.get(
            "HIGGSFIELD_MODEL",
            "minimax/video-01-live",
        )
        self.backend = self._select_backend()

    @property
    def api_key(self) -> str:
        """Backwards-compat: single credential string for the active backend."""
        if self.backend == "higgsfield":
            return self.higgsfield_key_id
        if self.backend == "replicate":
            return self.replicate_key
        return ""

    @property
    def default_model(self) -> str:
        """Backwards-compat: model identifier for the active backend."""
        if self.backend == "higgsfield":
            return self.higgsfield_model
        return self.replicate_model

    @property
    def is_configured(self) -> bool:
        return self.backend != "none"

    def _select_backend(self) -> str:
        if self.higgsfield_key_id and self.higgsfield_key_secret:
            return "higgsfield"
        if self.replicate_key:
            return "replicate"
        return "none"

    def _hf_client(self):
        """Return a configured higgsfield_client.SyncClient or raise.

        Passes the api_key directly via the SDK constructor rather than
        mutating os.environ, so test fixtures can isolate credentials
        per-test without leaking.
        """
        try:
            import higgsfield_client
        except ImportError as exc:
            raise HiggsFieldError(
                "higgsfield-client is not installed. "
                "Run: pip install higgsfield-client"
            ) from exc

        if not (self.higgsfield_key_id and self.higgsfield_key_secret):
            raise HiggsFieldAuthError(
                "HiggsField credentials missing. Set HF_API_KEY and "
                "HF_API_SECRET (get a pair at https://cloud.higgsfield.ai/)."
            )
        combined = f"{self.higgsfield_key_id}:{self.higgsfield_key_secret}"
        return higgsfield_client.SyncClient(api_key=combined)

    def ping(self) -> bool:
        if self.backend == "higgsfield":
            try:
                self._hf_client()
                return True
            except Exception:
                return False
        if self.backend == "replicate":
            return self._ping_replicate()
        return False

    def _ping_replicate(self) -> bool:
        import urllib.request

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
                "No video backend configured. Set HF_API_KEY and HF_API_SECRET "
                "(get a pair at https://cloud.higgsfield.ai/) or "
                "REPLICATE_API_TOKEN as a fallback."
            )
        if self.backend == "higgsfield":
            try:
                return self._generate_higgsfield(
                    prompt,
                    first_frame_image=first_frame_image,
                    model_id=model or self.higgsfield_model,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                )
            except HiggsFieldAuthError:
                raise
            except HiggsFieldError:
                if not self.replicate_key:
                    raise
                # Soft-degrade to Replicate when REST call fails for non-auth reasons
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
        """Submit a video generation job via the official higgsfield-client SDK."""
        try:
            import higgsfield_client
        except ImportError:
            raise HiggsFieldError(
                "higgsfield-client is not installed. "
                "Run: pip install higgsfield-client"
            )

        client = self._hf_client()
        arguments: dict = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        if first_frame_image:
            arguments["start_image"] = first_frame_image
        try:
            controller = client.submit(application=model_id, arguments=arguments)
        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "Unauthorized" in msg or "Credentials" in msg:
                raise HiggsFieldAuthError(
                    "HF_API_KEY or HF_API_SECRET is invalid. "
                    "Verify at https://cloud.higgsfield.ai/."
                ) from exc
            raise HiggsFieldError(f"HiggsField submit failed: {exc}") from exc
        return {
            "id": controller.request_id,
            "status": "processing",
            "output_url": None,
            "backend": "higgsfield",
            "model": model_id,
            "status_url": controller.status_url,
        }

    def _generate_replicate(
        self,
        prompt: str,
        *,
        first_frame_image: str | None,
        model_id: str,
    ) -> dict:
        import json
        import urllib.error
        import urllib.request

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
                raise HiggsFieldAuthError("REPLICATE_API_TOKEN is invalid or expired.")
            raise HiggsFieldError(f"Replicate video generation failed: HTTP {exc.code}")
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

    def _poll_higgsfield(self, request_id: str) -> dict:
        """Poll HiggsField job status via the official SDK."""
        try:
            client = self._hf_client()
            controller = client.get_request_controller(request_id)
            status = controller.status()
            status_name = type(status).__name__.lower()
        except HiggsFieldAuthError:
            raise
        except Exception as exc:
            raise HiggsFieldError(f"Failed to fetch generation: {exc}") from exc

        # Try to fetch result if completed; otherwise return status only.
        output_url = None
        if status_name == "completed":
            try:
                result = controller.get()
                if isinstance(result, dict):
                    output_url = (
                        result.get("video_url")
                        or result.get("output_url")
                        or (result.get("videos", [{}])[0].get("url") if result.get("videos") else None)
                    )
            except Exception:
                pass

        return {
            "id": request_id,
            "status": status_name,
            "output_url": output_url,
            "backend": "higgsfield",
        }

    def _poll_replicate(self, prediction_id: str) -> dict:
        import json
        import urllib.request

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
        """Stub — HiggsField virality predictor is a separate model.

        On the official API, virality scoring is done by submitting a job
        to the ``brain_activity`` model with an existing video UUID, not by
        scoring a prompt. We leave this as a stub for now; the prompt-time
        prediction we wired into the wizard is non-essential UX polish.
        """
        if self.backend != "higgsfield":
            return {"score": None, "reason": "Virality prediction requires HiggsField."}
        return {
            "score": None,
            "reason": (
                "HiggsField virality (brain_activity) scores existing videos, not prompts. "
                "Run after generation completes."
            ),
        }
