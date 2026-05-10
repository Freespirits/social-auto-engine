"""Notion adapter: OAuth + page and database access.

Notion uses 3-legged OAuth for public integrations. Flow:

1. Redirect to ``https://api.notion.com/v1/oauth/authorize`` with
   ``client_id``, ``redirect_uri``, ``response_type=code``,
   ``owner=user`` and a state cookie.
2. User chooses pages and clicks Allow.
3. Notion redirects to the configured callback URL with ``code``.
4. Exchange the code at ``/v1/oauth/token`` using HTTP Basic auth
   (``client_id:client_secret``). The response contains
   ``access_token``, ``workspace_id``, ``workspace_name`` and
   ``bot_id``. Tokens do not expire.

For local development you can also paste an internal integration token
(``NOTION_TOKEN``) to skip OAuth.

API base: ``https://api.notion.com/v1``. The ``Notion-Version`` header
is required on every request. Update it when Notion ships breaking
changes.
"""

from __future__ import annotations

import os
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
NOTION_API_VERSION = "2022-06-28"


class NotionAPI:
    """Thin wrapper over the Notion REST API."""

    def __init__(self) -> None:
        self.access_token = (
            os.getenv("NOTION_ACCESS_TOKEN")
            or os.getenv("NOTION_TOKEN")
            or ""
        )
        self.client_id = os.getenv("NOTION_CLIENT_ID", "")
        self.client_secret = os.getenv("NOTION_CLIENT_SECRET", "")

    # ------------------------------------------------------------------
    # OAuth helpers (used by dashboard/app.py /oauth/notion/* routes)
    # ------------------------------------------------------------------

    def build_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        from urllib.parse import urlencode

        return f"{NOTION_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if not (self.client_id and self.client_secret):
            return {"error": "NOTION_CLIENT_ID / NOTION_CLIENT_SECRET not set"}
        try:
            r = requests.post(
                NOTION_TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            return r.json()
        except ValueError:
            return {"error": "Non-JSON response from Notion token endpoint"}

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> requests.Response:
        url = f"{NOTION_API_BASE}/{endpoint}"
        try:
            return requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Notion request failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        if not self.access_token:
            return {"connected": False, "error": "NOTION_ACCESS_TOKEN not set"}
        try:
            r = self._request("GET", "users/me")
        except RuntimeError as exc:
            return {"connected": False, "error": str(exc)}
        if r.status_code == 401:
            return {"connected": False, "error": "Invalid Notion token"}
        if not r.ok:
            return {"connected": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"connected": False, "error": "Non-JSON response"}
        bot = payload.get("bot") or {}
        owner = bot.get("owner") or {}
        workspace_user = owner.get("user") or {}
        return {
            "connected": True,
            "name": payload.get("name", ""),
            "workspace": bot.get("workspace_name", ""),
            "owner_email": (workspace_user.get("person") or {}).get("email", ""),
        }

    # ------------------------------------------------------------------
    # Search and databases
    # ------------------------------------------------------------------

    def search(self, query: str = "", filter_type: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "page_size": 25}
        if filter_type in {"page", "database"}:
            body["filter"] = {"property": "object", "value": filter_type}
        try:
            r = self._request("POST", "search", json_body=body)
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
        try:
            return r.json()
        except ValueError:
            return {"error": "Non-JSON response"}

    def list_databases(self) -> list[dict[str, Any]]:
        result = self.search(filter_type="database")
        if "error" in result:
            return []
        items = []
        for entry in result.get("results", []):
            title_blocks = entry.get("title", []) or []
            title = "".join(t.get("plain_text", "") for t in title_blocks)
            items.append(
                {
                    "id": entry.get("id", ""),
                    "title": title or "Untitled",
                    "url": entry.get("url", ""),
                }
            )
        return items

    # ------------------------------------------------------------------
    # Push a post into a Notion database row
    # ------------------------------------------------------------------

    def push_post(
        self,
        database_id: str,
        title: str,
        body: str,
        *,
        platform: str = "",
        status: str = "Draft",
        scheduled_for: str | None = None,
    ) -> dict[str, Any]:
        """Create a page in ``database_id`` representing a post draft.

        The database must have at least a title property. Optional
        properties are written when present in the schema. Missing
        properties are silently ignored by Notion only when they are
        not required, so the database needs ``Title`` (title) and
        ideally ``Platform`` (select), ``Status`` (status or select),
        ``Scheduled`` (date).
        """
        if not (self.access_token and database_id and title):
            return {"error": "access_token, database_id, title all required"}
        properties: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": title[:200]}}]},
        }
        if platform:
            properties["Platform"] = {"select": {"name": platform}}
        if status:
            properties["Status"] = {"select": {"name": status}}
        if scheduled_for:
            properties["Scheduled"] = {"date": {"start": scheduled_for}}
        body_chunks = [body[i : i + 1900] for i in range(0, len(body), 1900)] or [""]
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            }
            for chunk in body_chunks
        ]
        request_body = {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": children,
        }
        try:
            r = self._request("POST", "pages", json_body=request_body)
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not r.ok:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        try:
            payload = r.json()
        except ValueError:
            return {"error": "Non-JSON response"}
        return {
            "id": payload.get("id", ""),
            "url": payload.get("url", ""),
        }
