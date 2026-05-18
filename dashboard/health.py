"""CLI health check: print which AI backends and platforms are configured.

Run with: ``python -m dashboard.health``

Useful for first-run debugging. No secrets are printed.
"""
from __future__ import annotations

import os
import sys


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"


def _has(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def _supports_unicode() -> bool:
    """Test if the current stdout encoding can render filled bullets."""
    enc = (sys.stdout.encoding or "ascii").lower()
    return enc.startswith("utf")


def _row(label: str, ok: bool, hint: str = "", color: bool = True) -> str:
    if _supports_unicode():
        ok_glyph, off_glyph = "●", "○"
    else:
        ok_glyph, off_glyph = "[+]", "[ ]"
    if color:
        dot = f"{GREEN}{ok_glyph}{RESET}" if ok else f"{RED}{off_glyph}{RESET}"
        state = f"{GREEN}ready{RESET}" if ok else f"{DIM}not set{RESET}"
    else:
        dot = ok_glyph if ok else off_glyph
        state = "ready" if ok else "not set"
    line = f"  {dot} {label:<32} {state}"
    if hint and not ok:
        line += f"  {DIM}({hint}){RESET}" if color else f"  ({hint})"
    return line


def _load_env() -> None:
    """Load ~/.social-auto-engine/tokens.env and project .env, like config.py does."""
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        home_tokens = Path.home() / ".social-auto-engine" / "tokens.env"
        if home_tokens.exists():
            load_dotenv(home_tokens)
        local_env = Path(__file__).resolve().parent.parent / ".env"
        if local_env.exists():
            load_dotenv(local_env)
    except Exception:
        pass


def collect() -> dict:
    """Return the same shape as /api/status, no I/O beyond env vars."""
    _load_env()
    try:
        from ai_services.higgsfield import HiggsFieldAdapter
        backend = HiggsFieldAdapter().backend
    except Exception:
        backend = "none"

    return {
        "video": {
            "higgsfield_native": _has("HIGGSFIELD_API_KEY_ID") and _has("HIGGSFIELD_API_KEY_SECRET"),
            "replicate_fallback": _has("REPLICATE_API_TOKEN"),
            "active_backend": backend,
        },
        "voice": {"elevenlabs": _has("ELEVENLABS_API_KEY")},
        "captions": {
            "openai": _has("OPENAI_API_KEY"),
            "anthropic": _has("ANTHROPIC_API_KEY"),
        },
        "images": {
            "replicate": _has("REPLICATE_API_TOKEN"),
            "openai": _has("OPENAI_API_KEY"),
        },
        "platforms": {
            "facebook": _has("FACEBOOK_PAGE_ACCESS_TOKEN"),
            "instagram": _has("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
            "threads": _has("THREADS_ACCESS_TOKEN"),
            "linkedin": _has("LINKEDIN_ACCESS_TOKEN"),
            "whatsapp": _has("WHATSAPP_ACCESS_TOKEN"),
            "tiktok": _has("TIKTOK_ACCESS_TOKEN"),
        },
    }


def render(data: dict, color: bool = True) -> str:
    lines: list[str] = []
    title = "SocialBlast AI. Backend status"
    lines.append(f"\n{BOLD}{title}{RESET}" if color else f"\n{title}")
    lines.append("=" * len(title))

    def section(name: str, items: list[tuple[str, bool, str]]) -> None:
        header = f"\n{BOLD}{name}{RESET}" if color else f"\n{name}"
        lines.append(header)
        for label, ok, hint in items:
            lines.append(_row(label, ok, hint, color=color))

    backend = data["video"]["active_backend"]
    backend_pill = (
        f"  {YELLOW}Active video backend:{RESET} {backend}"
        if color else
        f"  Active video backend: {backend}"
    )
    lines.append("")
    lines.append(backend_pill)

    section("Video", [
        ("HiggsField (Key ID + Secret)", data["video"]["higgsfield_native"],
         "set HIGGSFIELD_API_KEY_ID and HIGGSFIELD_API_KEY_SECRET"),
        ("Replicate (fallback)", data["video"]["replicate_fallback"],
         "set REPLICATE_API_TOKEN"),
    ])

    section("Voice", [
        ("ElevenLabs", data["voice"]["elevenlabs"], "set ELEVENLABS_API_KEY"),
    ])

    section("Captions", [
        ("OpenAI (GPT-4o-mini)", data["captions"]["openai"], "set OPENAI_API_KEY"),
        ("Anthropic (Claude)", data["captions"]["anthropic"], "set ANTHROPIC_API_KEY"),
    ])

    section("Images", [
        ("Replicate (SDXL/Flux)", data["images"]["replicate"], "set REPLICATE_API_TOKEN"),
        ("OpenAI (DALL-E 3)", data["images"]["openai"], "set OPENAI_API_KEY"),
    ])

    section("Platform tokens", [
        ("Facebook", data["platforms"]["facebook"], "see docs/meta-survival-guide.md"),
        ("Instagram", data["platforms"]["instagram"], "see docs/meta-survival-guide.md"),
        ("Threads", data["platforms"]["threads"], "OAuth flow in /onboarding"),
        ("LinkedIn", data["platforms"]["linkedin"], "OAuth flow in /onboarding"),
        ("WhatsApp", data["platforms"]["whatsapp"], "Meta Business Suite"),
        ("TikTok", data["platforms"]["tiktok"], "see docs/api-setup-guide.md"),
    ])

    # Summary
    all_flags = []
    for section_name, section_data in data.items():
        if section_name == "video" and isinstance(section_data, dict):
            all_flags.append(section_data["higgsfield_native"] or section_data["replicate_fallback"])
        elif isinstance(section_data, dict):
            for v in section_data.values():
                if isinstance(v, bool):
                    all_flags.append(v)
    total = len(all_flags)
    ready = sum(1 for f in all_flags if f)
    summary = f"\n{ready}/{total} services configured"
    if color:
        c = GREEN if ready >= total * 0.6 else (YELLOW if ready > 0 else RED)
        summary = f"\n{c}{ready}/{total}{RESET} services configured"
    lines.append(summary)
    lines.append(
        f"{DIM}Edit ~/.social-auto-engine/tokens.env or .env to add keys, then re-run this check.{RESET}"
        if color else
        "Edit ~/.social-auto-engine/tokens.env or .env to add keys, then re-run this check."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    color = _supports_color()
    print(render(collect(), color=color))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
