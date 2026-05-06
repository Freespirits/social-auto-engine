"""LinkedIn API adapter.

LinkedIn uses its own REST API at api.linkedin.com (NOT the Meta Graph API).
It uses 3-legged OAuth 2.0 for authentication.

Publishing uses the UGC Post API (v2) or the newer Posts API:
    POST https://api.linkedin.com/v2/ugcPosts

The author URN is derived from the authenticated user's profile via
    GET https://api.linkedin.com/v2/userinfo

Permissions required: openid, profile, email, w_member_social

Rate limits: 100 posts per day per member.
"""
from __future__ import annotations

import os
from typing import Any

import requests


LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


class LinkedInAPI:
    """Thin wrapper around the LinkedIn API v2.

    Uses a LinkedIn OAuth 2.0 access token. Obtain one via the 3-legged
    OAuth flow or by providing LINKEDIN_ACCESS_TOKEN in .env.
    """

    def __init__(self):
        self.access_token = os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.client_id = os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
        self._person_urn: str | None = None

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
        """Send a request to the LinkedIn API."""
        url = (
            endpoint
            if endpoint.startswith("https://")
            else f"{LINKEDIN_API_BASE}/{endpoint}"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        try:
            r = requests.request(
                method, url, headers=headers, params=params, json=json_body, timeout=30
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"LinkedIn API request failed: {exc}") from exc

        if r.status_code == 204:
            return {"success": True}

        try:
            result = r.json()
        except ValueError:
            raise RuntimeError(
                f"LinkedIn API returned non-JSON (HTTP {r.status_code}): {r.text[:300]}"
            )

        if r.status_code not in (200, 201):
            error_msg = result.get("message", str(result))
            raise RuntimeError(f"LinkedIn API error (HTTP {r.status_code}): {error_msg}")
        return result

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def get_auth_url(
        self,
        redirect_uri: str,
        scopes: str = "openid profile email w_member_social",
    ) -> str:
        """Return the URL the user should visit to authorise the app.

        After authorising, LinkedIn redirects to redirect_uri with a ?code= param.
        Pass that code to exchange_code().
        """
        return (
            f"{LINKEDIN_AUTH_URL}"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
        )

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorisation code for an access token (~60 days)."""
        try:
            r = requests.post(
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
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

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token using a refresh token.

        LinkedIn refresh tokens are available only for apps approved for
        the 'r_basicprofile' or marketing APIs. Returns the new token pair.
        """
        try:
            r = requests.post(
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
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
    # Connection check / profile
    # ------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        """Return the LinkedIn profile for the authenticated user.

        Uses the OpenID Connect userinfo endpoint which returns sub, name,
        email, and picture.
        """
        if not self.access_token:
            return {"connected": False, "error": "LINKEDIN_ACCESS_TOKEN not set"}
        try:
            result = self._request("GET", "https://api.linkedin.com/v2/userinfo")
            # The 'sub' field is the member's person ID
            person_id = result.get("sub", "")
            self._person_urn = f"urn:li:person:{person_id}"
            return {
                "connected": True,
                "id": person_id,
                "name": result.get("name", ""),
                "email": result.get("email", ""),
                "picture": result.get("picture", ""),
                "given_name": result.get("given_name", ""),
                "family_name": result.get("family_name", ""),
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    @property
    def person_urn(self) -> str:
        """Lazy-load the LinkedIn person URN (urn:li:person:xxx)."""
        if self._person_urn is None:
            info = self.get_profile()
            if not info.get("connected"):
                raise RuntimeError(info.get("error", "LinkedIn not connected"))
        return self._person_urn  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def post_text(self, text: str) -> dict[str, Any]:
        """Publish a text-only post to the user's LinkedIn feed.

        Uses the UGC Post API (v2).
        """
        author = self.person_urn
        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        try:
            result = self._request("POST", "ugcPosts", json_body=payload)
            post_id = result.get("id", "")
            return {"success": True, "id": post_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def post_image(self, image_url: str, text: str = "") -> dict[str, Any]:
        """Share an image post with optional text on LinkedIn.

        LinkedIn requires images to be uploaded via their image upload API.
        For simplicity this method uses an external image URL as a thumbnail
        via the article share type, which supports external URLs directly.
        For native image uploads, use the register/upload flow instead.
        """
        author = self.person_urn
        media_entry: dict[str, Any] = {
            "status": "READY",
            "originalUrl": image_url,
            "description": {"text": text or "Shared image"},
        }
        if text:
            media_entry["title"] = {"text": text[:200]}

        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [media_entry],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        try:
            result = self._request("POST", "ugcPosts", json_body=payload)
            post_id = result.get("id", "")
            return {"success": True, "id": post_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def post_article(self, article_url: str, text: str = "") -> dict[str, Any]:
        """Share a link/article on LinkedIn with optional commentary text.

        LinkedIn will automatically unfurl the link and display a preview card.
        """
        author = self.person_urn
        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "originalUrl": article_url,
                        }
                    ],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        try:
            result = self._request("POST", "ugcPosts", json_body=payload)
            post_id = result.get("id", "")
            return {"success": True, "id": post_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_post(self, post_id: str) -> dict[str, Any]:
        """Fetch a single UGC post by its ID (URN-encoded)."""
        try:
            return self._request("GET", f"ugcPosts/{post_id}")
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_post(self, post_id: str) -> dict[str, Any]:
        """Delete a UGC post by its ID.

        post_id should be the full URN, e.g. urn:li:ugcPost:12345
        """
        try:
            return self._request("DELETE", f"ugcPosts/{post_id}")
        except Exception as exc:
            return {"success": False, "error": str(exc)}
