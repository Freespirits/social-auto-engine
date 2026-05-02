"""WhatsApp Business Cloud API adapter.

Unlike Facebook/Instagram, WhatsApp is a *messaging* channel — you send to
a specific phone number, not a public feed. Two modes:

1. **Template messages** — pre-approved by Meta, can be sent at any time
   to any opted-in recipient. The default place to start.
2. **Free-form messages** — only allowed within the 24-hour customer service
   window AFTER the user first messages your business.

The platform stores messages in the same approval queue as posts; the
approve action calls one of the send_* methods below.
"""
from __future__ import annotations

import os
from typing import Any

import requests

from config import GRAPH_API_BASE_URL


class WhatsAppAPI:
    """Thin wrapper around the WhatsApp Business Cloud API."""

    def __init__(self):
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
        self.base_url = GRAPH_API_BASE_URL

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict[str, Any]:
        """Return verified name, display phone, quality, messaging-limit tier."""
        if not self.configured:
            return {"connected": False, "error": "WhatsApp env vars missing"}
        params = {
            "access_token": self.access_token,
            "fields": "verified_name,display_phone_number,quality_rating,code_verification_status,messaging_limit_tier",
        }
        r = requests.get(f"{self.base_url}/{self.phone_number_id}", params=params)
        data = r.json()
        if r.status_code != 200:
            return {"connected": False, "error": data.get("error", {}).get("message", "Unknown error")}
        return {"connected": True, **data}

    def list_templates(self, limit: int = 50) -> list[dict[str, Any]]:
        """Approved message templates we can send any time."""
        if not self.waba_id:
            return []
        params = {
            "access_token": self.access_token,
            "fields": "name,status,language,category,components",
            "limit": limit,
        }
        r = requests.get(f"{self.base_url}/{self.waba_id}/message_templates", params=params)
        if r.status_code != 200:
            return []
        return r.json().get("data", [])

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_template(
        self,
        to: str,
        template_name: str = "hello_world",
        language: str = "en_US",
        components: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send an approved template message. Always allowed (with opt-in)."""
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": _normalise(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            body["template"]["components"] = components
        return self._post(body)

    def send_text(self, to: str, message: str) -> dict[str, Any]:
        """Send a plain-text message. Only works within the 24-hour service window
        after the recipient has messaged you. Outside the window, use a template."""
        body = {
            "messaging_product": "whatsapp",
            "to": _normalise(to),
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }
        return self._post(body)

    def send_image(self, to: str, image_url: str, caption: str = "") -> dict[str, Any]:
        body = {
            "messaging_product": "whatsapp",
            "to": _normalise(to),
            "type": "image",
            "image": {"link": image_url, **({"caption": caption} if caption else {})},
        }
        return self._post(body)

    def send_document(self, to: str, doc_url: str, caption: str = "", filename: str = "") -> dict[str, Any]:
        body = {
            "messaging_product": "whatsapp",
            "to": _normalise(to),
            "type": "document",
            "document": {
                "link": doc_url,
                **({"caption": caption} if caption else {}),
                **({"filename": filename} if filename else {}),
            },
        }
        return self._post(body)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return {"success": False, "error": "WhatsApp not configured"}
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        r = requests.post(url, headers=headers, json=body)
        data = r.json()
        if r.status_code != 200:
            return {"success": False, "error": data}
        msg_id = (data.get("messages") or [{}])[0].get("id")
        return {"success": True, "id": msg_id, "raw": data}


def _normalise(phone: str) -> str:
    """E.164 without leading + and no spaces, e.g. '972526139179'."""
    return "".join(c for c in str(phone) if c.isdigit())
