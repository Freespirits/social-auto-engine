"""Threads API adapter.

Threads uses its own API at graph.threads.net (NOT the Facebook Graph API).
It has its own OAuth 2.0 token flow and user IDs.

Publishing is a two-step container flow (same pattern as Instagram):
    1. POST /{threads_user_id}/threads         -> returns container_id
    2. POST /{threads_user_id}/threads_publish  -> publishes the container

Unlike Instagram, Threads supports text-only posts.

Rate limits: 250 posts per 24-hour rolling window.

Permissions required: threads_basic, threads_content_publish
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests


THREADS_API_BASE = "https://graph.threads.net/v1.0"
THREADS_AUTH_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"


class ThreadsAPI:
    """Thin wrapper around the Threads API.

    Uses a Threads-specific user access token (separate from Facebook).
    Obtain one via the OAuth flow or the exchange_code() helper.
    """

    def __init__(self):
        self.access_token = os.getenv("THREADS_ACCESS_TOKEN")
        self.app_id = os.getenv("THREADS_APP_ID")
        self.app_secret = os.getenv("THREADS_APP_SECRET")
        self._user_id: str | None = os.getenv("THREADS_USER_ID")

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a request to the Threads API."""
        url = f"{THREADS_API_BASE}/{endpoint}"
        if params is None:
            params = {}
        params["access_token"] = self.access_token

        r = requests.request(method, url, params=params, data=data)
        result = r.json()
        if r.status_code != 200:
            error_msg = result.get("error", {}).get("message", str(result))
            raise RuntimeError(f"Threads API error: {error_msg}")
        return result

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def get_auth_url(self, redirect_uri: str, scopes: str = "threads_basic,threads_content_publish") -> str:
        """Return the URL the user should visit to authorise the app.

        After authorising, Threads redirects to redirect_uri with a ?code= param.
        Pass that code to exchange_code().
        """
        return (
            f"{THREADS_AUTH_URL}"
            f"?client_id={self.app_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&response_type=code"
        )

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorisation code for a short-lived access token (~1 hour)."""
        r = requests.post(
            THREADS_TOKEN_URL,
            data={
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        result = r.json()
        if "access_token" in result:
            self.access_token = result["access_token"]
            self._user_id = str(result.get("user_id", ""))
        return result

    def exchange_long_lived_token(self) -> dict[str, Any]:
        """Swap a short-lived token for a long-lived one (~60 days)."""
        r = requests.get(
            f"{THREADS_API_BASE}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": self.app_secret,
                "access_token": self.access_token,
            },
        )
        result = r.json()
        if "access_token" in result:
            self.access_token = result["access_token"]
        return result

    def refresh_token(self) -> dict[str, Any]:
        """Refresh a valid, non-expired long-lived token (extends to 60 more days)."""
        r = requests.get(
            f"{THREADS_API_BASE}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": self.access_token,
            },
        )
        result = r.json()
        if "access_token" in result:
            self.access_token = result["access_token"]
        return result

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict[str, Any]:
        """Return the Threads profile for the authenticated user."""
        if not self.access_token:
            return {"connected": False, "error": "THREADS_ACCESS_TOKEN not set"}
        try:
            fields = "id,username,name,threads_profile_picture_url,threads_biography"
            result = self._request("GET", "me", {"fields": fields})
            self._user_id = result.get("id")
            return {"connected": True, **result}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    @property
    def user_id(self) -> str:
        """Lazy-load the Threads user ID."""
        if self._user_id is None:
            info = self.get_account_info()
            if not info.get("connected"):
                raise RuntimeError(info.get("error", "Threads not connected"))
        return self._user_id  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_text(self, text: str, reply_control: str | None = None) -> dict[str, Any]:
        """Publish a text-only post to Threads.

        reply_control: 'everyone' | 'accounts_you_follow' | 'mentioned_only'
        """
        uid = self.user_id

        # Step 1: create container
        params: dict[str, Any] = {"media_type": "TEXT", "text": text}
        if reply_control:
            params["reply_control"] = reply_control
        container = self._request("POST", f"{uid}/threads", params)
        container_id = container.get("id")

        # Step 2: publish
        publish_result = self._request(
            "POST", f"{uid}/threads_publish", {"creation_id": container_id}
        )
        return {"success": True, "id": publish_result.get("id"), "container_id": container_id}

    def publish_image(self, image_url: str, text: str = "") -> dict[str, Any]:
        """Publish an image post to Threads.

        image_url must be publicly accessible.
        """
        uid = self.user_id

        params: dict[str, Any] = {"media_type": "IMAGE", "image_url": image_url}
        if text:
            params["text"] = text
        container = self._request("POST", f"{uid}/threads", params)
        container_id = container.get("id")

        publish_result = self._request(
            "POST", f"{uid}/threads_publish", {"creation_id": container_id}
        )
        return {"success": True, "id": publish_result.get("id"), "container_id": container_id}

    def publish_video(self, video_url: str, text: str = "") -> dict[str, Any]:
        """Publish a video post to Threads. Video must be publicly hosted.

        Videos require processing time, so we poll the container status.
        """
        uid = self.user_id

        params: dict[str, Any] = {"media_type": "VIDEO", "video_url": video_url}
        if text:
            params["text"] = text
        container = self._request("POST", f"{uid}/threads", params)
        container_id = container.get("id")

        # Poll for video processing
        for _ in range(30):
            status = self._container_status(container_id)
            if status == "FINISHED":
                break
            if status in {"ERROR", "EXPIRED"}:
                return {"success": False, "error": f"Container status: {status}", "container_id": container_id}
            time.sleep(2)

        publish_result = self._request(
            "POST", f"{uid}/threads_publish", {"creation_id": container_id}
        )
        return {"success": True, "id": publish_result.get("id"), "container_id": container_id}

    def _container_status(self, container_id: str) -> str:
        """Check the processing status of a media container."""
        result = self._request("GET", container_id, {"fields": "status"})
        return result.get("status", "UNKNOWN")

    # ------------------------------------------------------------------
    # Insights & metadata
    # ------------------------------------------------------------------

    def get_recent_threads(self, limit: int = 10) -> dict[str, Any]:
        """Fetch recent threads posted by the authenticated user."""
        uid = self.user_id
        fields = "id,media_type,text,timestamp,permalink,is_quote_post"
        return self._request("GET", f"{uid}/threads", {"fields": fields, "limit": limit})

    def get_thread_permalink(self, thread_id: str) -> dict[str, Any]:
        """Get the permalink for a specific thread."""
        return self._request("GET", thread_id, {"fields": "id,permalink"})

    def get_thread_insights(self, thread_id: str) -> dict[str, Any]:
        """Get engagement metrics for a specific thread.

        Available metrics: views, likes, replies, reposts, quotes.
        """
        return self._request(
            "GET",
            f"{thread_id}/insights",
            {"metric": "views,likes,replies,reposts,quotes"},
        )

    def delete_thread(self, thread_id: str) -> dict[str, Any]:
        """Delete a thread. Rate limited to 100 deletions per 24 hours."""
        return self._request("DELETE", thread_id)
