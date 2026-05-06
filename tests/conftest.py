"""Shared pytest fixtures.

We isolate every test from the user's real `~/.social-auto-engine/` directory
by pointing the dashboard at a temporary database before any module imports.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


# Ensure the project root is importable as a package
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_dashboard_db(monkeypatch, tmp_path):
    """Redirect the dashboard's SQLite db to a tmp file for each test."""
    db_dir = tmp_path / ".social-auto-engine"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / "dashboard.db"

    # Patch the module-level path constants the dashboard's db uses
    from dashboard import db as dash_db

    monkeypatch.setattr(dash_db, "DB_DIR", db_dir)
    monkeypatch.setattr(dash_db, "DB_PATH", db_path)

    # Force the schema in the new db
    dash_db.init_db()
    yield db_path
