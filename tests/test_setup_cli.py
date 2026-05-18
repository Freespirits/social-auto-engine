"""Tests for the interactive setup CLI (dashboard/setup.py)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def isolated_tokens(monkeypatch, tmp_path):
    """Redirect TOKENS_PATH so tests can't touch the real ~/.social-auto-engine/tokens.env."""
    fake = tmp_path / "tokens.env"
    from dashboard import setup as setup_mod

    monkeypatch.setattr(setup_mod, "TOKENS_PATH", fake)
    return fake


# ---------------------------------------------------------------------------
# File round-trip
# ---------------------------------------------------------------------------

class TestLoadSave:
    def test_load_missing_returns_empty(self, isolated_tokens):
        from dashboard import setup
        assert setup._load_existing(isolated_tokens) == {}

    def test_save_then_load_round_trip(self, isolated_tokens):
        from dashboard import setup
        setup._save(isolated_tokens, {"FOO": "bar", "BAZ": "quux"})
        loaded = setup._load_existing(isolated_tokens)
        assert loaded == {"FOO": "bar", "BAZ": "quux"}

    def test_save_skips_empty_values(self, isolated_tokens):
        from dashboard import setup
        setup._save(isolated_tokens, {"FOO": "bar", "EMPTY": ""})
        loaded = setup._load_existing(isolated_tokens)
        assert loaded == {"FOO": "bar"}
        assert "EMPTY" not in loaded

    def test_save_preserves_comments_header(self, isolated_tokens):
        from dashboard import setup
        setup._save(isolated_tokens, {"FOO": "bar"})
        text = isolated_tokens.read_text(encoding="utf-8")
        assert text.startswith("# ")
        assert "dashboard.setup" in text

    def test_load_ignores_comments_and_blank_lines(self, isolated_tokens):
        isolated_tokens.write_text(
            "# top comment\n"
            "\n"
            "FOO=bar\n"
            "# inline comment\n"
            "BAZ=quux\n",
            encoding="utf-8",
        )
        from dashboard import setup
        assert setup._load_existing(isolated_tokens) == {"FOO": "bar", "BAZ": "quux"}


# ---------------------------------------------------------------------------
# Mask helper — no secrets in logs
# ---------------------------------------------------------------------------

class TestMask:
    def test_mask_empty(self):
        from dashboard import setup
        assert setup._mask("") == "(empty)"

    def test_mask_short(self):
        from dashboard import setup
        assert setup._mask("abc") == "***"

    def test_mask_long_preserves_edges(self):
        from dashboard import setup
        out = setup._mask("sk-abc123def456ghi789")
        # First 2 + last 3 visible, middle masked
        assert out.startswith("sk")
        assert out.endswith("789")
        assert "abc123def" not in out
        assert "*" in out


# ---------------------------------------------------------------------------
# Non-interactive run
# ---------------------------------------------------------------------------

class TestNonInteractiveRun:
    def test_run_with_no_existing_file(self, isolated_tokens, capsys):
        from dashboard import setup
        rc = setup.run(non_interactive=True)
        assert rc == 0
        # No tokens.env at all -> still completes without error
        out = capsys.readouterr().out
        assert "SocialBlast AI" in out
        assert "Health check" in out or "health check" in out.lower()

    def test_run_preserves_existing_values(self, isolated_tokens, capsys):
        from dashboard import setup
        setup._save(isolated_tokens, {"OPENAI_API_KEY": "pre-existing"})
        rc = setup.run(non_interactive=True)
        assert rc == 0
        loaded = setup._load_existing(isolated_tokens)
        assert loaded["OPENAI_API_KEY"] == "pre-existing"

    def test_run_does_not_print_raw_secret(self, isolated_tokens, capsys):
        from dashboard import setup
        secret_val = "sk-VERY-SECRET-DO-NOT-LEAK-1234567890"
        setup._save(isolated_tokens, {"OPENAI_API_KEY": secret_val})
        setup.run(non_interactive=True)
        out = capsys.readouterr().out
        assert secret_val not in out


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_python_module_setup_non_interactive_runs(self, tmp_path, monkeypatch):
        """`python -m dashboard.setup --non-interactive` exits cleanly."""
        # Use a fake HOME so the real ~/.social-auto-engine/tokens.env is never touched.
        env = {
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            "NO_COLOR": "1",
            "PATH": "",
        }
        result = subprocess.run(
            [sys.executable, "-m", "dashboard.setup", "--non-interactive"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "SocialBlast AI" in result.stdout
