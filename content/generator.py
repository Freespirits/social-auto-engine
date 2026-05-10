"""Generate post drafts via Claude, OpenAI, or Gemini.

The compose dashboard's Sparkles button hits `POST /generate`, which calls
`generate_post(topic)`. The provider is chosen by the `AI_PROVIDER`
environment variable (`claude`, `openai`, or `gemini`). Default is
`claude`.

The voice profile, if present, is read from `about-me.md` and `voice.md`
at the project root and prepended to the prompt. If neither file exists
the generator falls back to a topic-only prompt.

Provider SDKs are imported lazily so users only need to install the one
they actually use.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


CLAUDE_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o-mini"
# Note: the `google.generativeai` package itself is deprecated in favour
# of `google.genai`. Migrating the SDK is tracked separately. Until then
# we use a current GA model name; `gemini-1.5-flash` no longer resolves
# on the v1beta endpoint.
GEMINI_MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 400


class GeneratorError(RuntimeError):
    """Raised when post generation fails."""


class AuthError(GeneratorError):
    """Raised when a provider rejects credentials or they are missing."""


def _read_voice_profile(root: Path) -> str:
    """Return the concatenated contents of `about-me.md` and `voice.md`.

    Either or both may be absent. Missing files contribute nothing. The
    return value is stripped of trailing whitespace.
    """
    parts: list[str] = []
    for filename in ("about-me.md", "voice.md"):
        candidate = root / filename
        if candidate.is_file():
            parts.append(candidate.read_text(encoding="utf-8"))
    return "\n\n".join(parts).strip()


def _build_prompt(topic: str, voice_profile: str) -> str:
    """Compose the user prompt for the chosen provider.

    The prompt asks for a short on-brand social post and instructs the
    model to return only the post text. The voice profile is prepended
    when non-empty.
    """
    sections = ["Draft a short, on-brand social media post."]
    if voice_profile:
        sections.append(f"Voice profile:\n{voice_profile}")
    sections.append(f"Topic: {topic}")
    sections.append(
        "Return only the post text. No headlines and no hashtags unless they "
        "are clearly natural to the voice profile above."
    )
    return "\n\n".join(sections)


def _generate_claude(prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AuthError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to .env and restart. "
            "Get a key at https://console.anthropic.com"
        )
    import anthropic  # late import: only required when the user picks claude

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise AuthError(
            "Your ANTHROPIC_API_KEY is invalid or expired. "
            "Rotate it at https://console.anthropic.com"
        )
    return response.content[0].text.strip()


def _generate_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AuthError(
            "OPENAI_API_KEY is not set. "
            "Add it to .env and restart. "
            "Get a key at https://platform.openai.com/api-keys"
        )
    from openai import OpenAI  # late import
    import openai as openai_mod

    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except openai_mod.AuthenticationError:
        raise AuthError(
            "Your OPENAI_API_KEY is invalid or expired. "
            "Rotate it at https://platform.openai.com/api-keys"
        )
    return response.choices[0].message.content.strip()


def _generate_gemini(prompt: str) -> str:
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        raise AuthError(
            "GOOGLE_AI_API_KEY is not set. "
            "Add it to .env and restart. "
            "Get a key at https://aistudio.google.com/apikey"
        )
    import google.generativeai as genai  # late import

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    try:
        response = model.generate_content(prompt)
    except Exception as exc:
        if "401" in str(exc) or "API_KEY_INVALID" in str(exc):
            raise AuthError(
                "Your GOOGLE_AI_API_KEY is invalid or expired. "
                "Rotate it at https://aistudio.google.com/apikey"
            )
        raise
    return response.text.strip()


_PROVIDERS: dict[str, Callable[[str], str]] = {
    "claude": _generate_claude,
    "openai": _generate_openai,
    "gemini": _generate_gemini,
}


def generate_post(
    topic: str,
    voice_profile: str | None = None,
    provider: str | None = None,
    project_root: Path | None = None,
) -> str:
    """Generate a post draft.

    `topic` is the user-supplied subject line ("What's this post about?").
    `voice_profile` overrides the file-based load when not None, including
    when set to an empty string (which suppresses the voice section).
    `provider` overrides the `AI_PROVIDER` environment variable.
    `project_root` overrides the directory used to look for `voice.md`
    and `about-me.md` (defaults to `Path.cwd()`).

    Raises `GeneratorError` on empty topic, unknown provider, missing SDK,
    or any provider call failure.
    """
    topic = topic.strip()
    if not topic:
        raise GeneratorError("topic must not be empty")

    chosen = (provider or os.environ.get("AI_PROVIDER") or "claude").lower()
    if chosen not in _PROVIDERS:
        valid = ", ".join(sorted(_PROVIDERS))
        raise GeneratorError(
            f"Unknown AI provider '{chosen}'. Valid options: {valid}."
        )

    if voice_profile is None:
        root = project_root or Path.cwd()
        voice_profile = _read_voice_profile(root)

    prompt = _build_prompt(topic, voice_profile)
    handler = _PROVIDERS[chosen]
    try:
        return handler(prompt)
    except ImportError as exc:
        raise GeneratorError(
            f"The '{chosen}' provider needs its SDK installed. "
            f"Try: pip install {chosen}"
        ) from exc
    except GeneratorError:
        raise
    except Exception as exc:
        raise GeneratorError(f"{chosen} generation failed: {exc}") from exc
