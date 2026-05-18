"""Interactive first-run setup CLI for SocialBlast AI.

Run with: ``python -m dashboard.setup``

Prompts for the most important API keys, writes them to
``~/.social-auto-engine/tokens.env``, then runs the health check.

Existing values in tokens.env are shown and preserved unless the user
overrides them. No secrets are echoed back to the terminal after entry.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


TOKENS_PATH = Path.home() / ".social-auto-engine" / "tokens.env"


PROMPTS = [
    {
        "key": "HIGGSFIELD_API_KEY_ID",
        "label": "HiggsField API Key ID",
        "hint": "Get a pair at https://higgsfield.ai. Unlocks Veo 3.1, Kling 3.0, Seedance, etc.",
        "secret": False,
    },
    {
        "key": "HIGGSFIELD_API_KEY_SECRET",
        "label": "HiggsField API Key Secret",
        "hint": "The secret half of the key pair above.",
        "secret": True,
    },
    {
        "key": "ELEVENLABS_API_KEY",
        "label": "ElevenLabs API key",
        "hint": "https://elevenlabs.io/app/settings/api-keys. Voice cloning + multilingual TTS.",
        "secret": True,
    },
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API key",
        "hint": "Optional. Premium captions via GPT-4o-mini. Templates work without it.",
        "secret": True,
    },
    {
        "key": "REPLICATE_API_TOKEN",
        "label": "Replicate API token",
        "hint": "Fallback video backend when HiggsField is not set. Also images (SDXL/Flux).",
        "secret": True,
    },
]


def _load_existing(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _save(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# SocialBlast AI tokens — written by `python -m dashboard.setup`",
             "# Edit by hand if you prefer. Keep this file out of git.", ""]
    for k, v in values.items():
        if not v:
            continue
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 5) + value[-3:]


def _prompt(label: str, hint: str, current: str, *, secret: bool, non_interactive: bool) -> str:
    if non_interactive:
        return current
    print()
    print(f"  {label}")
    print(f"  {hint}")
    if current:
        print(f"  Currently set to: {_mask(current)}")
        action = input("  Press Enter to keep, or paste a new value: ").strip()
        return action or current
    return input("  Enter value (or press Enter to skip): ").strip()


def run(non_interactive: bool = False) -> int:
    print("SocialBlast AI. First-run setup.")
    print(f"Writing to: {TOKENS_PATH}")
    existing = _load_existing(TOKENS_PATH)

    values = dict(existing)  # Start with what's already there
    for prompt in PROMPTS:
        key = prompt["key"]
        current = existing.get(key, "")
        new_val = _prompt(
            prompt["label"],
            prompt["hint"],
            current,
            secret=prompt["secret"],
            non_interactive=non_interactive,
        )
        if new_val:
            values[key] = new_val
        elif key in values and not current:
            values.pop(key, None)

    _save(TOKENS_PATH, values)
    print()
    print(f"Saved {len([v for v in values.values() if v])} value(s) to {TOKENS_PATH}")

    # Run health check immediately so the user sees the result
    print("\nRunning health check...")
    try:
        from dashboard import health
        for k, v in values.items():
            if v:
                os.environ[k] = v
        print(health.render(health.collect(), color=False))
    except Exception as exc:
        print(f"Health check skipped: {exc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SocialBlast AI first-run setup")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for input. Just save current state and run health.",
    )
    args = parser.parse_args()
    return run(non_interactive=args.non_interactive)


if __name__ == "__main__":
    raise SystemExit(main())
