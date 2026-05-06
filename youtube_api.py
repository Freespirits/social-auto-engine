"""YouTube Data API v3 adapter.

YouTube uses Google OAuth 2.0 and the Google APIs at googleapis.com.
This adapter implements:

  - 3-legged OAuth (auth URL, code exchange, refresh)
  - Channel info read
  - Video upload via simple multipart (suitable for files up to ~128 MB,
    which covers virtually all social-media video lengths). Resumable
    upload is a follow-up if anyone hits the cap.

Permissions:
  - youtube.upload    (upload videos)
  - youtube.readonly  (read channel info, optional)

Quota cost:
  - videos.insert: 100 units per upload
  - Default daily quota: 10,000 units → 100 uploads/day per project
  - Increase via Google Cloud quota request when needed

Notes on Shorts:
  YouTube auto-detects Shorts based on aspect ratio (9:16) and duration
  (≤ 60 seconds). There is no separate "is_short" API flag. Pass a vertical
  video under 60 seconds and YouTube treats it as a Short.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


class YouTubeAPI:
    """Thin wrapper around the YouTube Data API v3."""

    def __init__(self):
        self.access_token = os.getenv("YOUTUBE_ACCESS_TOKEN")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def get_auth_url(
        self,
        redirect_uri: str,
        scopes: str = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        state: str = "",
    ) -> str:
        """Return the URL the user should visit to authorise the app.

        access_type=offline + prompt=consent ensures we get a refresh_token
        on first authorisation, which we need because access_tokens expire
        in 1 hour.
        """
        params = {
            "client_id": self.client_id or "",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        from urllib.parse import urlencode

        return f"{YOUTUBE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an auth code for access + refresh tokens."""
        try:
            r = requests.post(
                YOUTUBE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"success": False, "error": str(exc)}

        try:
            result = r.json()
        except ValueError:
            return {"success": False, "error": f"Non-JSON response: {r.text[:200]}"}

        if "access_token" in result:
            self.access_token = result["access_token"]
        if "refresh_token" in result:
            self.refresh_token = result["refresh_token"]
        return result

    def refresh_access_token(self) -> dict[str, Any]:
        """Use the stored refresh_token to get a new access_token."""
        if not self.refresh_token:
            return {"success": False, "error": "No refresh_token available"}
        try:
            r = requests.post(
                YOUTUBE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"success": False, "error": str(exc)}

        try:
            result = r.json()
        except ValueError:
            return {"success": False, "error": f"Non-JSON response: {r.text[:200]}"}

        if "access_token" in result:
            self.access_token = result["access_token"]
        return result

    # ------------------------------------------------------------------
    # Channel info
    # ------------------------------------------------------------------

    def get_channel_info(self) -> dict[str, Any]:
        """Return basic info for the authenticated user's channel."""
        if not self.access_token:
            return {"connected": False, "error": "YOUTUBE_ACCESS_TOKEN not set"}
        try:
            r = requests.get(
                f"{YOUTUBE_API_BASE}/channels",
                params={"part": "snippet,statistics", "mine": "true"},
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"connected": False, "error": str(exc)}

        if r.status_code == 401:
            # Try a single refresh if we have a refresh token
            refreshed = self.refresh_access_token()
            if "access_token" in refreshed:
                return self.get_channel_info()
            return {"connected": False, "error": "401 Unauthorized (refresh failed)"}

        if r.status_code != 200:
            return {"connected": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}

        try:
            data = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response"}

        items = data.get("items") or []
        if not items:
            return {"connected": False, "error": "No channel for this account"}
        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        return {
            "connected": True,
            "id": item.get("id", ""),
            "name": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "thumbnail_url": (snippet.get("thumbnails") or {}).get("default", {}).get("url", ""),
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
            "view_count": int(stats.get("viewCount", 0)),
        }

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        privacy_status: str = "private",
        made_for_kids: bool = False,
    ) -> dict[str, Any]:
        """Upload a local video file to the authenticated user's channel.

        Defaults privacy_status to 'private'. The user can switch to
        'public' or 'unlisted' from the dashboard once they have reviewed
        the upload. This matches the project's no-silent-automation spine.

        category_id 22 = "People & Blogs", a safe default for social
        creator content. Other common values:
          - 24: Entertainment
          - 25: News & Politics
          - 27: Education
          - 28: Science & Technology

        For Shorts, supply a vertical video (9:16) under 60 seconds.
        YouTube auto-detects.
        """
        path = Path(video_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            return {"success": False, "error": f"Video file not found: {video_path}"}

        if not self.access_token:
            return {"success": False, "error": "YOUTUBE_ACCESS_TOKEN not set"}

        metadata = {
            "snippet": {
                "title": title[:100] or "Untitled",
                "description": description[:5000],
                "tags": (tags or [])[:30],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        # Multipart "related" body. Two parts: JSON metadata and the video bytes.
        # We hand-build because requests' multipart only does form-data, not "related".
        boundary = "----social_auto_engine_boundary"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        body += json.dumps(metadata).encode("utf-8") + b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b"Content-Type: video/*\r\n\r\n"
        with path.open("rb") as fh:
            body += fh.read()
        body += f"\r\n--{boundary}--\r\n".encode()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(body)),
        }

        try:
            r = requests.post(
                YOUTUBE_UPLOAD_URL,
                params={"part": "snippet,status", "uploadType": "multipart"},
                headers=headers,
                data=body,
                timeout=600,
            )
        except requests.RequestException as exc:
            return {"success": False, "error": str(exc)}

        if r.status_code == 401:
            refreshed = self.refresh_access_token()
            if "access_token" in refreshed:
                return self.upload_video(
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    category_id=category_id,
                    privacy_status=privacy_status,
                    made_for_kids=made_for_kids,
                )

        if r.status_code not in (200, 201):
            return {
                "success": False,
                "error": f"YouTube upload HTTP {r.status_code}: {r.text[:300]}",
            }

        try:
            data = r.json()
        except ValueError:
            return {"success": False, "error": f"Non-JSON response: {r.text[:200]}"}

        return {
            "success": True,
            "id": data.get("id", ""),
            "watch_url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
            "privacy_status": data.get("status", {}).get("privacyStatus", privacy_status),
        }

    def delete_video(self, video_id: str) -> dict[str, Any]:
        """Delete a video by ID."""
        if not self.access_token:
            return {"success": False, "error": "YOUTUBE_ACCESS_TOKEN not set"}
        try:
            r = requests.delete(
                f"{YOUTUBE_API_BASE}/videos",
                params={"id": video_id},
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"success": False, "error": str(exc)}

        if r.status_code in (200, 204):
            return {"success": True}
        return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
