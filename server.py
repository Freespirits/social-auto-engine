from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

import mcp_support
from manager import Manager

mcp = FastMCP("FacebookMCP")
manager = Manager()

# Kept in sync by hand with dashboard.app.SUPPORTED_PLATFORMS, duplicated
# here so this module never has to import the FastAPI app just for one set.
KNOWN_PLATFORMS = {"facebook", "instagram", "whatsapp", "threads", "linkedin", "tiktok"}


def _require_facebook_config() -> dict[str, Any] | None:
    return mcp_support.require_env("FACEBOOK_PAGE_ID", "FACEBOOK_ACCESS_TOKEN")


# ---------------------------------------------------------------------------
# Pipeline and approval-queue tools (11), always registered.
#
# No tool in this section can approve or publish a post. Approval stays
# human-only in the dashboard (CLAUDE.md section 5).
# ---------------------------------------------------------------------------

@mcp.tool()
def socialblast_status() -> dict[str, Any]:
    """Report which AI backends and platforms are configured. No secrets exposed.

    Returns:
        Nested dict with booleans for video, voice, captions, images, platforms.
    """
    from ai_services.higgsfield import HiggsFieldAdapter

    def has(key: str) -> bool:
        return bool(os.environ.get(key, "").strip())

    def hf_configured() -> bool:
        if has("HF_API_KEY") and has("HF_API_SECRET"):
            return True
        combined = os.environ.get("HF_KEY", "").strip()
        if combined and ":" in combined:
            return True
        if has("HIGGSFIELD_API_KEY_ID") and has("HIGGSFIELD_API_KEY_SECRET"):
            return True
        return False

    higgsfield_backend = "none"
    try:
        higgsfield_backend = HiggsFieldAdapter().backend
    except Exception:
        pass

    return {
        "video": {
            "higgsfield_native": hf_configured(),
            "replicate_fallback": has("REPLICATE_API_TOKEN"),
            "active_backend": higgsfield_backend,
        },
        "voice": {"elevenlabs": has("ELEVENLABS_API_KEY")},
        "captions": {
            "openai": has("OPENAI_API_KEY"),
            "anthropic": has("ANTHROPIC_API_KEY"),
        },
        "images": {
            "replicate": has("REPLICATE_API_TOKEN"),
            "openai": has("OPENAI_API_KEY"),
        },
        "platforms": {
            "facebook": has("FACEBOOK_ACCESS_TOKEN") or has("FACEBOOK_PAGE_ACCESS_TOKEN"),
            "instagram": has("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
            "threads": has("THREADS_ACCESS_TOKEN"),
            "linkedin": has("LINKEDIN_ACCESS_TOKEN"),
            "whatsapp": has("WHATSAPP_ACCESS_TOKEN"),
            "tiktok": has("TIKTOK_ACCESS_TOKEN"),
        },
    }


@mcp.tool()
def socialblast_generate_campaign(
    business_description: str,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a 7-day social media campaign for a business.

    Creates 7 pending posts per platform in the approval queue. Uses OpenAI
    if available, falls back to hand-tuned premium templates otherwise.

    Args:
        business_description: One-sentence description (e.g. "Coffee shop in London")
        platforms: List of target platforms. Defaults to all five broadcast platforms.

    Returns:
        {"group_id": str, "post_ids": list[int], "count": int, "preview": list[str]}
    """
    from dashboard import campaign

    if not platforms:
        platforms = ["facebook", "instagram", "threads", "linkedin", "tiktok"]
    return campaign.generate_campaign(business_description, platforms)


@mcp.tool()
def socialblast_enrich_post(post_id: int, with_video: bool = False) -> dict[str, Any]:
    """Run the AI media pipeline on a pending post.

    Generates an image (and optionally a video) from the post's caption,
    attaching them to the post in the approval queue. The post stays in
    pending status, a human must still approve.

    Args:
        post_id: The pending post's database id.
        with_video: If True, also generate a 6s video (slow, costs more credits).

    Returns:
        {"ok": bool, "post_id": int, "steps": list[{"step", "ok", "url"|"error"}]}
    """
    from dashboard import campaign

    return campaign.enrich_post(post_id, with_video=with_video)


@mcp.tool()
def socialblast_enrich_campaign(group_id: str, with_video: bool = False) -> dict[str, Any]:
    """Enrich every pending post in a campaign group.

    Args:
        group_id: The campaign's group_id (returned by generate_campaign).
        with_video: If True, also generate videos (slow).

    Returns:
        {"group_id": str, "enriched": int, "total": int, "results": list}
    """
    from dashboard import campaign

    return campaign.enrich_campaign(group_id, with_video=with_video)


@mcp.tool()
def socialblast_predict_virality(prompt: str, platform: str = "instagram") -> dict[str, Any]:
    """Score how likely a caption is to go viral on a given platform.

    Requires HiggsField credentials (HF_API_KEY + HF_API_SECRET).
    Returns a stub on other backends.

    Args:
        prompt: The caption text to score.
        platform: instagram, tiktok, facebook, etc.

    Returns:
        {"score": float | None, "engagement_prediction": dict, "reason": str}
    """
    from ai_services.higgsfield import HiggsFieldAdapter

    return HiggsFieldAdapter().predict_virality(prompt, platform=platform)


@mcp.tool()
def socialblast_list_pending() -> dict[str, Any]:
    """List all pending posts in the approval queue with their caption + metadata.

    Useful for Claude to review the queue and suggest which posts to approve,
    edit, or enrich. Read-only, does not change any state.

    Returns:
        {"count": int, "posts": list[{id, message, platform, account_name,
        image_url, video_url, group_id, created_at}]}
    """
    from dashboard import db

    posts = db.list_posts(status="pending")
    return {
        "count": len(posts),
        "posts": [
            {
                "id": p["id"],
                "message": p["message"],
                "platform": p["platform"],
                "account_name": p["account_name"],
                "image_url": p.get("image_url"),
                "video_url": p.get("video_url"),
                "group_id": p.get("group_id"),
                "created_at": p["created_at"],
            }
            for p in posts
        ],
    }


@mcp.tool()
def socialblast_create_draft(
    message: str,
    platform: str,
    image_url: str | None = None,
    video_url: str | None = None,
    scheduled_time: str | None = None,
) -> dict[str, Any]:
    """Create a new pending post in the approval queue.

    This tool never auto-publishes or auto-schedules the post. It
    lands with status='pending' exactly like every other draft, and a
    human must approve it from the dashboard before anything is sent to
    a platform. scheduled_time is stored as metadata only. Arming the
    scheduler happens when a human approves from the dashboard.

    Args:
        message: The post body.
        platform: One of "facebook", "instagram", "whatsapp", "threads", "linkedin", "tiktok".
        image_url: Optional image to attach.
        video_url: Optional video to attach.
        scheduled_time: Optional ISO 8601 timestamp to display alongside the draft.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    if platform not in KNOWN_PLATFORMS:
        return {
            "ok": False,
            "error": f"Unknown platform '{platform}'. Choose one of: {', '.join(sorted(KNOWN_PLATFORMS))}",
        }
    if scheduled_time is not None:
        try:
            datetime.fromisoformat(scheduled_time)
        except ValueError:
            return {"ok": False, "error": f"scheduled_time '{scheduled_time}' is not valid ISO 8601"}

    post_id = db.create_post(message=message, platform=platform, image_url=image_url, video_url=video_url)
    if scheduled_time is not None:
        db.update_post(post_id, scheduled_for=scheduled_time)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_edit_pending(
    post_id: int,
    message: str | None = None,
    image_url: str | None = None,
    video_url: str | None = None,
    scheduled_time: str | None = None,
) -> dict[str, Any]:
    """Edit a pending post's fields. Refuses to touch non-pending posts.

    Args:
        post_id: The post's database id.
        message: New caption text, if changing.
        image_url: New image URL, if changing.
        video_url: New video URL, if changing.
        scheduled_time: New ISO 8601 scheduled time, if changing.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": f"Post {post_id} not found"}
    if post["status"] != "pending":
        return {
            "ok": False,
            "error": (
                f"Post {post_id} is '{post['status']}', not 'pending'. "
                "Approved and published posts are managed from the dashboard."
            ),
        }

    fields: dict[str, Any] = {}
    if message is not None:
        fields["message"] = message
    if image_url is not None:
        fields["image_url"] = image_url
    if video_url is not None:
        fields["video_url"] = video_url
    if scheduled_time is not None:
        try:
            datetime.fromisoformat(scheduled_time)
        except ValueError:
            return {"ok": False, "error": f"scheduled_time '{scheduled_time}' is not valid ISO 8601"}
        fields["scheduled_for"] = scheduled_time

    if not fields:
        return {"ok": False, "error": "No fields to update"}

    db.update_post(post_id, **fields)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_reject_pending(post_id: int) -> dict[str, Any]:
    """Reject a pending post. Refuses to touch non-pending posts.

    Args:
        post_id: The post's database id.

    Returns:
        {"ok": True, "post_id": int} or {"ok": False, "error": str}
    """
    from dashboard import db

    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": f"Post {post_id} not found"}
    if post["status"] != "pending":
        return {
            "ok": False,
            "error": (
                f"Post {post_id} is '{post['status']}', not 'pending'. "
                "Approved and published posts are managed from the dashboard."
            ),
        }
    db.reject_post(post_id)
    return {"ok": True, "post_id": post_id}


@mcp.tool()
def socialblast_search_posts(q: str = "", status: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Full-text search over post messages, optionally filtered by status. Read-only.

    Args:
        q: Substring to search for in the message body. Empty matches all.
        status: Optional status filter (pending, published, rejected, failed, scheduled).
        limit: Maximum rows to return.

    Returns:
        {"count": int, "posts": list[dict]}
    """
    from dashboard import db

    posts = db.search_posts(q=q, status=status or "", limit=limit)
    return {"count": len(posts), "posts": posts}


@mcp.tool()
def socialblast_queue_stats() -> dict[str, Any]:
    """Counts of posts per status, plus the upcoming scheduled queue. Read-only.

    Returns:
        {"by_status": dict[str, int], "scheduled": list[dict]}
    """
    from dashboard import db

    return {"by_status": db.stats(), "scheduled": db.list_scheduled()}


# ---------------------------------------------------------------------------
# Facebook read-only tools (4), always registered.
# ---------------------------------------------------------------------------

@mcp.tool()
@mcp_support.envelope
def facebook_get_posts(limit: int = 25, after: str | None = None, include_scheduled: bool = False) -> dict[str, Any]:
    """List recent Facebook Page posts. Read-only.

    Args:
        limit: Max posts to return (client-side truncation of Graph's
            default page. The adapter does not yet request custom page
            sizes from Graph itself).
        after: Reserved for a future paging cursor. Not yet wired to the
            underlying adapter. Accepted for forward compatibility only.
        include_scheduled: When True, also return unpublished scheduled
            posts (the old get_scheduled_posts tool) under "scheduled".

    Returns:
        {"success": True, "data": {"posts": [...], "scheduled": [...] | None}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    posts = manager.get_page_posts()
    if "error" in posts:
        return posts
    result: dict[str, Any] = {"posts": posts.get("data", [])[:limit]}
    if include_scheduled:
        scheduled = manager.get_scheduled_posts()
        if "error" in scheduled:
            return scheduled
        result["scheduled"] = scheduled.get("data", [])
    return result


@mcp.tool()
@mcp_support.envelope
def facebook_get_post_engagement(post_id: str) -> dict[str, Any]:
    """One-call engagement summary: reactions, comments, shares, permalink, impressions.

    Individual insight metrics Meta has deprecated degrade to null with a
    note in "deprecated_metrics" instead of failing the whole call.

    Args:
        post_id: The Facebook post id.

    Returns:
        {"success": True, "data": {"reactions": dict, "comment_count": int,
        "share_count": int, "permalink_url": str | None, "impressions": dict,
        "deprecated_metrics": list[str]}} or {"success": False, "error": {...}}
        if the post itself can't be read.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    return manager.get_post_engagement(post_id)


@mcp.tool()
@mcp_support.envelope
def facebook_get_comments(post_id: str, include_replies: bool = False) -> dict[str, Any]:
    """List comments on a post, optionally with each comment's reply thread. Read-only.

    Args:
        post_id: The Facebook post id.
        include_replies: When True, fetch and attach each top-level
            comment's replies (one extra Graph API call per comment).

    Returns:
        {"success": True, "data": {"comments": list[dict], "count": int}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    comments = manager.get_post_comments(post_id)
    if "error" in comments:
        return comments
    data = comments.get("data", [])
    if include_replies:
        for comment in data:
            replies = manager.get_comment_replies(comment["id"])
            comment["replies"] = replies.get("data", []) if "error" not in replies else []
    return {"comments": data, "count": len(data)}


@mcp.tool()
@mcp_support.envelope
def facebook_get_page_info() -> dict[str, Any]:
    """Extended Page metadata including fan_count. Read-only.

    Returns:
        {"success": True, "data": {..., "fan_count": int}}
        or {"success": False, "error": {...}} on a Graph API failure.
    """
    missing = _require_facebook_config()
    if missing:
        return missing
    info = manager.get_page_info()
    if "error" in info:
        return info
    info["fan_count"] = manager.get_page_fan_count()
    return info


# ---------------------------------------------------------------------------
# Direct-write tools (4), registered only when SOCIALBLAST_ALLOW_DIRECT_WRITES
# is set. Every tool here bypasses the approval queue. See CLAUDE.md section 5.
# ---------------------------------------------------------------------------

if mcp_support.direct_writes_enabled():

    @mcp.tool()
    @mcp_support.envelope
    def facebook_publish_now(
        message: str,
        image_url: str | None = None,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Publishes to Facebook immediately.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true. Prefer
        socialblast_create_draft for anything a human should review first.

        Args:
            message: Post text.
            image_url: Optional image to post as a photo instead of a text post.
            scheduled_publish_time: Optional Unix timestamp for Graph-native
                future publishing. The post WILL go live at that time with
                no further review. This is Graph's own scheduling, not
                the dashboard's approval queue.

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if image_url:
            return manager.post_image_to_facebook(image_url, message)
        if scheduled_publish_time is not None:
            return manager.schedule_post(message, scheduled_publish_time)
        return manager.post_to_facebook(message)

    @mcp.tool()
    @mcp_support.envelope
    def facebook_manage_post(post_id: str, action: str, new_message: str | None = None) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Update or delete a live post.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            post_id: The Facebook post id.
            action: "update" or "delete".
            new_message: Required when action="update".

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if action == "update":
            if not new_message:
                return {
                    "success": False,
                    "error": {
                        "code": "bad_request",
                        "message": "new_message is required for action='update'",
                        "hint": "Pass new_message with the updated text.",
                    },
                }
            return manager.update_post(post_id, new_message)
        if action == "delete":
            return manager.delete_post(post_id)
        return {
            "success": False,
            "error": {
                "code": "bad_request",
                "message": f"Unknown action '{action}'",
                "hint": "action must be 'update' or 'delete'.",
            },
        }

    @mcp.tool()
    @mcp_support.envelope
    def facebook_moderate_comment(
        comment_ids: list[str],
        action: str,
        post_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Moderate one or more comments.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            comment_ids: One or more comment ids to act on.
            action: "reply" (single id only, requires message + post_id),
                "hide", "unhide", or "delete".
            post_id: Required when action="reply".
            message: Required when action="reply".

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        if action == "reply":
            if len(comment_ids) != 1 or not post_id or not message:
                return {
                    "success": False,
                    "error": {
                        "code": "bad_request",
                        "message": "action='reply' needs exactly one comment id plus post_id and message",
                        "hint": "Call again with a single comment id.",
                    },
                }
            return manager.reply_to_comment(post_id, comment_ids[0], message)
        if action == "hide":
            return {"results": manager.bulk_hide_comments(comment_ids)}
        if action == "unhide":
            return {"results": manager.bulk_unhide_comments(comment_ids)}
        if action == "delete":
            return {"results": manager.bulk_delete_comments(comment_ids)}
        return {
            "success": False,
            "error": {
                "code": "bad_request",
                "message": f"Unknown action '{action}'",
                "hint": "action must be one of reply, hide, unhide, delete.",
            },
        }

    @mcp.tool()
    @mcp_support.envelope
    def facebook_send_dm(user_id: str, message: str) -> dict[str, Any]:
        """DIRECT WRITE. Bypasses the approval queue. Sends a Messenger DM immediately.

        Only registered when SOCIALBLAST_ALLOW_DIRECT_WRITES=true.

        Args:
            user_id: The Messenger-scoped user id.
            message: DM text.

        Returns:
            {"success": True, "data": {...}} or {"success": False, "error": {...}}
        """
        missing = _require_facebook_config()
        if missing:
            return missing
        return manager.send_dm_to_user(user_id, message)

else:
    # importlib.reload() re-executes this module's code but does not reset
    # its namespace, so a prior "flag on" import can leave these names
    # behind even after the flag is turned off. Clear them explicitly.
    for _tool_name in (
        "facebook_publish_now",
        "facebook_manage_post",
        "facebook_moderate_comment",
        "facebook_send_dm",
    ):
        if _tool_name in globals():
            del globals()[_tool_name]
    del _tool_name
