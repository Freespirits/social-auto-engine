"""Campaign wizard — generate a week of content from a single prompt.

Generates 7 social-media post drafts (one per day) and inserts them into
the approval queue as pending posts.  Tries OpenAI for smart captions;
falls back to template-based generation when no API key is available.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_campaign(
    business_description: str,
    platforms: list[str],
    face_asset_id: int | None = None,
) -> dict:
    """Generate a 7-day content campaign and create posts in the approval queue.

    Returns ``{"group_id": str, "post_ids": list[int], "count": int}``.
    """
    group_id = str(uuid.uuid4())
    post_ids: list[int] = []
    now = datetime.now(timezone.utc)

    captions = _generate_captions_ai(business_description)
    if not captions:
        captions = _generate_captions_template(business_description)

    for i, caption in enumerate(captions[:7]):
        scheduled = now + timedelta(days=i + 1, hours=9)  # 9 AM each day
        for platform in platforms:
            pid = db.create_post(
                message=caption["text"],
                account_name=platform.title(),
                platform=platform,
                group_id=group_id,
            )
            db.update_post(
                pid,
                scheduled_for=scheduled.isoformat(timespec="seconds"),
                status="pending",
            )
            post_ids.append(pid)

    return {
        "group_id": group_id,
        "post_ids": post_ids,
        "count": len(post_ids),
        "preview": [c["text"] for c in captions[:3]],
    }


# ---------------------------------------------------------------------------
# Post enrichment — add image + voice + video to a pending post
# ---------------------------------------------------------------------------

def enrich_post(post_id: int, *, with_video: bool = False) -> dict:
    """Run the full media pipeline on a single pending post.

    Generates an image from the caption if image_url is empty. Optionally
    generates a video too (slow). Returns the steps that ran and the result.
    """
    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": "Post not found"}
    if post.get("status") != "pending":
        return {"ok": False, "error": "Only pending posts can be enriched"}

    steps: list[dict] = []
    caption = post.get("message", "").strip()
    if not caption:
        return {"ok": False, "error": "Post has no caption"}

    if not post.get("image_url"):
        img_step = _enrich_image(post_id, caption)
        steps.append(img_step)

    if with_video and not post.get("video_url"):
        vid_step = _enrich_video(post_id, caption)
        steps.append(vid_step)

    return {"ok": True, "post_id": post_id, "steps": steps}


def enrich_campaign(group_id: str, *, with_video: bool = False) -> dict:
    """Enrich every pending post in a campaign group."""
    posts = db.list_group(group_id)
    results = [enrich_post(p["id"], with_video=with_video) for p in posts if p.get("status") == "pending"]
    return {
        "group_id": group_id,
        "enriched": sum(1 for r in results if r.get("ok")),
        "total": len(results),
        "results": results,
    }


def _enrich_image(post_id: int, caption: str) -> dict:
    try:
        from content.image_gen import generate_image
    except ImportError:
        return {"step": "image", "ok": False, "error": "Image gen module unavailable"}
    prompt = _caption_to_image_prompt(caption)
    try:
        url = generate_image(prompt, aspect_ratio="1:1")
        db.update_post(post_id, image_url=url)
        return {"step": "image", "ok": True, "url": url}
    except Exception as exc:
        return {"step": "image", "ok": False, "error": str(exc)[:200]}


def _enrich_video(post_id: int, caption: str) -> dict:
    try:
        from ai_services.higgsfield import HiggsFieldAdapter
    except ImportError:
        return {"step": "video", "ok": False, "error": "Video gen module unavailable"}
    adapter = HiggsFieldAdapter()
    if not adapter.is_configured:
        return {"step": "video", "ok": False, "error": "No video backend configured"}
    prompt = _caption_to_video_prompt(caption)
    try:
        result = adapter.generate_video(prompt, aspect_ratio="9:16", duration=6)
        url = result.get("output_url")
        if url:
            db.update_post(post_id, video_url=url)
        return {"step": "video", "ok": bool(url), "url": url, "backend": result.get("backend")}
    except Exception as exc:
        return {"step": "video", "ok": False, "error": str(exc)[:200]}


def _caption_to_image_prompt(caption: str) -> str:
    """Convert a social caption into an image prompt."""
    base = caption.replace('"', "").replace("\n", " ").strip()
    return f"Professional social media photo: {base}. Bright, clean, high quality, eye-catching composition."


def _caption_to_video_prompt(caption: str) -> str:
    """Convert a social caption into a video prompt."""
    base = caption.replace('"', "").replace("\n", " ").strip()
    return f"Cinematic 6-second social video: {base}. Smooth motion, modern style, vertical format."


# ---------------------------------------------------------------------------
# Caption generators
# ---------------------------------------------------------------------------

def _generate_captions_ai(business_description: str) -> list[dict] | None:
    """Try to generate captions using OpenAI. Returns None if unavailable."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    try:
        import urllib.request

        prompt = (
            f"You are a social media expert. Generate 7 social media post captions "
            f"for a business described as: '{business_description}'. "
            f"Each post should use a different viral hook style. "
            f"Return valid JSON: an array of 7 objects, each with a 'text' field "
            f"containing the caption (max 280 chars) and a 'type' field "
            f"('text', 'image', or 'video')."
        )

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        captions = parsed.get("posts") or parsed.get("captions") or parsed
        if isinstance(captions, list):
            return [
                {
                    "text": c.get("text", c.get("caption", str(c))),
                    "type": c.get("type", "text"),
                }
                for c in captions
            ]
    except Exception:
        pass
    return None


def _generate_captions_template(business_description: str) -> list[dict]:
    """Fallback: hand-tuned premium captions used when OpenAI is unavailable."""
    biz = business_description.strip() or "our brand"
    return [
        {
            "text": f"Three things nobody tells you about running {biz}. Number two saved us 12 hours a week.",
            "type": "video",
        },
        {
            "text": f"Watch what happens when a regular customer walks into {biz} for the first time. Real reactions, no script.",
            "type": "video",
        },
        {
            "text": f"Behind every order at {biz} there is a story. Today's story: a Tuesday morning regular who never misses a beat.",
            "type": "image",
        },
        {
            "text": f"We tried the trend everyone is talking about. Here is what happened when {biz} did it our way.",
            "type": "video",
        },
        {
            "text": f"Question for our followers: what is the one thing you wish you had known before discovering {biz}? Comment below.",
            "type": "text",
        },
        {
            "text": f"The before and after that has everyone talking. {biz} delivers, every single time.",
            "type": "image",
        },
        {
            "text": f"Friday roundup from {biz}: three wins this week, one funny mistake, and what is coming next Monday.",
            "type": "text",
        },
    ]
