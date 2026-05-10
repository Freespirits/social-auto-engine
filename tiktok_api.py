"""TikTok Content Posting API adapter.

TikTok has its own OAuth 2.0 flow via tiktok.com and its own API host at
open.tiktokapis.com. The Content Posting API has two tiers:

  - Inbox upload (video.upload scope): pushes the video to the user's
    TikTok drafts. The user opens TikTok, edits if they want, and taps
    publish. This tier is approvable without the heavy review process.
  - Direct post  (video.publish scope): publishes immediately. Requires
    full app review and is harder to obtain. Saved for a later iteration.

This adapter ships with the inbox-upload flow.

Permissions:
  - user.info.basic   (read profile basics)
  - user.info.profile (read full profile)
  - video.upload      (inbox upload)
  - video.list        (read user's videos, optional)

Rate limits:
  - Inbox-upload init: 6 requests per minute per user access token
  - Maximum 5 pending drafts in any 24-hour rolling window

Note: PULL_FROM_URL requires the source domain to be pre-verified in the
TikTok developer portal. For users without a verified domain, supply a
local file path and the adapter will use the chunked FILE_UPLOAD flow.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB


class TikTokAPI:
    """Thin wrapper around the TikTok Content Posting API (inbox tier)."""

    def __init__(self):
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        self.client_key = os.getenv("TIKTOK_CLIENT_KEY")
        self.client_secret = os.getenv("TIKTOK_CLIENT_SECRET")

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = (
            endpoint
            if endpoint.startswith("https://")
            else f"{TIKTOK_API_BASE}/{endpoint}"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            r = requests.request(
                method, url, headers=headers, params=params, json=json_body, timeout=30
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"TikTok API request failed: {exc}") from exc

        try:
            result = r.json()
        except ValueError:
            raise RuntimeError(
                f"TikTok API returned non-JSON (HTTP {r.status_code}): {r.text[:300]}"
            )

        # TikTok returns errors inside an "error" envelope even on 200s
        err = result.get("error") or {}
        code = err.get("code", "ok")
        if r.status_code not in (200, 201) or (code and code != "ok"):
            raise RuntimeError(
                f"TikTok API error (HTTP {r.status_code}, code {code}): "
                f"{err.get('message', str(result))}"
            )
        return result

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def get_auth_url(
        self,
        redirect_uri: str,
        scopes: str = "user.info.basic,user.info.profile,video.upload,video.list",
        state: str = "",
    ) -> str:
        """Return the URL the user should visit to authorise the app."""
        return (
            f"{TIKTOK_AUTH_URL}"
            f"?client_key={self.client_key}"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorisation code for an access token."""
        try:
            r = requests.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token using a refresh token."""
        try:
            r = requests.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
    # Profile
    # ------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        """Return the authenticated TikTok user's basic profile info.

        Only requests fields covered by the minimum required scope
        (`user.info.basic`). `username` needs `user.info.profile`,
        `follower_count` needs `user.info.stats`. Both are attempted
        as a separate enrichment call so a missing scope on either does
        not break the basic "connected/not connected" check.
        """
        if not self.access_token:
            return {"connected": False, "error": "TIKTOK_ACCESS_TOKEN not set"}

        try:
            result = self._request(
                "GET",
                "user/info/",
                params={"fields": "open_id,avatar_url,display_name"},
            )
            user = result.get("data", {}).get("user", {})
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

        # Optional enrichment, swallow any scope-related failure
        username = ""
        follower_count = 0
        try:
            enrich = self._request(
                "GET",
                "user/info/",
                params={"fields": "username,follower_count"},
            )
            enrich_user = enrich.get("data", {}).get("user", {})
            username = enrich_user.get("username", "")
            follower_count = enrich_user.get("follower_count", 0)
        except Exception:
            pass

        return {
            "connected": True,
            "id": user.get("open_id", ""),
            "name": user.get("display_name", ""),
            "username": username,
            "avatar_url": user.get("avatar_url", ""),
            "follower_count": follower_count,
        }

    # ------------------------------------------------------------------
    # Inbox upload
    # ------------------------------------------------------------------

    def upload_to_inbox(
        self,
        video_url: str | None = None,
        video_path: str | None = None,
    ) -> dict[str, Any]:
        """Push a video to the user's TikTok inbox / drafts.

        Pass either:
          - video_url: must be a publicly reachable URL on a domain that has
            been pre-verified in the TikTok developer portal.
          - video_path: a local file path. The adapter will read it and use
            the chunked FILE_UPLOAD flow.

        After this returns, the user opens the TikTok app, taps the inbox
        notification, and finalises the post themselves. We never publish
        without their final tap.
        """
        if not video_url and not video_path:
            return {"success": False, "error": "Pass either video_url or video_path"}
        if video_url and video_path:
            return {"success": False, "error": "Pass either video_url or video_path, not both"}

        if video_url:
            return self._init_pull_from_url(video_url)
        return self._init_and_upload_file(video_path)

    def _init_pull_from_url(self, video_url: str) -> dict[str, Any]:
        try:
            result = self._request(
                "POST",
                "post/publish/inbox/video/init/",
                json_body={
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": video_url,
                    }
                },
            )
            publish_id = result.get("data", {}).get("publish_id", "")
            return {"success": True, "id": publish_id, "mode": "pull_from_url"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _init_and_upload_file(self, video_path: str) -> dict[str, Any]:
        path = Path(video_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            return {"success": False, "error": f"Video file not found: {video_path}"}

        size = path.stat().st_size
        if size == 0:
            return {"success": False, "error": "Video file is empty (0 bytes)"}
        chunk_size = min(UPLOAD_CHUNK_SIZE, size)
        total_chunks = max(1, (size + chunk_size - 1) // chunk_size)

        try:
            init = self._request(
                "POST",
                "post/publish/inbox/video/init/",
                json_body={
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": size,
                        "chunk_size": chunk_size,
                        "total_chunk_count": total_chunks,
                    }
                },
            )
        except Exception as exc:
            return {"success": False, "error": f"Init failed: {exc}"}

        publish_id = init.get("data", {}).get("publish_id", "")
        upload_url = init.get("data", {}).get("upload_url", "")
        if not upload_url:
            return {"success": False, "error": "No upload_url returned from init"}

        try:
            with path.open("rb") as fh:
                offset = 0
                while offset < size:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    last = offset + len(chunk) - 1
                    headers = {
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{last}/{size}",
                    }
                    r = requests.put(upload_url, data=chunk, headers=headers, timeout=120)
                    if r.status_code not in (200, 201, 206):
                        return {
                            "success": False,
                            "error": f"Chunk upload HTTP {r.status_code}: {r.text[:200]}",
                        }
                    offset += len(chunk)
        except Exception as exc:
            return {"success": False, "error": f"Chunk upload failed: {exc}"}

        return {"success": True, "id": publish_id, "mode": "file_upload"}

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    def get_publish_status(self, publish_id: str) -> dict[str, Any]:
        """Poll the publish status of a previously-initiated upload."""
        try:
            result = self._request(
                "POST",
                "post/publish/status/fetch/",
                json_body={"publish_id": publish_id},
            )
            return result.get("data", {})
        except Exception as exc:
            return {"success": False, "error": str(exc)}
