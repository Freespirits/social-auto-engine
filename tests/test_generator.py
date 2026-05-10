"""Tests for content.generator.

Provider-specific helpers are not exercised against real SDKs. We mock
the entries in `_PROVIDERS` so the tests run without anthropic, openai,
or google-generativeai installed.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from content.generator import (
    GeneratorError,
    _build_prompt,
    _read_voice_profile,
    generate_post,
)


def test_read_voice_profile_returns_empty_when_no_files(tmp_path: Path):
    assert _read_voice_profile(tmp_path) == ""


def test_read_voice_profile_reads_about_me_only(tmp_path: Path):
    (tmp_path / "about-me.md").write_text("I am a baker in Lisbon.", encoding="utf-8")
    assert _read_voice_profile(tmp_path) == "I am a baker in Lisbon."


def test_read_voice_profile_reads_voice_only(tmp_path: Path):
    (tmp_path / "voice.md").write_text("Wry, short sentences.", encoding="utf-8")
    assert _read_voice_profile(tmp_path) == "Wry, short sentences."


def test_read_voice_profile_concatenates_both_files_in_order(tmp_path: Path):
    (tmp_path / "about-me.md").write_text("Baker.", encoding="utf-8")
    (tmp_path / "voice.md").write_text("Wry.", encoding="utf-8")
    result = _read_voice_profile(tmp_path)
    assert result == "Baker.\n\nWry."


def test_build_prompt_omits_voice_section_when_profile_empty():
    prompt = _build_prompt("Sourdough rise tips", "")
    assert "Voice profile:" not in prompt
    assert "Sourdough rise tips" in prompt
    assert "Return only the post text" in prompt


def test_build_prompt_includes_voice_section_when_profile_set():
    prompt = _build_prompt("Sourdough rise tips", "Wry baker.")
    assert "Voice profile:\nWry baker." in prompt
    assert "Topic: Sourdough rise tips" in prompt


def test_generate_post_raises_on_empty_topic():
    with pytest.raises(GeneratorError, match="topic must not be empty"):
        generate_post("")


def test_generate_post_raises_on_whitespace_topic():
    with pytest.raises(GeneratorError, match="topic must not be empty"):
        generate_post("   \n   ")


def test_generate_post_raises_on_unknown_provider():
    with pytest.raises(GeneratorError, match="Unknown AI provider"):
        generate_post("topic", provider="nonsense")


def test_generate_post_uses_provider_argument_over_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.chdir(tmp_path)
    with patch.dict(
        "content.generator._PROVIDERS",
        {"claude": lambda prompt: "claude:" + prompt[:20]},
    ):
        result = generate_post("Sourdough", provider="claude")
    assert result.startswith("claude:")


def test_generate_post_falls_back_to_env_when_no_provider_arg(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.chdir(tmp_path)
    with patch.dict(
        "content.generator._PROVIDERS",
        {"openai": lambda prompt: "openai:" + prompt[:20]},
    ):
        result = generate_post("Sourdough")
    assert result.startswith("openai:")


def test_generate_post_defaults_to_claude_when_env_unset(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch.dict(
        "content.generator._PROVIDERS",
        {"claude": lambda prompt: "claude-default"},
    ):
        result = generate_post("Sourdough")
    assert result == "claude-default"


def test_generate_post_normalises_provider_case(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    with patch.dict(
        "content.generator._PROVIDERS",
        {"claude": lambda prompt: "ok"},
    ):
        assert generate_post("topic", provider="CLAUDE") == "ok"


def test_generate_post_passes_prompt_with_voice_profile(tmp_path: Path):
    (tmp_path / "voice.md").write_text("Terse.", encoding="utf-8")
    captured: dict[str, str] = {}

    def fake_provider(prompt: str) -> str:
        captured["prompt"] = prompt
        return "draft"

    with patch.dict("content.generator._PROVIDERS", {"claude": fake_provider}):
        generate_post("Sourdough", provider="claude", project_root=tmp_path)

    assert "Voice profile:\nTerse." in captured["prompt"]
    assert "Topic: Sourdough" in captured["prompt"]


def test_generate_post_explicit_voice_profile_overrides_files(tmp_path: Path):
    (tmp_path / "voice.md").write_text("FILE_VOICE", encoding="utf-8")
    captured: dict[str, str] = {}

    def fake_provider(prompt: str) -> str:
        captured["prompt"] = prompt
        return "draft"

    with patch.dict("content.generator._PROVIDERS", {"claude": fake_provider}):
        generate_post(
            "Sourdough",
            voice_profile="EXPLICIT",
            provider="claude",
            project_root=tmp_path,
        )

    assert "EXPLICIT" in captured["prompt"]
    assert "FILE_VOICE" not in captured["prompt"]


def test_generate_post_explicit_empty_voice_profile_suppresses_section(tmp_path: Path):
    (tmp_path / "voice.md").write_text("FILE_VOICE", encoding="utf-8")
    captured: dict[str, str] = {}

    def fake_provider(prompt: str) -> str:
        captured["prompt"] = prompt
        return "draft"

    with patch.dict("content.generator._PROVIDERS", {"claude": fake_provider}):
        generate_post(
            "Sourdough",
            voice_profile="",
            provider="claude",
            project_root=tmp_path,
        )

    assert "Voice profile:" not in captured["prompt"]
    assert "FILE_VOICE" not in captured["prompt"]


def test_generate_post_wraps_provider_exception_in_generator_error():
    def boom(prompt: str) -> str:
        raise RuntimeError("upstream 500")

    with patch.dict("content.generator._PROVIDERS", {"claude": boom}):
        with pytest.raises(GeneratorError, match="claude generation failed: upstream 500"):
            generate_post("topic", provider="claude")


def test_generate_post_wraps_missing_sdk_with_install_hint():
    def missing_sdk(prompt: str) -> str:
        raise ImportError("No module named 'anthropic'")

    with patch.dict("content.generator._PROVIDERS", {"claude": missing_sdk}):
        with pytest.raises(GeneratorError, match="pip install claude"):
            generate_post("topic", provider="claude")


def test_generate_post_passes_through_generator_error_unchanged():
    def already_clean(prompt: str) -> str:
        raise GeneratorError("GOOGLE_AI_API_KEY is not set in the environment")

    with patch.dict("content.generator._PROVIDERS", {"gemini": already_clean}):
        with pytest.raises(GeneratorError, match="GOOGLE_AI_API_KEY is not set"):
            generate_post("topic", provider="gemini")
