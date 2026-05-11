"""Amazon Bedrock adapter for Claude, SDXL, and Titan."""
from __future__ import annotations

import os


class BedrockError(RuntimeError):
    pass


class BedrockAuthError(BedrockError):
    pass


class BedrockAdapter:
    def __init__(self) -> None:
        self.access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        self.region = os.environ.get("AWS_REGION", "us-east-1")
        self.text_model = os.environ.get(
            "BEDROCK_TEXT_MODEL", "anthropic.claude-sonnet-4-20250514"
        )
        self.image_model = os.environ.get(
            "BEDROCK_IMAGE_MODEL", "stability.stable-diffusion-xl-v1"
        )

    def _check_auth(self) -> None:
        if not self.access_key or not self.secret_key:
            raise BedrockAuthError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are not set. "
                "Configure AWS credentials for Bedrock access."
            )

    def ping(self) -> bool:
        if not self.access_key or not self.secret_key:
            return False
        try:
            import boto3
            client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            client.list_foundation_models = None
            bedrock = boto3.client(
                "bedrock",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            bedrock.list_foundation_models(maxResults=1)
            return True
        except ImportError:
            return self._ping_urllib()
        except Exception:
            return False

    def _ping_urllib(self) -> bool:
        try:
            from ai_services._aws_sig import signed_request
            resp = signed_request(
                method="GET",
                service="bedrock",
                region=self.region,
                path="/foundation-models?maxResults=1",
                access_key=self.access_key,
                secret_key=self.secret_key,
            )
            return resp["status"] == 200
        except Exception:
            return False

    def generate_text(self, prompt: str, *, max_tokens: int = 500) -> str:
        self._check_auth()
        try:
            import boto3
            import json
            client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = client.invoke_model(
                modelId=self.text_model,
                body=body,
                contentType="application/json",
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"].strip()
        except ImportError:
            raise BedrockError(
                "boto3 is required for Bedrock. Install with: pip install boto3"
            )
        except Exception as exc:
            if "AccessDenied" in str(exc) or "credentials" in str(exc).lower():
                raise BedrockAuthError(
                    "AWS credentials are invalid or lack Bedrock permissions."
                )
            raise BedrockError(f"Bedrock text generation failed: {exc}") from exc

    def enhance_prompt(self, text: str) -> str:
        """Enhance a social media post using Claude on Bedrock."""
        return self.generate_text(
            "Improve this social media post. Make it more engaging and "
            "shareable while keeping the same meaning and tone. "
            f"Return only the improved text, nothing else.\n\n{text}"
        )

    def rewrite(self, text: str, style: str = "professional") -> str:
        """Rewrite a social media post in a given style using Claude on Bedrock."""
        return self.generate_text(
            f"Rewrite this social media post in a {style} style. "
            f"Return only the rewritten text, nothing else.\n\n{text}"
        )

    def generate_image(self, prompt: str, *, width: int = 1024, height: int = 1024) -> bytes:
        self._check_auth()
        try:
            import boto3
            import json
            import base64
            client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            body = json.dumps({
                "text_prompts": [{"text": prompt}],
                "cfg_scale": 7,
                "steps": 30,
                "width": width,
                "height": height,
            })
            response = client.invoke_model(
                modelId=self.image_model,
                body=body,
                contentType="application/json",
            )
            result = json.loads(response["body"].read())
            return base64.b64decode(result["artifacts"][0]["base64"])
        except ImportError:
            raise BedrockError(
                "boto3 is required for Bedrock. Install with: pip install boto3"
            )
        except Exception as exc:
            if "AccessDenied" in str(exc) or "credentials" in str(exc).lower():
                raise BedrockAuthError(
                    "AWS credentials are invalid or lack Bedrock permissions."
                )
            raise BedrockError(f"Bedrock image generation failed: {exc}") from exc
