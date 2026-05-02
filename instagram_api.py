"""Instagram Graph API adapter.

Instagram Business uses the Facebook Graph API. The IG Business Account ID
is reached via the connected Facebook Page (`instagram_business_account` edge).

Publishing is a two-step container flow:
    1. POST /{ig_user_id}/media         → returns container_id
    2. POST /{ig_user_id}/media_publish → publishes the container

Text-only posts are not supported on Instagram. Posts must include an image
or video. For Reels, use a video URL plus media_type=REELS.
"""
from __future__ import annotations

import os
from typing import Any

import requests

from config import GRAPH_API_BASE_URL, GRAPH_API_VERSION


class InstagramAPI:
    """Thin wrapper around the Instagram Graph API.

    Uses the Facebook Page Access Token. The Page must have a connected
    Instagram Business Account.
    """

    def __init__(self):
        self.access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        self.page_id = os.getenv("FACEBOOK_PAGE_ID")
        self.base_url = GRAPH_API_BASE_URL
        self._ig_user_id: str | None = None
        self._ig_username: str | None = None

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict[str, Any]:
        """Return the Instagram Business Account linked to the FB Page."""
        params = {
            "access_token": self.access_token,
            "fields": "instagram_business_account{id,username,name,profile_picture_url,followers_count,media_count,biography,website}",
        }
        r = requests.get(f"{self.base_url}/{self.page_id}", params=params)
        data = r.json()
        if r.status_code != 200:
            return {"connected": False, "error": data.get("error", {}).get("message", "Unknown error")}

        ig = data.get("instagram_business_account")
        if not ig:
            return {
                "connected": False,
                "error": "No Instagram Business Account is linked to this Facebook Page. "
                         "Link one in Meta Business Suite → Settings → Instagram.",
            }

        self._ig_user_id = ig.get("id")
        self._ig_username = ig.get("username")
        return {"connected": True, **ig}

    @property
    def ig_user_id(self) -> str:
        """Lazy-load the Instagram Business Account ID."""
        if self._ig_user_id is None:
            info = self.get_account_info()
            if not info.get("connected"):
                raise RuntimeError(info.get("error", "Instagram not connected"))
        return self._ig_user_id  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_image(self, image_url: str, caption: str = "") -> dict[str, Any]:
        """Publish a single image to Instagram.

        image_url must be publicly accessible (Meta fetches it server-side).
        """
        ig_id = self.ig_user_id

        # Step 1: create container
        params = {
            "access_token": self.access_token,
            "image_url": image_url,
            "caption": caption,
        }
        r = requests.post(f"{self.base_url}/{ig_id}/media", params=params)
        if r.status_code != 200:
            return {"success": False, "error": r.json()}
        container_id = r.json().get("id")

        # Step 2: publish container
        publish_params = {"access_token": self.access_token, "creation_id": container_id}
        r2 = requests.post(f"{self.base_url}/{ig_id}/media_publish", params=publish_params)
        if r2.status_code != 200:
            return {"success": False, "error": r2.json(), "container_id": container_id}
        return {"success": True, "id": r2.json().get("id"), "container_id": container_id}

    def publish_reel(self, video_url: str, caption: str = "") -> dict[str, Any]:
        """Publish a Reel to Instagram. Video must be publicly hosted."""
        ig_id = self.ig_user_id
        params = {
            "access_token": self.access_token,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        }
        r = requests.post(f"{self.base_url}/{ig_id}/media", params=params)
        if r.status_code != 200:
            return {"success": False, "error": r.json()}
        container_id = r.json().get("id")

        # Reels require waiting for processing — poll status
        import time
        for _ in range(30):
            status = self._container_status(container_id)
            if status == "FINISHED":
                break
            if status in {"ERROR", "EXPIRED"}:
                return {"success": False, "error": f"Container status: {status}", "container_id": container_id}
            time.sleep(2)

        publish_params = {"access_token": self.access_token, "creation_id": container_id}
        r2 = requests.post(f"{self.base_url}/{ig_id}/media_publish", params=publish_params)
        if r2.status_code != 200:
            return {"success": False, "error": r2.json(), "container_id": container_id}
        return {"success": True, "id": r2.json().get("id"), "container_id": container_id}

    def _container_status(self, container_id: str) -> str:
        params = {"access_token": self.access_token, "fields": "status_code"}
        r = requests.get(f"{self.base_url}/{container_id}", params=params)
        return r.json().get("status_code", "UNKNOWN")

    # ------------------------------------------------------------------
    # Insights & metadata
    # ------------------------------------------------------------------

    def get_recent_media(self, limit: int = 10) -> dict[str, Any]:
        """Recent posts on the Instagram account."""
        ig_id = self.ig_user_id
        params = {
            "access_token": self.access_token,
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count",
            "limit": limit,
        }
        r = requests.get(f"{self.base_url}/{ig_id}/media", params=params)
        return r.json()

    def get_media_permalink(self, media_id: str) -> dict[str, Any]:
        params = {"access_token": self.access_token, "fields": "id,permalink"}
        r = requests.get(f"{self.base_url}/{media_id}", params=params)
        return r.json()
