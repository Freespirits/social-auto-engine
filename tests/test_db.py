"""Persistence tests for the dashboard's SQLite layer."""
from __future__ import annotations

from dashboard import db


def test_init_db_creates_post_table_with_group_id():
    """The migration must add group_id to existing schemas and ship it on new ones."""
    with db.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(post)")}
    assert "group_id" in cols
    assert "platform" in cols
    assert "status" in cols


def test_create_post_returns_id_and_persists_row():
    pid = db.create_post(
        message="hello world",
        account_name="Hack-Tech",
        platform="facebook",
    )
    assert isinstance(pid, int) and pid > 0

    row = db.get_post(pid)
    assert row is not None
    assert row["message"] == "hello world"
    assert row["platform"] == "facebook"
    assert row["status"] == "pending"
    assert row["group_id"] is None  # legacy single-platform posts have no group


def test_create_broadcast_creates_n_rows_with_shared_group_id():
    targets = [
        {"platform": "facebook", "account_name": "Hack-Tech"},
        {"platform": "instagram", "account_name": "Instagram"},
        {"platform": "linkedin", "account_name": "LinkedIn"},
    ]
    result = db.create_broadcast(
        message="multi-platform launch",
        targets=targets,
        image_url="https://example.com/x.jpg",
    )
    assert "group_id" in result and result["group_id"]
    assert len(result["post_ids"]) == 3

    rows = db.list_group(result["group_id"])
    assert len(rows) == 3
    assert {r["platform"] for r in rows} == {"facebook", "instagram", "linkedin"}
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["group_id"] == result["group_id"] for r in rows)
    assert all(r["image_url"] == "https://example.com/x.jpg" for r in rows)


def test_create_broadcast_rejects_empty_targets():
    import pytest

    with pytest.raises(ValueError):
        db.create_broadcast(message="x", targets=[])


def test_list_pending_grouped_separates_singles_and_groups():
    db.create_post(message="single fb", platform="facebook")
    db.create_broadcast(
        message="broadcast",
        targets=[
            {"platform": "facebook", "account_name": "Hack-Tech"},
            {"platform": "linkedin", "account_name": "LinkedIn"},
        ],
    )
    db.create_post(message="single ig", platform="instagram", image_url="https://x/y")

    singles, groups = db.list_pending_grouped()
    assert len(singles) == 2
    assert {s["platform"] for s in singles} == {"facebook", "instagram"}
    assert all(s["group_id"] is None for s in singles)

    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert {p["platform"] for p in groups[0]} == {"facebook", "linkedin"}


def test_mark_published_and_mark_failed_set_decision_timestamps():
    pid = db.create_post(message="x", platform="facebook")
    db.mark_published(pid, platform_post_id="fb_123", permalink_url="https://fb/1")
    row = db.get_post(pid)
    assert row["status"] == "published"
    assert row["platform_post_id"] == "fb_123"
    assert row["permalink_url"] == "https://fb/1"
    assert row["published_at"] is not None
    assert row["decided_at"] is not None

    pid2 = db.create_post(message="y", platform="facebook")
    db.mark_failed(pid2, error_message="token expired")
    row2 = db.get_post(pid2)
    assert row2["status"] == "failed"
    assert row2["error_message"] == "token expired"
    assert row2["decided_at"] is not None
