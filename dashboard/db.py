"""SQLite persistence for the dashboard.

Single-file storage at ~/.social-auto-engine/dashboard.db. WAL mode for
concurrent reads from FastAPI workers + the MCP server.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_DIR = Path.home() / ".social-auto-engine"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "dashboard.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS post (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL DEFAULT 'facebook',
    account_name    TEXT,
    message         TEXT NOT NULL,
    image_url       TEXT,
    recipient       TEXT,
    template_name   TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    platform_post_id TEXT,
    error_message   TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    decided_at      TEXT,
    published_at    TEXT,
    permalink_url   TEXT
);

CREATE INDEX IF NOT EXISTS idx_post_status ON post(status);
CREATE INDEX IF NOT EXISTS idx_post_created ON post(created_at DESC);
"""


def init_db():
    """Create tables if they don't exist. Safe to call repeatedly."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Lightweight migrations for existing dbs
        cols = {row[1] for row in conn.execute("PRAGMA table_info(post)")}
        if "image_url" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN image_url TEXT")
        if "recipient" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN recipient TEXT")
        if "template_name" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN template_name TEXT")
        conn.commit()


@contextmanager
def connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_post(
    message: str,
    account_name: str = "Hack-Tech",
    platform: str = "facebook",
    image_url: str | None = None,
    recipient: str | None = None,
    template_name: str | None = None,
) -> int:
    """Insert a new pending post. Returns the post id."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO post (message, account_name, platform, image_url, "
            "recipient, template_name, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (message, account_name, platform, image_url, recipient, template_name),
        )
        conn.commit()
        return cur.lastrowid


def get_post(post_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM post WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None


def list_posts(status: str | None = None, limit: int = 50):
    with connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM post WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM post ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def update_post(post_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [post_id]
    with connect() as conn:
        conn.execute(f"UPDATE post SET {sets} WHERE id = ?", values)
        conn.commit()


def reject_post(post_id: int):
    update_post(
        post_id,
        status="rejected",
        decided_at=_now(),
    )


def mark_published(post_id: int, platform_post_id: str, permalink_url: str | None = None):
    update_post(
        post_id,
        status="published",
        platform_post_id=platform_post_id,
        permalink_url=permalink_url,
        decided_at=_now(),
        published_at=_now(),
    )


def mark_failed(post_id: int, error_message: str):
    update_post(
        post_id,
        status="failed",
        error_message=error_message,
        decided_at=_now(),
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stats():
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM post GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}
