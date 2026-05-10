"""HTTP-level tests for the dashboard's POST /generate endpoint.

The actual provider call is mocked so the tests run without anthropic,
openai, or google-generativeai installed.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard import app as dash_app


def test_generate_returns_200_and_text_for_valid_topic():
    client = TestClient(dash_app.app)
    with patch("content.generator.generate_post", return_value="DRAFTED POST TEXT"):
        response = client.post("/generate", data={"topic": "Sourdough rise tips"})
    assert response.status_code == 200
    assert response.text == "DRAFTED POST TEXT"


def test_generate_returns_400_for_empty_topic():
    client = TestClient(dash_app.app)
    response = client.post("/generate", data={"topic": ""})
    assert response.status_code == 400


def test_generate_returns_400_for_whitespace_topic():
    client = TestClient(dash_app.app)
    response = client.post("/generate", data={"topic": "   \n  "})
    assert response.status_code == 400


def test_generate_returns_500_when_generator_raises():
    from content.generator import GeneratorError

    client = TestClient(dash_app.app)
    with patch(
        "content.generator.generate_post",
        side_effect=GeneratorError("upstream rejected the prompt"),
    ):
        response = client.post("/generate", data={"topic": "Sourdough"})
    assert response.status_code == 500
    assert "upstream rejected" in response.text


def test_generate_strips_whitespace_around_topic_before_calling_generator():
    client = TestClient(dash_app.app)
    with patch("content.generator.generate_post", return_value="ok") as mock_gen:
        response = client.post("/generate", data={"topic": "  Sourdough  \n"})
    assert response.status_code == 200
    args, kwargs = mock_gen.call_args
    assert args[0] == "Sourdough"
