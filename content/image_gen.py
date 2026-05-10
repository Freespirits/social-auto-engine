"""AI image generation via Replicate (SDXL / Flux).

The compose modal's "Generate image" button hits `POST /compose/generate-image`,
which calls `generate_image(prompt)`. The provider is Replicate by default.
An `OPENAI_API_KEY` in the environment enables DALL-E 3 as an alternative.

The generated image URL is returned and dropped into the image_url field.
"""
from __future__ import annotations

import os


class ImageGenError(RuntimeError):
    """Raised when image generation fails."""


class ImageAuthError(ImageGenError):
    """Raised when credentials are missing or invalid."""


def generate_image(
    prompt: str,
    provider: str | None = None,
    aspect_ratio: str = "1:1",
) -> str:
    prompt = prompt.strip()
    if not prompt:
        raise ImageGenError("Prompt must not be empty.")

    chosen = (provider or os.environ.get("IMAGE_PROVIDER") or "replicate").lower()

    if chosen == "replicate":
        return _generate_replicate(prompt, aspect_ratio)
    elif chosen == "openai":
        return _generate_dalle(prompt)
    else:
        raise ImageGenError(
            f"Unknown image provider '{chosen}'. Valid options: replicate, openai."
        )


def _generate_replicate(prompt: str, aspect_ratio: str) -> str:
    api_token = os.environ.get("REPLICATE_API_TOKEN")
    if not api_token:
        raise ImageAuthError(
            "REPLICATE_API_TOKEN is not set. "
            "Add it to .env and restart. "
            "Get a token at https://replicate.com/account/api-tokens"
        )

    import replicate  # late import

    model = os.environ.get(
        "REPLICATE_IMAGE_MODEL",
        "black-forest-labs/flux-schnell",
    )
    try:
        output = replicate.run(
            model,
            input={"prompt": prompt, "aspect_ratio": aspect_ratio},
        )
    except Exception as exc:
        if "401" in str(exc) or "Unauthenticated" in str(exc):
            raise ImageAuthError(
                "Your REPLICATE_API_TOKEN is invalid or expired. "
                "Rotate it at https://replicate.com/account/api-tokens"
            )
        raise ImageGenError(f"Replicate generation failed: {exc}") from exc

    if isinstance(output, list) and output:
        return str(output[0])
    if hasattr(output, "url"):
        return str(output.url)
    return str(output)


def _generate_dalle(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ImageAuthError(
            "OPENAI_API_KEY is not set. "
            "Add it to .env and restart. "
            "Get a key at https://platform.openai.com/api-keys"
        )

    from openai import OpenAI  # late import
    import openai as openai_mod

    client = OpenAI()
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
    except openai_mod.AuthenticationError:
        raise ImageAuthError(
            "Your OPENAI_API_KEY is invalid or expired. "
            "Rotate it at https://platform.openai.com/api-keys"
        )
    except Exception as exc:
        raise ImageGenError(f"DALL-E generation failed: {exc}") from exc

    return response.data[0].url
