"""Lightweight i18n for the dashboard.

Translations live in dashboard/locales/<code>.json as flat key-value maps.
The active locale is stored in the settings table and defaults to "en".
Templates access translations via the `t()` function injected into the
Jinja2 global context.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent / "locales"

_cache: dict[str, dict[str, str]] = {}

SUPPORTED_LOCALES = [
    {"code": "en", "label": "English", "dir": "ltr"},
    {"code": "he", "label": "עברית", "dir": "rtl"},
    {"code": "es", "label": "Español", "dir": "ltr"},
    {"code": "pt", "label": "Português", "dir": "ltr"},
]


def _load(locale: str) -> dict[str, str]:
    if locale in _cache:
        return _cache[locale]
    path = LOCALES_DIR / f"{locale}.json"
    if not path.is_file():
        _cache[locale] = {}
        return _cache[locale]
    with open(path, encoding="utf-8") as f:
        _cache[locale] = json.load(f)
    return _cache[locale]


def translate(key: str, locale: str = "en", **kwargs: Any) -> str:
    strings = _load(locale)
    fallback = _load("en") if locale != "en" else strings
    text = strings.get(key) or fallback.get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def locale_dir(locale: str) -> str:
    for loc in SUPPORTED_LOCALES:
        if loc["code"] == locale:
            return loc["dir"]
    return "ltr"


def reload_cache() -> None:
    _cache.clear()
