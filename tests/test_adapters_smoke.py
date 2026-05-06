"""Adapter import / instantiation smoke tests.

These never call out to a real platform API. They confirm:
  - the modules import without errors
  - the classes can be instantiated with no env vars set
  - the safe-failure behaviour returns a connected=False dict, never crashes
"""
from __future__ import annotations

import pytest


def test_facebook_adapter_imports():
    from facebook_api import FacebookAPI

    api = FacebookAPI()
    assert api is not None


def test_instagram_adapter_imports():
    from instagram_api import InstagramAPI

    api = InstagramAPI()
    assert api is not None


def test_whatsapp_adapter_imports():
    from whatsapp_api import WhatsAppAPI

    api = WhatsAppAPI()
    assert api is not None


def test_threads_adapter_imports():
    from threads_api import ThreadsAPI

    api = ThreadsAPI()
    assert api is not None


def test_linkedin_adapter_imports_and_safe_failure():
    from linkedin_api import LinkedInAPI

    api = LinkedInAPI()
    info = api.get_profile()
    assert info["connected"] is False
    assert "error" in info


def test_tiktok_adapter_imports_and_safe_failure():
    from tiktok_api import TikTokAPI

    api = TikTokAPI()
    info = api.get_profile()
    assert info["connected"] is False
    assert "error" in info


def test_youtube_adapter_imports_and_safe_failure():
    from youtube_api import YouTubeAPI

    api = YouTubeAPI()
    info = api.get_channel_info()
    assert info["connected"] is False
    assert "error" in info


def test_manager_wires_every_adapter():
    """Manager exposes one attribute per adapter, all instantiable together."""
    from manager import Manager

    m = Manager()
    assert hasattr(m, "api")
    assert hasattr(m, "ig")
    assert hasattr(m, "wa")
    assert hasattr(m, "threads")
    assert hasattr(m, "linkedin")
    assert hasattr(m, "tiktok")
    assert hasattr(m, "youtube")


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("get_linkedin_profile", {}),
        ("get_tiktok_profile", {}),
        ("get_youtube_channel_info", {}),
    ],
)
def test_manager_safe_failure_methods(method, kwargs):
    """Each safe-failure read returns a connected=False dict, no exception."""
    from manager import Manager

    m = Manager()
    fn = getattr(m, method)
    result = fn(**kwargs)
    assert isinstance(result, dict)
    assert result.get("connected") is False
