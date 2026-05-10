"""Amazon Bedrock adapter.

Bedrock exposes Anthropic Claude, Meta Llama, Mistral, Stability AI
Stable Diffusion and Amazon Titan models behind a single AWS-signed
API. The adapter uses ``boto3`` when available, falling back to a
clear "boto3 not installed" error otherwise.

Credentials are sourced from any of:

* The Settings page (key id, secret, region pasted by the user;
  persisted by ``_store_tokens`` as ``AWS_ACCESS_KEY_ID``,
  ``AWS_SECRET_ACCESS_KEY``, ``AWS_REGION``).
* The standard AWS credential chain (``~/.aws/credentials``, IAM
  instance profile, env vars).

Used as:

* Premium alternative to Grok for prompt enhancement (Claude on
  Bedrock).
* Image generation backend (Stable Diffusion XL or Titan Image G1).

The adapter intentionally returns dicts rather than raising, matching
the rest of the AI services package.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

# Defaults updated 2026-05-07. The previous Claude 3.5 Sonnet snapshot was
# EOL'd on Bedrock. Haiku 4.5 (via the us. cross-region inference profile)
# is the cheapest currently-active Claude. Nova Canvas is Amazon's current
# image model and shares the request shape with Titan Image, which keeps
# the invoke_image branching simple.
DEFAULT_TEXT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_IMAGE_MODEL = "amazon.nova-canvas-v1:0"
DEFAULT_REGION = "us-east-1"


def _get_boto3():
    try:
        import boto3  # type: ignore

        return boto3
    except ImportError:
        return None


class BedrockAPI:
    """boto3-backed Bedrock Runtime client."""

    def __init__(self) -> None:
        # Three credential paths, any of which is enough:
        #   1. Bedrock long-term API key (single token).  AWS released
        #      these July 2025 to skip the full IAM access-key dance.
        #   2. Classic access-key + secret pair.
        #   3. Standard credential chain (~/.aws/credentials, IAM role).
        # boto3 1.39+ honours AWS_BEARER_TOKEN_BEDROCK automatically.
        self.bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
        self.access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.region = os.getenv("AWS_REGION") or os.getenv(
            "AWS_DEFAULT_REGION", DEFAULT_REGION
        )
        self.text_model = os.getenv("BEDROCK_TEXT_MODEL", DEFAULT_TEXT_MODEL)
        self.image_model = os.getenv("BEDROCK_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)

    # ------------------------------------------------------------------
    # boto3 client
    # ------------------------------------------------------------------

    def _client(self, service: str = "bedrock-runtime"):
        boto3 = _get_boto3()
        if boto3 is None:
            return None
        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        try:
            return boto3.client(service, **kwargs)
        except Exception:  # boto3 raises a variety of client errors
            return None

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        if _get_boto3() is None:
            return {"connected": False, "error": "boto3 not installed"}
        if not (
            self.bearer_token
            or self.access_key
            or os.path.exists(os.path.expanduser("~/.aws/credentials"))
        ):
            return {"connected": False, "error": "AWS credentials not set"}
        client = self._client(service="bedrock")
        if client is None:
            return {"connected": False, "error": "Could not create Bedrock client"}
        try:
            resp = client.list_foundation_models()
        except Exception as exc:
            return {"connected": False, "error": str(exc)[:200]}
        models = [
            m.get("modelId", "") for m in resp.get("modelSummaries", [])
        ][:50]
        auth_method = (
            "bearer-token" if self.bearer_token
            else "access-key" if self.access_key
            else "credential-chain"
        )
        return {
            "connected": True,
            "region": self.region,
            "auth_method": auth_method,
            "text_model": self.text_model,
            "image_model": self.image_model,
            "model_count": len(resp.get("modelSummaries", [])),
            "sample_models": models[:10],
        }

    # ------------------------------------------------------------------
    # Text via Anthropic Claude on Bedrock
    # ------------------------------------------------------------------

    def invoke_text(
        self,
        prompt: str,
        *,
        system: str = "",
        model_id: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return {"error": "Prompt is empty"}
        client = self._client()
        if client is None:
            return {"error": "Could not create Bedrock client"}
        model = model_id or self.text_model
        # Bedrock's Anthropic invocation shape:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        try:
            resp = client.invoke_model(
                modelId=model,
                body=json.dumps(body).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(resp["body"].read())
        except Exception as exc:
            return {"error": str(exc)[:300]}
        chunks = payload.get("content", []) or []
        text = "".join(c.get("text", "") for c in chunks if c.get("type") == "text").strip()
        return {
            "text": text,
            "model": model,
            "usage": payload.get("usage", {}),
        }

    # ------------------------------------------------------------------
    # Image via Stable Diffusion or Titan Image
    # ------------------------------------------------------------------

    def invoke_image(
        self,
        prompt: str,
        *,
        model_id: str | None = None,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return {"error": "Prompt is empty"}
        client = self._client()
        if client is None:
            return {"error": "Could not create Bedrock client"}
        model = model_id or self.image_model
        # Nova Canvas (Amazon's current image model) is marked LEGACY in
        # the Bedrock catalog. AWS blocks new accounts from using it
        # unless the model has been used in the past 30 days. If the
        # invocation fails with that signature, surface a clear error
        # rather than the generic AWS message.
        if model.startswith("stability."):
            body = {
                "text_prompts": [{"text": prompt, "weight": 1.0}],
                "cfg_scale": 7,
                "steps": 30,
                "width": width,
                "height": height,
            }
            if seed is not None:
                body["seed"] = seed
        elif model.startswith("amazon.titan-image") or model.startswith("amazon.nova-canvas"):
            # Titan Image and Nova Canvas share the same request body.
            body = {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {"text": prompt},
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "width": width,
                    "height": height,
                    "cfgScale": 8.0,
                    "seed": seed if seed is not None else 0,
                },
            }
        else:
            return {"error": f"Unsupported image model: {model}"}
        try:
            resp = client.invoke_model(
                modelId=model,
                body=json.dumps(body).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(resp["body"].read())
        except Exception as exc:
            msg = str(exc)
            if "Legacy" in msg and "active model" in msg:
                return {
                    "error": (
                        "This Bedrock account has no active text-to-image model. "
                        "Request access to Nova Canvas (Amazon Bedrock console > "
                        "Model access > Request) or use the upload-image flow."
                    )
                }
            return {"error": msg[:300]}
        # Normalise the two payload shapes to a single base64 image.
        image_b64 = ""
        if "artifacts" in payload:  # Stability
            artifacts = payload["artifacts"] or []
            if artifacts:
                image_b64 = artifacts[0].get("base64", "")
        elif "images" in payload:  # Titan
            images = payload["images"] or []
            if images:
                image_b64 = images[0]
        if not image_b64:
            return {"error": "No image data returned"}
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            return {"error": f"Decode failed: {exc}"}
        return {
            "image_bytes": image_bytes,
            "mime_type": "image/png",
            "model": model,
        }
