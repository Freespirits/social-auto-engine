import os
from pathlib import Path
from typing import Any

from facebook_api import FacebookAPI
from instagram_api import InstagramAPI
from whatsapp_api import WhatsAppAPI
from threads_api import ThreadsAPI
from linkedin_api import LinkedInAPI
from tiktok_api import TikTokAPI
from youtube_api import YouTubeAPI


class Manager:
    def __init__(self):
        self.api = FacebookAPI()
        self.ig = InstagramAPI()
        self.wa = WhatsAppAPI()
        self.threads = ThreadsAPI()
        self.linkedin = LinkedInAPI()
        self.tiktok = TikTokAPI()
        self.youtube = YouTubeAPI()

    def refresh_facebook_token(self, short_lived_user_token: str) -> str:
        """Refresh the Facebook Page access token from a short-lived user token.

        Reads `META_APP_ID`, `META_APP_SECRET`, and `FACEBOOK_PAGE_ID` from
        the environment. Exchanges `short_lived_user_token` for a long-lived
        user token, derives the Page access token via `/me/accounts`, writes
        the new token back to `.env`, and returns it.

        The dashboard can call this on a 401 response by surfacing a form
        that asks the user to paste a fresh Graph API Explorer token.
        """
        from scripts.refresh_token import (
            TokenRefreshError,
            refresh_page_token,
            write_token_to_env,
        )

        app_id = os.environ.get("META_APP_ID")
        app_secret = os.environ.get("META_APP_SECRET")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        missing = [
            name
            for name, value in (
                ("META_APP_ID", app_id),
                ("META_APP_SECRET", app_secret),
                ("FACEBOOK_PAGE_ID", page_id),
            )
            if not value
        ]
        if missing:
            raise TokenRefreshError(
                f"Missing required env vars: {', '.join(missing)}"
            )

        page_token = refresh_page_token(
            short_lived_user_token, app_id, app_secret, page_id
        )
        write_token_to_env(Path.cwd() / ".env", page_token)
        return page_token

    def post_to_facebook(self, message: str) -> dict[str, Any]:
        return self.api.post_message(message)

    # --- Instagram passthroughs (used by the dashboard) ---
    def get_instagram_account_info(self) -> dict[str, Any]:
        return self.ig.get_account_info()

    def post_to_instagram(self, image_url: str, caption: str = "") -> dict[str, Any]:
        return self.ig.publish_image(image_url, caption)

    def post_reel_to_instagram(self, video_url: str, caption: str = "") -> dict[str, Any]:
        return self.ig.publish_reel(video_url, caption)

    def get_instagram_media(self, limit: int = 10) -> dict[str, Any]:
        return self.ig.get_recent_media(limit)

    # --- Threads passthroughs ---
    def get_threads_account_info(self) -> dict[str, Any]:
        return self.threads.get_account_info()

    def post_text_to_threads(self, text: str, reply_control: str | None = None) -> dict[str, Any]:
        return self.threads.publish_text(text, reply_control)

    def post_image_to_threads(self, image_url: str, text: str = "") -> dict[str, Any]:
        return self.threads.publish_image(image_url, text)

    def post_video_to_threads(self, video_url: str, text: str = "") -> dict[str, Any]:
        return self.threads.publish_video(video_url, text)

    def get_recent_threads(self, limit: int = 10) -> dict[str, Any]:
        return self.threads.get_recent_threads(limit)

    def get_thread_insights(self, thread_id: str) -> dict[str, Any]:
        return self.threads.get_thread_insights(thread_id)

    def delete_thread(self, thread_id: str) -> dict[str, Any]:
        return self.threads.delete_thread(thread_id)

    # --- WhatsApp passthroughs ---
    def get_whatsapp_account_info(self) -> dict[str, Any]:
        return self.wa.get_account_info()

    def list_whatsapp_templates(self) -> list[dict[str, Any]]:
        return self.wa.list_templates()

    def send_whatsapp_template(self, to: str, template_name: str = "hello_world", language: str = "en_US") -> dict[str, Any]:
        return self.wa.send_template(to, template_name, language)

    def send_whatsapp_text(self, to: str, message: str) -> dict[str, Any]:
        return self.wa.send_text(to, message)

    def reply_to_comment(self, post_id: str, comment_id: str, message: str) -> dict[str, Any]:
        return self.api.reply_to_comment(comment_id, message)

    def get_page_posts(self) -> dict[str, Any]:
        return self.api.get_posts()

    def get_post_comments(self, post_id: str) -> dict[str, Any]:
        return self.api.get_comments(post_id)

    def delete_post(self, post_id: str) -> dict[str, Any]:
        return self.api.delete_post(post_id)

    def post_image_to_facebook(self, image_url: str, caption: str) -> dict[str, Any]:
        return self.api.post_image_to_facebook(image_url, caption)

    def send_dm_to_user(self, user_id: str, message: str) -> dict[str, Any]:
        return self.api.send_dm_to_user(user_id, message)

    def update_post(self, post_id: str, new_message: str) -> dict[str, Any]:
        return self.api.update_post(post_id, new_message)

    def schedule_post(self, message: str, publish_time: int) -> dict[str, Any]:
        return self.api.schedule_post(message, publish_time)

    def get_page_fan_count(self) -> int:
        return self.api.get_page_fan_count()

    def get_post_share_count(self, post_id: str) -> int:
        return self.api.get_post_share_count(post_id)

    def bulk_delete_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Delete multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.delete_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def bulk_hide_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Hide multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.hide_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def bulk_unhide_comments(self, comment_ids: list[str]) -> list[dict[str, Any]]:
        """Unhide multiple comments and return their results."""
        results = []
        for cid in comment_ids:
            res = self.api.unhide_comment(cid)
            results.append({"comment_id": cid, "result": res})
        return results

    def get_comment_replies(self, comment_id: str) -> dict[str, Any]:
        return self.api.get_comment_replies(comment_id)

    def get_post_permalink(self, post_id: str) -> dict[str, Any]:
        return self.api.get_post_permalink(post_id)

    def get_scheduled_posts(self) -> dict[str, Any]:
        return self.api.get_scheduled_posts()

    def get_page_info(self) -> dict[str, Any]:
        return self.api.get_page_info()

    _REACTION_METRICS = {
        "like": "post_reactions_like_total",
        "love": "post_reactions_love_total",
        "wow": "post_reactions_wow_total",
        "haha": "post_reactions_haha_total",
        "sorry": "post_reactions_sorry_total",
        "anger": "post_reactions_anger_total",
    }
    _IMPRESSION_METRICS = {
        "total": "post_impressions",
        "unique": "post_impressions_unique",
        "paid": "post_impressions_paid",
        "organic": "post_impressions_organic",
    }

    def get_post_engagement(self, post_id: str) -> dict[str, Any]:
        """Single-call engagement summary: reactions, comments, shares, permalink, impressions.

        Insight metrics Meta has deprecated degrade to null with a note in
        "deprecated_metrics" instead of failing the whole call. Each metric
        is fetched individually so one bad metric can't take down the rest.
        A failure on the underlying post lookup itself (bad post_id, expired
        token) short-circuits and returns {"error": ...} so
        mcp_support.envelope can rewrap it as a hard failure.
        """
        comments = self.api.get_comments(post_id)
        if "error" in comments:
            return {"error": comments["error"]}
        permalink = self.api.get_post_permalink(post_id)
        if "error" in permalink:
            return {"error": permalink["error"]}

        reactions, reaction_notes = self._bulk_metric_values(post_id, self._REACTION_METRICS)
        impressions, impression_notes = self._bulk_metric_values(post_id, self._IMPRESSION_METRICS)

        return {
            "reactions": reactions,
            "comment_count": len(comments.get("data", [])),
            "share_count": self.get_post_share_count(post_id),
            "permalink_url": permalink.get("permalink_url"),
            "impressions": impressions,
            "deprecated_metrics": reaction_notes + impression_notes,
        }

    def _bulk_metric_values(
        self, post_id: str, metric_map: dict[str, str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Fetch each metric individually so one deprecated metric doesn't fail the rest."""
        values: dict[str, Any] = {}
        deprecated: list[str] = []
        for label, metric in metric_map.items():
            raw = self.api.get_insights(post_id, metric)
            if "error" in raw:
                values[label] = None
                deprecated.append(metric)
                continue
            data = raw.get("data", [{}])
            values[label] = data[0].get("values", [{}])[0].get("value") if data else None
        return values, deprecated

    # --- LinkedIn passthroughs ---
    def get_linkedin_profile(self) -> dict[str, Any]:
        return self.linkedin.get_profile()

    def post_to_linkedin(self, message: str, image_url: str | None = None, article_url: str | None = None) -> dict[str, Any]:
        if image_url:
            return self.linkedin.post_image(image_url, message)
        if article_url:
            return self.linkedin.post_article(article_url, message)
        return self.linkedin.post_text(message)

    def post_image_to_linkedin(self, image_url: str, text: str = "") -> dict[str, Any]:
        return self.linkedin.post_image(image_url, text)

    def post_article_to_linkedin(self, article_url: str, text: str = "") -> dict[str, Any]:
        return self.linkedin.post_article(article_url, text)

    def delete_linkedin_post(self, post_id: str) -> dict[str, Any]:
        return self.linkedin.delete_post(post_id)

    # --- TikTok passthroughs ---
    def get_tiktok_profile(self) -> dict[str, Any]:
        return self.tiktok.get_profile()

    def post_to_tiktok(
        self,
        video_url: str | None = None,
        video_path: str | None = None,
    ) -> dict[str, Any]:
        """Push a video to the user's TikTok inbox / drafts.

        The user finalises and publishes from the TikTok app itself.
        This is the inbox-upload tier; direct publishing requires the
        video.publish scope and full app review.
        """
        return self.tiktok.upload_to_inbox(video_url=video_url, video_path=video_path)

    def get_tiktok_publish_status(self, publish_id: str) -> dict[str, Any]:
        return self.tiktok.get_publish_status(publish_id)

    # --- YouTube passthroughs ---
    def get_youtube_channel_info(self) -> dict[str, Any]:
        return self.youtube.get_channel_info()

    def post_to_youtube(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy_status: str = "private",
    ) -> dict[str, Any]:
        """Upload a local video to the authenticated user's channel.

        Defaults privacy_status='private'. The user can switch to public
        from the dashboard once they have reviewed the upload.
        """
        return self.youtube.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
        )

    def delete_youtube_video(self, video_id: str) -> dict[str, Any]:
        return self.youtube.delete_video(video_id)
