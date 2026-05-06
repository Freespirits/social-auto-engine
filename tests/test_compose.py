"""HTTP-level tests for the compose endpoint and the broadcast group flow.

These tests do not exercise any real social-platform API. The publish
dispatch is mocked via env vars so the dashboard never tries to call out.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from dashboard import app as dash_app
from dashboard import db


client = TestClient(dash_app.app)


def _post_form(path: str, body: str):
    return client.post(
        path,
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_compose_single_platform_legacy_creates_one_row():
    r = _post_form("/compose", "message=hello&platform=facebook")
    assert r.status_code == 200

    singles, groups = db.list_pending_grouped()
    assert len(singles) == 1
    assert singles[0]["platform"] == "facebook"
    assert singles[0]["group_id"] is None
    assert not groups


def test_compose_broadcast_two_platforms_creates_one_group_of_two():
    r = _post_form(
        "/compose",
        "message=cross+post&platforms=facebook&platforms=linkedin",
    )
    assert r.status_code == 200

    singles, groups = db.list_pending_grouped()
    assert not singles
    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert {p["platform"] for p in groups[0]} == {"facebook", "linkedin"}
    # Both rows share the same group_id
    gids = {p["group_id"] for p in groups[0]}
    assert len(gids) == 1


def test_compose_rejects_whatsapp_combined_with_broadcast():
    r = _post_form(
        "/compose",
        "message=mix&platforms=whatsapp&platforms=facebook&recipient=%2B9725",
    )
    assert r.status_code == 400


def test_compose_rejects_empty_message():
    r = _post_form("/compose", "platforms=facebook")
    assert r.status_code == 400


def test_compose_rejects_instagram_without_image():
    r = _post_form("/compose", "message=hi&platforms=instagram")
    assert r.status_code == 400


def test_compose_rejects_unknown_platform():
    r = _post_form("/compose", "message=hi&platforms=myspace")
    assert r.status_code == 400


def test_reject_group_marks_all_rows_rejected():
    _post_form(
        "/compose",
        "message=reject+me&platforms=facebook&platforms=linkedin",
    )
    singles, groups = db.list_pending_grouped()
    gid = groups[0][0]["group_id"]

    r = client.post(f"/reject-group/{gid}")
    assert r.status_code == 200

    rows = db.list_group(gid)
    assert all(r["status"] == "rejected" for r in rows)


def test_reject_group_404_when_group_missing():
    r = client.post("/reject-group/nonexistent-uuid")
    assert r.status_code == 404
