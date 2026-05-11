"""SQLite persistence for the dashboard.

Single-file storage at ~/.social-auto-engine/dashboard.db. WAL mode for
concurrent reads from FastAPI workers + the MCP server.
"""
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
    permalink_url   TEXT,
    group_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_post_status ON post(status);
CREATE INDEX IF NOT EXISTS idx_post_created ON post(created_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
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
        if "scheduled_for" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN scheduled_for TEXT")
        if "group_id" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN group_id TEXT")
        if "video_url" not in cols:
            conn.execute("ALTER TABLE post ADD COLUMN video_url TEXT")
        # Always ensure the index exists (idempotent, runs after the column is present)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_post_group ON post(group_id)")
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
    video_url: str | None = None,
    recipient: str | None = None,
    template_name: str | None = None,
    group_id: str | None = None,
) -> int:
    """Insert a new pending post. Returns the post id."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO post (message, account_name, platform, image_url, video_url, "
            "recipient, template_name, status, group_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (message, account_name, platform, image_url, video_url, recipient, template_name, group_id),
        )
        conn.commit()
        return cur.lastrowid


def create_broadcast(
    message: str,
    targets: list[dict],
    image_url: str | None = None,
    video_url: str | None = None,
) -> dict:
    """Create N pending posts under one group_id, one per platform target.

    Each target dict carries: platform, account_name, optional message_override.
    Returns {"group_id": str, "post_ids": list[int]}.
    """
    import uuid

    if not targets:
        raise ValueError("Broadcast needs at least one target")
    group_id = str(uuid.uuid4())
    post_ids: list[int] = []
    with connect() as conn:
        for target in targets:
            text = target.get("message_override") or message
            cur = conn.execute(
                "INSERT INTO post (message, account_name, platform, image_url, video_url, "
                "status, group_id) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (
                    text,
                    target.get("account_name", target["platform"].title()),
                    target["platform"],
                    image_url,
                    video_url,
                    group_id,
                ),
            )
            post_ids.append(cur.lastrowid)
        conn.commit()
    return {"group_id": group_id, "post_ids": post_ids}


def list_group(group_id: str, status: str | None = None) -> list[dict]:
    """Return every post sharing a group_id, optionally filtered by status."""
    with connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM post WHERE group_id = ? AND status = ? "
                "ORDER BY id ASC",
                (group_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM post WHERE group_id = ? ORDER BY id ASC",
                (group_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def list_pending_grouped() -> tuple[list[dict], list[list[dict]]]:
    """Return (singles, groups) for the pending queue.

    singles: pending posts with NULL group_id, rendered individually.
    groups: list of platform-row lists, one entry per group_id, ordered newest first.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM post WHERE status = 'pending' "
            "ORDER BY created_at DESC"
        ).fetchall()
    singles: list[dict] = []
    grouped: dict[str, list[dict]] = {}
    group_order: list[str] = []
    for r in rows:
        d = dict(r)
        gid = d.get("group_id")
        if not gid:
            singles.append(d)
        else:
            if gid not in grouped:
                grouped[gid] = []
                group_order.append(gid)
            grouped[gid].append(d)
    return singles, [grouped[g] for g in group_order]


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


def list_scheduled(limit: int = 50):
    """Return all posts with status='scheduled', ordered by scheduled time."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM post WHERE status = 'scheduled' "
            "ORDER BY scheduled_for ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def calendar_posts(start_iso: str, end_iso: str):
    """Return all posts (any status) within a date range for the calendar view."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM post WHERE "
            "(scheduled_for BETWEEN ? AND ?) OR "
            "(published_at BETWEEN ? AND ?) OR "
            "(created_at BETWEEN ? AND ?) "
            "ORDER BY COALESCE(scheduled_for, published_at, created_at) ASC",
            (start_iso, end_iso, start_iso, end_iso, start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]


def stats():
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM post GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# Settings (key-value store for onboarding state and future config)
# ---------------------------------------------------------------------------
# ── Settings key-value store ───────────────────────────────────────────


def get_setting(key: str, default: str | None = None) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (key, value),
        )
        conn.commit()


def is_onboarded() -> bool:
    return get_setting("onboarding.completed") == "true"
