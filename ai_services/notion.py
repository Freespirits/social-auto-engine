"""Notion adapter for syncing drafts to a Notion database."""
from __future__ import annotations

import os


class NotionError(RuntimeError):
    pass


class NotionAuthError(NotionError):
    pass


class NotionAdapter:
    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self) -> None:
        self.api_key = os.environ.get("NOTION_ACCESS_TOKEN", "")
        self.database_id = os.environ.get("NOTION_DATABASE_ID", "")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION,
        }

    def ping(self) -> bool:
        if not self.api_key:
            return False
        import urllib.request

        req = urllib.request.Request(
            f"{self.BASE_URL}/users/me",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_databases(self) -> list[dict]:
        if not self.api_key:
            raise NotionAuthError(
                "NOTION_ACCESS_TOKEN is not set. "
                "Create an integration at https://www.notion.so/my-integrations"
            )
        import urllib.request
        import json

        payload = json.dumps({
            "filter": {"property": "object", "value": "database"},
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/search",
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            return [
                {
                    "id": db["id"],
                    "title": self._extract_title(db),
                }
                for db in data.get("results", [])
            ]
        except Exception as exc:
            if "401" in str(exc) or "Unauthorized" in str(exc):
                raise NotionAuthError(
                    "Your NOTION_ACCESS_TOKEN is invalid or expired."
                )
            raise NotionError(f"Notion search failed: {exc}") from exc

    def sync_draft(
        self,
        title: str,
        body: str,
        *,
        platform: str = "",
        status: str = "Draft",
        database_id: str | None = None,
    ) -> dict:
        if not self.api_key:
            raise NotionAuthError(
                "NOTION_ACCESS_TOKEN is not set. "
                "Create an integration at https://www.notion.so/my-integrations"
            )
        db_id = database_id or self.database_id
        if not db_id:
            raise NotionError(
                "NOTION_DATABASE_ID is not set. "
                "Set it to the ID of the Notion database to sync to."
            )
        import urllib.request
        import json

        properties: dict = {
            "Name": {"title": [{"text": {"content": title}}]},
        }
        if platform:
            properties["Platform"] = {"select": {"name": platform}}
        if status:
            properties["Status"] = {"select": {"name": status}}

        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": body}}],
                },
            }
        ]

        payload = json.dumps({
            "parent": {"database_id": db_id},
            "properties": properties,
            "children": children,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}/pages",
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            return {"success": True, "page_id": data["id"], "url": data.get("url", "")}
        except Exception as exc:
            if "401" in str(exc) or "Unauthorized" in str(exc):
                raise NotionAuthError(
                    "Your NOTION_ACCESS_TOKEN is invalid or expired."
                )
            raise NotionError(f"Notion sync failed: {exc}") from exc

    @staticmethod
    def _extract_title(db: dict) -> str:
        title_parts = db.get("title", [])
        if title_parts:
            return title_parts[0].get("plain_text", "Untitled")
        return "Untitled"
