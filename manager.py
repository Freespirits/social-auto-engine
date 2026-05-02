from typing import Any
from facebook_api import FacebookAPI
from instagram_api import InstagramAPI
from whatsapp_api import WhatsAppAPI
from threads_api import ThreadsAPI


class Manager:
    def __init__(self):
        self.api = FacebookAPI()
        self.ig = InstagramAPI()
        self.wa = WhatsAppAPI()
        self.threads = ThreadsAPI()

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

    def delete_comment(self, comment_id: str) -> dict[str, Any]:
        return self.api.delete_comment(comment_id)

    def hide_comment(self, comment_id: str) -> dict[str, Any]:
        return self.api.hide_comment(comment_id)

    def unhide_comment(self, comment_id: str) -> dict[str, Any]:
        return self.api.unhide_comment(comment_id)

    def delete_comment_from_post(self, post_id: str, comment_id: str) -> dict[str, Any]:
        return self.api.delete_comment(comment_id)

    def filter_negative_comments(self, comments: dict[str, Any]) -> list[dict[str, Any]]:
        keywords = ["bad", "terrible", "awful", "hate", "dislike", "problem", "issue"]
        return [c for c in comments.get("data", []) if any(k in c.get("message", "").lower() for k in keywords)]

    def get_number_of_comments(self, post_id: str) -> int:
        return len(self.api.get_comments(post_id).get("data", []))

    def get_number_of_likes(self, post_id: str) -> int:
        return self.api._request("GET", post_id, {"fields": "likes.summary(true)"}).get("likes", {}).get("summary", {}).get("total_count", 0)

    def get_post_insights(self, post_id: str) -> dict[str, Any]:
        metrics = [
            "post_impressions", "post_impressions_unique", "post_impressions_paid",
            "post_impressions_organic", "post_engaged_users", "post_clicks",
            "post_reactions_like_total", "post_reactions_love_total", "post_reactions_wow_total",
            "post_reactions_haha_total", "post_reactions_sorry_total", "post_reactions_anger_total",
        ]
        return self.api.get_bulk_insights(post_id, metrics)
    
    def get_post_impressions(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_impressions")

    def get_post_impressions_unique(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_impressions_unique")

    def get_post_impressions_paid(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_impressions_paid")

    def get_post_impressions_organic(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_impressions_organic")

    def get_post_engaged_users(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_engaged_users")

    def get_post_clicks(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_clicks")

    def get_post_reactions_like_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_like_total")

    def get_post_reactions_love_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_love_total")

    def get_post_reactions_wow_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_wow_total")

    def get_post_reactions_haha_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_haha_total")

    def get_post_reactions_sorry_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_sorry_total")

    def get_post_reactions_anger_total(self, post_id: str) -> dict[str, Any]:
        return self.api.get_insights(post_id, "post_reactions_anger_total")

    def get_post_top_commenters(self, post_id: str) -> list[dict[str, Any]]:
        comments = self.get_post_comments(post_id).get("data", [])
        counter = {}
        for comment in comments:
            user_id = comment.get("from", {}).get("id")
            if user_id:
                counter[user_id] = counter.get(user_id, 0) + 1
        return sorted([{"user_id": k, "count": v} for k, v in counter.items()], key=lambda x: x["count"], reverse=True)

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

    def get_post_reactions_breakdown(self, post_id: str) -> dict[str, Any]:
        """Return counts for all reaction types on a post."""
        metrics = [
            "post_reactions_like_total",
            "post_reactions_love_total",
            "post_reactions_wow_total",
            "post_reactions_haha_total",
            "post_reactions_sorry_total",
            "post_reactions_anger_total",
        ]
        raw = self.api.get_bulk_insights(post_id, metrics)
        results: dict[str, Any] = {}
        for item in raw.get("data", []):
            name = item.get("name")
            value = item.get("values", [{}])[0].get("value")
            results[name] = value
        return results

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
