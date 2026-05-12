"""Render-level tests for the compose UI's AI Sparkles button.

These confirm the index template parses and includes the elements the
generate flow depends on. We do not run any JavaScript, so the actual
Sparkles click flow is exercised end-to-end only by manual smoke.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(isolated_dashboard_db, monkeypatch):
    from dashboard import db
    db.set_setting("onboarding.completed", "true")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    from dashboard import app as dash_app
    return TestClient(dash_app.app)


def test_index_renders_sparkles_button(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "toggleBroadcastAi" in response.text
    assert "AI draft" in response.text


def test_index_renders_ai_prompt_row(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="bAiRow"' in response.text
    assert 'id="bAiTopic"' in response.text
    assert 'id="bAiGenBtn"' in response.text
    assert "What is this post about?" in response.text


def test_index_wires_generate_handler_to_button(client):
    response = client.get("/")
    assert "generateBroadcastDraft" in response.text
    assert "/generate" in response.text
