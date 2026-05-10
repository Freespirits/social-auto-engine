"""Social Auto Engine dashboard.

Run: python -m dashboard.app
Open: http://127.0.0.1:7651

Architecture:
- FastAPI + Jinja2 + HTMX (no SPA build)
- SQLite for the approval queue
- Reuses facebook_api.FacebookAPI from the MCP server
"""
from __future__ import annotations

import os
import time
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Make sibling modules importable when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
# Also load persisted OAuth tokens written by the /oauth/<platform>/callback flows
load_dotenv(Path.home() / ".social-auto-engine" / "tokens.env", override=False)

import json  # noqa: E402

from manager import Manager  # noqa: E402

from . import db  # noqa: E402
from . import scheduler  # noqa: E402
from .auth import (  # noqa: E402
    AuthMiddleware,
    auth_required,
    check_password,
    create_session_token,
    COOKIE_NAME,
    SESSION_MAX_AGE,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _time_ago(iso: str | None) -> str:
    """Format an ISO timestamp as 'just now', '5m ago', '3h ago', '2d ago'."""
    if not iso:
        return ""
    from datetime import datetime, timezone
    try:
        ts = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
    except Exception:
        return iso[:16].replace("T", " ") if len(iso) >= 16 else iso

    if secs < 5:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    if secs < 86400 * 7:
        return f"{secs // 86400}d ago"
    return iso[:10]


templates.env.filters["time_ago"] = _time_ago

from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start scheduler on boot, stop on shutdown."""
    db.init_db()
    scheduler.start()
    yield
    scheduler.shutdown(wait=True)


app = FastAPI(title="Social Auto Engine", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# User-uploaded and AI-generated media live under ~/.social-auto-engine/media
# so they survive redeploys and stay separate from packaged static assets.
MEDIA_DIR = Path.home() / ".social-auto-engine" / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

fb = Manager()


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

def _sidebar_groups() -> list[dict]:
    """Build the sidebar accounts list, grouped by parent company.

    Returned shape:
        [
          {"company": "Meta", "accounts": [{cls, icon, label, connected, platform}, ...]},
          {"company": "LinkedIn", "accounts": [...]},
          ...
        ]
    Order is fixed: Meta → LinkedIn → TikTok → YouTube → X.
    """
    page_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
    linkedin_info = _safe_linkedin_info()
    tiktok_info = _safe_tiktok_info()
    youtube_info = _safe_youtube_info()

    return [
        {
            "company": "Meta",
            "key": "meta",
            "accounts": [
                {
                    "platform": "facebook",
                    "cls": "fb",
                    "icon": "f",
                    "label": page_info.get("name", "Facebook"),
                    "connected": bool(page_info.get("id")),
                },
                {
                    "platform": "instagram",
                    "cls": "ig",
                    "icon": "IG",
                    "label": f"@{ig_info.get('username')}" if ig_info.get("connected") else "Instagram",
                    "connected": ig_info.get("connected", False),
                },
                {
                    "platform": "threads",
                    "cls": "th",
                    "icon": "@",
                    "label": f"@{threads_info.get('username')}" if threads_info.get("connected") else "Threads",
                    "connected": threads_info.get("connected", False),
                },
                {
                    "platform": "whatsapp",
                    "cls": "wa",
                    "icon": "W",
                    "label": wa_info.get("display_phone_number", "WhatsApp") if wa_info.get("connected") else "WhatsApp",
                    "connected": wa_info.get("connected", False),
                },
            ],
        },
        {
            "company": "LinkedIn",
            "key": "linkedin",
            "accounts": [
                {
                    "platform": "linkedin",
                    "cls": "li",
                    "icon": "in",
                    "label": linkedin_info.get("name", "LinkedIn") if linkedin_info.get("connected") else "LinkedIn",
                    "connected": linkedin_info.get("connected", False),
                },
            ],
        },
        {
            "company": "TikTok",
            "key": "tiktok",
            "accounts": [
                {
                    "platform": "tiktok",
                    "cls": "tt",
                    "icon": "TT",
                    "label": (
                        f"@{tiktok_info.get('username')}"
                        if tiktok_info.get("connected") and tiktok_info.get("username")
                        else (tiktok_info.get("name") if tiktok_info.get("connected") else "TikTok")
                    ),
                    "connected": tiktok_info.get("connected", False),
                },
            ],
        },
        {
            "company": "YouTube",
            "key": "youtube",
            "accounts": [
                {
                    "platform": "youtube",
                    "cls": "yt",
                    "icon": "YT",
                    "label": youtube_info.get("name", "YouTube") if youtube_info.get("connected") else "YouTube",
                    "connected": youtube_info.get("connected", False),
                },
            ],
        },
        {
            "company": "X",
            "key": "x",
            "accounts": [
                {
                    "platform": "x",
                    "cls": "x",
                    "icon": "\U0001d54f",
                    "label": "X / Twitter",
                    "connected": False,
                },
            ],
        },
    ]


def _base_context(active_nav: str = "inbox") -> dict:
    """Common template context shared by all pages."""
    return {
        "stats": db.stats(),
        "sidebar_groups": _sidebar_groups(),
        "active_nav": active_nav,
        "auth_active": auth_required(),
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = _base_context("inbox")
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
    linkedin_info = _safe_linkedin_info()
    wa_templates = _safe_wa_templates() if wa_info.get("connected") else []
    pending_singles, pending_groups = db.list_pending_grouped()
    ctx.update({
        "page": _safe_page_info(),
        "ig": ig_info,
        "wa": wa_info,
        "threads": threads_info,
        "linkedin": linkedin_info,
        "wa_templates": wa_templates,
        "pending": pending_singles,
        "pending_groups": pending_groups,
        "published": db.list_posts(status="published", limit=10),
        "failed": db.list_posts(status="failed", limit=5),
        "rejected": db.list_posts(status="rejected", limit=5),
    })
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar(request: Request):
    from datetime import datetime, timezone as tz, timedelta

    # Default to this week (Mon–Sun)
    now = datetime.now(tz.utc)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=7)

    cal_posts = db.calendar_posts(monday.isoformat(), sunday.isoformat())
    ctx = _base_context("calendar")
    ctx["posts_json"] = json.dumps(cal_posts, default=str)
    return templates.TemplateResponse(request, "calendar.html", ctx)


@app.get("/api/calendar")
async def api_calendar(start: str = "", end: str = ""):
    """JSON endpoint for the calendar JS to fetch posts for a given week."""
    from fastapi.responses import JSONResponse
    if not start or not end:
        return JSONResponse([])
    posts = db.calendar_posts(start, end)
    return JSONResponse(posts)


@app.get("/published", response_class=HTMLResponse)
async def published_page(request: Request):
    ctx = _base_context("published")
    ctx["published"] = db.list_posts(status="published", limit=50)
    return templates.TemplateResponse(request, "published.html", ctx)


# ---------------------------------------------------------------------------
# HTMX-powered fragments
# ---------------------------------------------------------------------------

SUPPORTED_PLATFORMS = {"facebook", "instagram", "whatsapp", "threads", "linkedin"}
BROADCAST_PLATFORMS = {"facebook", "instagram", "threads", "linkedin"}
ACCOUNT_LABELS = {
    "facebook": "Hack-Tech",
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
    "threads": "Threads",
    "linkedin": "LinkedIn",
}


@app.post("/compose", response_class=HTMLResponse)
async def compose(
    request: Request,
    message: str = Form(""),
    platform: str = Form(""),
    platforms: list[str] = Form([]),
    image_url: str = Form(""),
    video_url: str = Form(""),
    audio_url: str = Form(""),
    recipient: str = Form(""),
    template_name: str = Form(""),
):
    """Create one or more pending posts.

    Two ways to call this:
    - Single platform (legacy / direct message): pass `platform=facebook` etc.
    - Broadcast: pass `platforms=facebook&platforms=instagram&...`. Creates one
      group_id and N pending rows, one per platform.
    """
    message = message.strip()
    image_url = image_url.strip() or None
    video_url = video_url.strip() or None
    audio_url = audio_url.strip() or None
    recipient = recipient.strip() or None
    template_name = template_name.strip() or None

    targets = [p.strip() for p in platforms if p and p.strip()]
    if not targets and platform.strip():
        targets = [platform.strip()]
    if not targets:
        raise HTTPException(400, "Pick at least one platform.")

    unknown = [p for p in targets if p not in SUPPORTED_PLATFORMS]
    if unknown:
        raise HTTPException(400, f"Unknown platform(s): {', '.join(unknown)}")

    if "whatsapp" in targets and len(targets) > 1:
        raise HTTPException(
            400,
            "WhatsApp messages are 1:1 and cannot be combined with broadcast platforms.",
        )

    if "whatsapp" in targets:
        if not recipient:
            raise HTTPException(400, "WhatsApp messages need a recipient phone number.")
        if not message and not template_name:
            raise HTTPException(400, "WhatsApp messages need either a body or a template.")
    else:
        if not message:
            raise HTTPException(400, "Message cannot be empty.")
        if "instagram" in targets and not image_url:
            raise HTTPException(400, "Instagram posts require an image URL.")

    if len(targets) == 1:
        only = targets[0]
        db.create_post(
            message or f"[Template: {template_name}]",
            account_name=ACCOUNT_LABELS[only],
            platform=only,
            image_url=image_url,
            video_url=video_url,
            audio_url=audio_url,
            recipient=recipient,
            template_name=template_name,
        )
    else:
        broadcast_targets = [
            {"platform": p, "account_name": ACCOUNT_LABELS[p]} for p in targets
        ]
        db.create_broadcast(
            message=message,
            targets=broadcast_targets,
            image_url=image_url,
            video_url=video_url,
            audio_url=audio_url,
        )

    return _refresh_all(request)


# ---------------------------------------------------------------------------
# Compose studio — media upload, prompt enhance, video gen, voiceover, captions
# ---------------------------------------------------------------------------
#
# These endpoints back the rich compose modal. They never publish anything
# directly. Their job is to land assets and text in the dashboard so the
# user can attach them to a post (which still flows through the usual
# /compose -> /approve approval queue).

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".webm"}
ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB hard ceiling


def _public_media_url(request: Request, filename: str) -> str:
    """Build a publicly reachable URL for a media file.

    Honours OAUTH_REDIRECT_BASE_URL the same way the OAuth flow does.
    Falls back to the request's base URL, which works locally but
    will fail when external publishing platforms (Instagram, LinkedIn)
    need to fetch the asset from the public internet — that's the
    cue to run an ngrok tunnel; see docs/ngrok-setup.md.
    """
    override = os.getenv("MEDIA_PUBLIC_BASE_URL") or os.getenv("OAUTH_REDIRECT_BASE_URL")
    base = (override or str(request.base_url)).rstrip("/")
    return f"{base}/media/{filename}"


def _save_upload(upload, *, allowed_exts: set[str], kind: str) -> tuple[str, str]:
    """Persist an UploadFile to MEDIA_DIR. Returns (filename, abs_path).

    Raises HTTPException on size or extension violations.
    """
    filename = (upload.filename or "").strip()
    if not filename:
        raise HTTPException(400, "Filename missing")
    ext = Path(filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"Unsupported {kind} extension: {ext}")
    safe_stem = secrets.token_hex(8)
    safe_name = f"{safe_stem}{ext}"
    dest = MEDIA_DIR / safe_name
    total = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "Upload exceeds 200 MB limit")
            f.write(chunk)
    return safe_name, str(dest)


@app.post("/compose/upload")
async def compose_upload(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("image"),
    alt_text: str = Form(""),
):
    """Accept a single image or video upload from the compose modal."""
    if kind == "image":
        allowed = ALLOWED_IMAGE_EXTS
    elif kind == "video":
        allowed = ALLOWED_VIDEO_EXTS
    elif kind == "audio":
        allowed = ALLOWED_AUDIO_EXTS
    else:
        raise HTTPException(400, f"Unknown media kind: {kind}")
    filename, abs_path = _save_upload(file, allowed_exts=allowed, kind=kind)
    public_url = _public_media_url(request, filename)
    media_id = db.create_media(
        kind=kind,
        path=abs_path,
        url=public_url,
        alt_text=alt_text or None,
        source_provider="upload",
        status="ready",
    )
    return {
        "id": media_id,
        "kind": kind,
        "filename": filename,
        "url": public_url,
        "alt_text": alt_text,
    }


@app.post("/compose/enhance-prompt")
async def compose_enhance_prompt(
    idea: str = Form(...),
    provider: str = Form("auto"),
    model: str = Form(""),
):
    """Expand a short user idea into a cinematic video prompt."""
    idea = (idea or "").strip()
    if not idea:
        raise HTTPException(400, "Idea is empty")
    chosen = fb.pick_text_provider(provider) if provider == "auto" else provider
    if chosen == "none":
        raise HTTPException(
            400,
            "No LLM provider connected. Connect Grok, Bedrock or Ollama on the Settings page.",
        )
    started = time.time()
    if chosen == "grok":
        result = fb.grok.enhance_video_prompt(idea, model=model or None)
    elif chosen == "bedrock":
        from ai_services.grok import VIDEO_PROMPT_SYSTEM
        result = fb.bedrock.invoke_text(idea, system=VIDEO_PROMPT_SYSTEM, max_tokens=400)
    elif chosen == "ollama":
        from ai_services.grok import VIDEO_PROMPT_SYSTEM
        result = fb.ollama.generate(idea, system=VIDEO_PROMPT_SYSTEM, num_predict=400)
    else:
        raise HTTPException(400, f"Unknown provider: {chosen}")
    duration_ms = int((time.time() - started) * 1000)
    db.log_prompt_run(
        provider=chosen,
        kind="enhance_video",
        input=idea,
        output=result.get("text", ""),
        duration_ms=duration_ms,
        error=result.get("error"),
    )
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return {"prompt": result.get("text", ""), "provider": chosen, "duration_ms": duration_ms}


@app.post("/compose/rewrite-post")
async def compose_rewrite_post(
    draft: str = Form(...),
    target_platform: str = Form("linkedin"),
    voice_notes: str = Form(""),
    provider: str = Form("auto"),
):
    draft = (draft or "").strip()
    if not draft:
        raise HTTPException(400, "Draft is empty")
    chosen = fb.pick_text_provider(provider) if provider == "auto" else provider
    if chosen == "none":
        raise HTTPException(400, "No LLM provider connected")
    if chosen == "grok":
        result = fb.grok.rewrite_post(draft, target_platform, voice_notes=voice_notes)
    elif chosen == "bedrock":
        from ai_services.grok import POST_REWRITE_SYSTEM
        prompt = f"Platform: {target_platform}\nVoice notes: {voice_notes or '(none)'}\n\nDraft:\n{draft}"
        result = fb.bedrock.invoke_text(prompt, system=POST_REWRITE_SYSTEM, max_tokens=800)
    elif chosen == "ollama":
        from ai_services.grok import POST_REWRITE_SYSTEM
        prompt = f"Platform: {target_platform}\nVoice notes: {voice_notes or '(none)'}\n\nDraft:\n{draft}"
        result = fb.ollama.generate(prompt, system=POST_REWRITE_SYSTEM, num_predict=600)
    else:
        raise HTTPException(400, f"Unknown provider: {chosen}")
    db.log_prompt_run(
        provider=chosen, kind="rewrite_post", input=draft, output=result.get("text", ""),
        error=result.get("error"),
    )
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return {"text": result.get("text", ""), "provider": chosen}


@app.post("/compose/generate-video")
async def compose_generate_video(
    request: Request,
    prompt: str = Form(...),
    duration: int = Form(5),
    aspect_ratio: str = Form("16:9"),
    image_url: str = Form(""),
    seed: int | None = Form(None),
):
    """Submit a video generation job. Returns the media_id immediately;
    the frontend polls /compose/video/{media_id}/status."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt is empty")
    submission = fb.higgsfield.generate_video(
        prompt,
        duration=duration,
        aspect_ratio=aspect_ratio,
        image_url=image_url or None,
        seed=seed,
    )
    if submission.get("error"):
        raise HTTPException(502, submission["error"])
    job_id = submission.get("job_id", "")
    provider = submission.get("provider", "")
    metadata = json.dumps(
        {"prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio}
    )
    media_id = db.create_media(
        kind="video",
        source_provider=provider,
        source_job_id=job_id,
        status="running",
        metadata=metadata,
    )
    db.log_prompt_run(
        provider=provider, kind="video", input=prompt, output=f"job:{job_id}",
    )
    return {
        "media_id": media_id,
        "job_id": job_id,
        "provider": provider,
        "status": submission.get("status"),
    }


@app.get("/compose/video/{media_id}/status")
async def compose_video_status(request: Request, media_id: int):
    media = db.get_media(media_id)
    if not media:
        raise HTTPException(404, "Media not found")
    if media["status"] in {"ready", "failed"}:
        return media
    job_id = media["source_job_id"]
    provider = media["source_provider"]
    info = fb.higgsfield.get_job(job_id, provider=provider)
    if info["status"] == "succeeded" and info.get("output"):
        db.update_media_status(media_id, status="ready", url=info["output"])
        media = db.get_media(media_id)
    elif info["status"] == "failed":
        db.update_media_status(
            media_id, status="failed", metadata=json.dumps({"error": info.get("error")})
        )
        media = db.get_media(media_id)
    else:
        media["status"] = info["status"]
    return media


@app.post("/compose/voiceover")
async def compose_voiceover(
    request: Request,
    text: str = Form(...),
    voice_id: str = Form(""),
    stability: float = Form(0.5),
    similarity_boost: float = Form(0.75),
):
    """Generate a voiceover MP3 from ``text`` and persist it as a media row."""
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "Text is empty")
    result = fb.elevenlabs.text_to_speech(
        text,
        voice_id=voice_id or None,
        stability=stability,
        similarity_boost=similarity_boost,
    )
    if result.get("error"):
        raise HTTPException(502, result["error"])
    audio_bytes: bytes = result["audio"]
    safe_name = f"voiceover_{secrets.token_hex(8)}.mp3"
    dest = MEDIA_DIR / safe_name
    dest.write_bytes(audio_bytes)
    public_url = _public_media_url(request, safe_name)
    media_id = db.create_media(
        kind="audio",
        path=str(dest),
        url=public_url,
        source_provider="elevenlabs",
        status="ready",
        metadata=json.dumps({"voice_id": result.get("voice_id"), "characters": result.get("characters")}),
    )
    db.log_prompt_run(
        provider="elevenlabs", kind="tts", input=text, output=public_url,
    )
    return {"id": media_id, "url": public_url, "characters": result.get("characters")}


@app.get("/compose/voices")
async def compose_voices():
    return {"voices": fb.elevenlabs.list_voices()}


@app.post("/compose/captions")
async def compose_captions(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(""),
):
    """Upload an audio or video file and return Deepgram captions in SRT."""
    filename = (file.filename or "").strip()
    ext = Path(filename).suffix.lower()
    if ext not in (ALLOWED_AUDIO_EXTS | ALLOWED_VIDEO_EXTS):
        raise HTTPException(400, f"Unsupported extension: {ext}")
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 200 MB limit")
    mime = file.content_type or "application/octet-stream"
    result = fb.deepgram.transcribe(
        audio_bytes=raw,
        mime_type=mime,
        language=language or None,
    )
    if result.get("error"):
        raise HTTPException(502, result["error"])
    srt = fb.deepgram.to_srt(result.get("words", []))
    safe_stem = secrets.token_hex(8)
    srt_path = MEDIA_DIR / f"captions_{safe_stem}.srt"
    srt_path.write_text(srt, encoding="utf-8")
    media_id = db.create_media(
        kind="caption",
        path=str(srt_path),
        url=_public_media_url(request, srt_path.name),
        source_provider="deepgram",
        status="ready",
        metadata=json.dumps(
            {"duration": result.get("duration"), "language": result.get("language")}
        ),
    )
    db.log_prompt_run(
        provider="deepgram", kind="transcribe",
        input=f"<audio {len(raw)} bytes>",
        output=result.get("transcript", "")[:2000],
    )
    return {
        "id": media_id,
        "transcript": result.get("transcript", ""),
        "srt": srt,
        "duration": result.get("duration"),
        "language": result.get("language"),
        "url": _public_media_url(request, srt_path.name),
    }


@app.post("/compose/generate-image")
async def compose_generate_image(
    request: Request,
    prompt: str = Form(...),
    width: int = Form(1024),
    height: int = Form(1024),
    seed: int | None = Form(None),
):
    """Generate a still image via Bedrock SDXL or Titan Image."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt is empty")
    result = fb.bedrock.invoke_image(prompt, width=width, height=height, seed=seed)
    if result.get("error"):
        raise HTTPException(502, result["error"])
    image_bytes: bytes = result["image_bytes"]
    safe_name = f"image_{secrets.token_hex(8)}.png"
    dest = MEDIA_DIR / safe_name
    dest.write_bytes(image_bytes)
    public_url = _public_media_url(request, safe_name)
    media_id = db.create_media(
        kind="image",
        path=str(dest),
        url=public_url,
        source_provider="bedrock",
        status="ready",
        metadata=json.dumps({"model": result.get("model"), "prompt": prompt}),
    )
    db.log_prompt_run(
        provider="bedrock", kind="image", input=prompt, output=public_url,
    )
    return {"id": media_id, "url": public_url, "model": result.get("model")}


@app.post("/approve/{post_id}", response_class=HTMLResponse)
async def approve(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")
    _publish_post(post)
    refreshed = db.get_post(post_id) or post
    if refreshed.get("status") == "published":
        toast = ("success", f"Published to {post['account_name']}")
    else:
        toast = ("error", f"Failed: {refreshed.get('error_message', 'unknown error')[:120]}")
    return _refresh_all(request, toast=toast)


def _publish_post(post: dict) -> None:
    """Dispatch to the right platform adapter and record the result."""
    platform = post.get("platform", "facebook")
    try:
        permalink = None

        if platform == "facebook":
            result = fb.post_to_facebook(post["message"])
            platform_post_id = result.get("id")
            try:
                detail = fb.get_post_permalink(platform_post_id) if platform_post_id else {}
                permalink = detail.get("permalink_url") if isinstance(detail, dict) else None
            except Exception:
                permalink = None

        elif platform == "instagram":
            result = fb.post_to_instagram(
                image_url=post["image_url"], caption=post["message"]
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")
            try:
                detail = fb.ig.get_media_permalink(platform_post_id) if platform_post_id else {}
                permalink = detail.get("permalink") if isinstance(detail, dict) else None
            except Exception:
                permalink = None

        elif platform == "threads":
            if post.get("image_url"):
                result = fb.post_image_to_threads(
                    image_url=post["image_url"], text=post["message"]
                )
            else:
                result = fb.post_text_to_threads(post["message"])
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")
            try:
                detail = fb.threads.get_thread_permalink(platform_post_id) if platform_post_id else {}
                permalink = detail.get("permalink") if isinstance(detail, dict) else None
            except Exception:
                permalink = None

        elif platform == "whatsapp":
            recipient = post.get("recipient")
            if not recipient:
                raise RuntimeError("WhatsApp post missing recipient")
            if post.get("template_name"):
                result = fb.send_whatsapp_template(recipient, post["template_name"])
            else:
                result = fb.send_whatsapp_text(recipient, post["message"])
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")  # WA message ID

        elif platform == "linkedin":
            result = fb.post_to_linkedin(
                message=post["message"],
                image_url=post.get("image_url"),
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error")))
            platform_post_id = result.get("id")

        else:
            raise RuntimeError(f"Unknown platform: {platform}")

        db.mark_published(post["id"], platform_post_id, permalink)
    except Exception as exc:
        db.mark_failed(post["id"], str(exc))


@app.post("/reject/{post_id}", response_class=HTMLResponse)
async def reject(request: Request, post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "pending":
        raise HTTPException(409, f"Post is {post['status']}")
    db.reject_post(post_id)
    return _refresh_all(request, toast=("info", "Rejected — won't publish"))


@app.post("/approve-all", response_class=HTMLResponse)
async def approve_all(request: Request):
    pending = db.list_posts(status="pending")
    n = len(pending)
    for post in pending:
        _publish_post(post)
    return _refresh_all(request, toast=("success", f"Approved & published {n} posts"))


@app.post("/approve-group/{group_id}", response_class=HTMLResponse)
async def approve_group(request: Request, group_id: str):
    """Publish every pending row sharing this group_id."""
    rows = db.list_group(group_id, status="pending")
    if not rows:
        raise HTTPException(404, "No pending posts in this group")

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for post in rows:
        _publish_post(post)
        refreshed = db.get_post(post["id"])
        platform_label = (post.get("platform") or "?").title()
        if refreshed and refreshed.get("status") == "published":
            succeeded.append(platform_label)
        else:
            err = (refreshed or {}).get("error_message") or "unknown error"
            failed.append((platform_label, err[:80]))

    if not failed:
        toast = ("success", f"Published to {', '.join(succeeded)}")
    elif not succeeded:
        toast = ("error", f"All {len(failed)} publishes failed. See activity log.")
    else:
        broken = ", ".join(f"{p} ({reason})" for p, reason in failed)
        toast = (
            "warning",
            f"Published {len(succeeded)} of {len(rows)}. Failed: {broken}",
        )
    return _refresh_all(request, toast=toast)


@app.post("/reject-group/{group_id}", response_class=HTMLResponse)
async def reject_group(request: Request, group_id: str):
    """Reject every pending row sharing this group_id."""
    rows = db.list_group(group_id, status="pending")
    if not rows:
        raise HTTPException(404, "No pending posts in this group")
    for post in rows:
        db.reject_post(post["id"])
    return _refresh_all(
        request,
        toast=("info", f"Rejected broadcast — {len(rows)} posts won't publish"),
    )


@app.get("/favicon.ico")
async def favicon():
    """Serve the SVG favicon for browsers that request /favicon.ico."""
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


# TikTok URL-prefix verification.
#
# TikTok asks us to host a small text file at a known path to prove
# ownership of EACH URL prefix configured in the dev portal. With our
# setup that is at least two: the domain root, and the OAuth callback
# subpath. Each prefix gets its own env-var pair.
#
# Domain-root verification:
#   TIKTOK_VERIFY_FILENAME=tiktokXXXXXXXX.txt
#   TIKTOK_VERIFY_TOKEN=XXXXXXXX
#
# OAuth-callback-prefix verification:
#   TIKTOK_CALLBACK_VERIFY_FILENAME=tiktokYYYYYYYY.txt
#   TIKTOK_CALLBACK_VERIFY_TOKEN=YYYYYYYY
#
# Both routes use the constrained pattern `tiktok{token}.txt` so neither
# shadows other routes.
@app.get("/tiktok{token}.txt")
async def serve_tiktok_verification_file(token: str):
    return _serve_tiktok_verify(
        token,
        filename_env="TIKTOK_VERIFY_FILENAME",
        token_env="TIKTOK_VERIFY_TOKEN",
    )


@app.get("/oauth/tiktok/callback/tiktok{token}.txt")
async def serve_tiktok_callback_verification_file(token: str):
    return _serve_tiktok_verify(
        token,
        filename_env="TIKTOK_CALLBACK_VERIFY_FILENAME",
        token_env="TIKTOK_CALLBACK_VERIFY_TOKEN",
    )


def _serve_tiktok_verify(token: str, filename_env: str, token_env: str):
    """Shared helper for TikTok URL-prefix verification routes."""
    from fastapi.responses import PlainTextResponse

    expected_filename = os.getenv(filename_env, "")
    expected_token = os.getenv(token_env, "")
    if not (expected_filename and expected_token):
        raise HTTPException(404)
    if f"tiktok{token}.txt" != expected_filename:
        raise HTTPException(404)
    return PlainTextResponse(
        f"tiktok-developers-site-verification={expected_token}",
        media_type="text/plain",
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login form.  Redirect to / if already authenticated or auth is off."""
    if not auth_required():
        return RedirectResponse(url="/", status_code=303)
    from .auth import validate_session_token
    token = request.cookies.get(COOKIE_NAME)
    if token and validate_session_token(token):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form("")):
    """Validate password and set session cookie."""
    if not auth_required():
        return RedirectResponse(url="/", status_code=303)
    if not check_password(password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Incorrect password"}, status_code=401,
        )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout():
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# OAuth connect flows (LinkedIn / TikTok / YouTube)
# ---------------------------------------------------------------------------
#
# Each platform has the same shape:
#   GET  /oauth/<platform>/start    -> redirects to provider auth page
#   GET  /oauth/<platform>/callback -> exchanges ?code= for tokens, persists
#
# Tokens are persisted to ~/.social-auto-engine/tokens.env using the same
# key names the adapters read at boot. When the user signs in next, the
# tokens are loaded by python-dotenv (see lifespan / load_dotenv) or by
# the adapter's os.getenv on init.
#
# We DO NOT write back to the project's repo .env file. The token store
# is a separate file under the user's home directory.

import secrets  # noqa: E402

TOKENS_PATH = Path.home() / ".social-auto-engine" / "tokens.env"


def _store_tokens(updates: dict[str, str]) -> None:
    """Write or update KEY=VALUE pairs in ~/.social-auto-engine/tokens.env.

    Also updates the live os.environ AND patches the in-memory adapter
    instances so the running dashboard sees the new tokens without restart.
    """
    TOKENS_PATH.parent.mkdir(exist_ok=True)
    existing: dict[str, str] = {}
    if TOKENS_PATH.exists():
        for line in TOKENS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            existing[k.strip()] = v.strip()
    existing.update({k: v for k, v in updates.items() if v})
    TOKENS_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    # Push to live env so a fresh adapter init sees them
    for k, v in updates.items():
        if v:
            os.environ[k] = v
    # Patch the live adapter instances so we don't need a restart
    if "LINKEDIN_ACCESS_TOKEN" in updates:
        fb.linkedin.access_token = updates["LINKEDIN_ACCESS_TOKEN"]
        fb.linkedin._person_urn = None  # force re-fetch on next call
    if "TIKTOK_ACCESS_TOKEN" in updates:
        fb.tiktok.access_token = updates["TIKTOK_ACCESS_TOKEN"]
    if "YOUTUBE_ACCESS_TOKEN" in updates:
        fb.youtube.access_token = updates["YOUTUBE_ACCESS_TOKEN"]
    if "YOUTUBE_REFRESH_TOKEN" in updates:
        fb.youtube.refresh_token = updates["YOUTUBE_REFRESH_TOKEN"]


def _public_redirect_uri(request: Request, platform: str) -> str:
    """Compute the OAuth callback URL for a given platform.

    Default: derive from the request's base URL so localhost works without
    any configuration.

    Override: set OAUTH_REDIRECT_BASE_URL in the environment when the
    dashboard runs behind a reverse proxy or tunnel and the redirect URI
    needs to match exactly what was registered in the platform dev portal.
    Example value: "https://yourdomain.com" (no trailing slash).
    """
    override = os.getenv("OAUTH_REDIRECT_BASE_URL", "").rstrip("/")
    base = override or str(request.base_url).rstrip("/")
    return f"{base}/oauth/{platform}/callback"


def _verify_oauth_state(request: Request, cookie_name: str, supplied_state: str) -> None:
    """Reject the callback when the state cookie is missing or doesn't match.

    Prevents CSRF: an attacker cannot trick a logged-in user into accepting
    OAuth credentials they did not start. The cookie is set during /start
    and removed after the callback runs.
    """
    expected = request.cookies.get(cookie_name)
    if not expected:
        raise HTTPException(
            400,
            "OAuth flow not properly initiated (no state cookie). "
            "Start the connection from the Settings page.",
        )
    if not supplied_state or supplied_state != expected:
        raise HTTPException(400, "OAuth state mismatch")


@app.get("/oauth/linkedin/start")
async def oauth_linkedin_start(request: Request):
    """Kick off the LinkedIn OAuth dance."""
    redirect_uri = _public_redirect_uri(request, "linkedin")
    state = secrets.token_urlsafe(16)
    url = fb.linkedin.get_auth_url(redirect_uri) + f"&state={state}"
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("linkedin_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/oauth/linkedin/callback")
async def oauth_linkedin_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Receive ?code= from LinkedIn, exchange for token, store, redirect."""
    if error:
        raise HTTPException(400, f"LinkedIn auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "linkedin_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "linkedin")
    result = fb.linkedin.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    _store_tokens({"LINKEDIN_ACCESS_TOKEN": token})
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("linkedin_oauth_state")
    return response


@app.get("/oauth/tiktok/start")
async def oauth_tiktok_start(request: Request):
    redirect_uri = _public_redirect_uri(request, "tiktok")
    state = secrets.token_urlsafe(16)
    url = fb.tiktok.get_auth_url(redirect_uri, state=state)
    response = RedirectResponse(url=url, status_code=303)
    # Stash the state in a short-lived cookie so we can validate the callback
    response.set_cookie("tiktok_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/oauth/tiktok/callback")
async def oauth_tiktok_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        raise HTTPException(400, f"TikTok auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "tiktok_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "tiktok")
    result = fb.tiktok.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    updates = {
        "TIKTOK_ACCESS_TOKEN": token,
    }
    if result.get("refresh_token"):
        updates["TIKTOK_REFRESH_TOKEN"] = result["refresh_token"]
    _store_tokens(updates)
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("tiktok_oauth_state")
    return response


@app.get("/oauth/youtube/start")
async def oauth_youtube_start(request: Request):
    redirect_uri = _public_redirect_uri(request, "youtube")
    state = secrets.token_urlsafe(16)
    url = fb.youtube.get_auth_url(redirect_uri, state=state)
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("youtube_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.post("/oauth/{platform}/disconnect")
async def oauth_disconnect(request: Request, platform: str):
    """Clear stored tokens for a platform and patch the live adapter."""
    if platform not in {"linkedin", "tiktok", "youtube"}:
        raise HTTPException(404, f"Unknown platform: {platform}")

    keys_to_clear = {
        "linkedin": ["LINKEDIN_ACCESS_TOKEN"],
        "tiktok": ["TIKTOK_ACCESS_TOKEN", "TIKTOK_REFRESH_TOKEN"],
        "youtube": ["YOUTUBE_ACCESS_TOKEN", "YOUTUBE_REFRESH_TOKEN"],
    }[platform]

    # Remove keys from the persisted tokens file
    if TOKENS_PATH.exists():
        existing: dict[str, str] = {}
        for line in TOKENS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() not in keys_to_clear:
                existing[k.strip()] = v.strip()
        TOKENS_PATH.write_text(
            "\n".join(f"{k}={v}" for k, v in existing.items()) + ("\n" if existing else ""),
            encoding="utf-8",
        )

    # Clear from live env
    for key in keys_to_clear:
        os.environ.pop(key, None)

    # Patch the live adapter instance
    if platform == "linkedin":
        fb.linkedin.access_token = None
        fb.linkedin._person_urn = None
    elif platform == "tiktok":
        fb.tiktok.access_token = None
    elif platform == "youtube":
        fb.youtube.access_token = None
        fb.youtube.refresh_token = None

    return RedirectResponse(url="/settings", status_code=303)


@app.get("/oauth/youtube/callback")
async def oauth_youtube_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        raise HTTPException(400, f"YouTube auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "youtube_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "youtube")
    result = fb.youtube.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    updates = {"YOUTUBE_ACCESS_TOKEN": token}
    if result.get("refresh_token"):
        updates["YOUTUBE_REFRESH_TOKEN"] = result["refresh_token"]
    _store_tokens(updates)
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("youtube_oauth_state")
    return response


# ---------------------------------------------------------------------------
# AI services — Notion OAuth + API-key save / disconnect / test
# ---------------------------------------------------------------------------
#
# Notion uses OAuth and reuses the existing _store_tokens / state-cookie
# infrastructure. Every other AI service (ElevenLabs, Grok, Deepgram,
# HiggsField, Bedrock, Ollama) is API-key based. The user pastes the key
# in the Settings page; the dashboard validates it with ``ping()`` and
# only persists when the ping succeeds. That way we never store an
# obviously wrong key.
#
# Bedrock takes three values (access key, secret, region). Ollama takes
# a base URL. Everything else takes a single API key.

AI_SERVICE_FIELDS: dict[str, list[str]] = {
    "elevenlabs": ["ELEVENLABS_API_KEY"],
    "higgsfield": ["HIGGSFIELD_API_KEY", "REPLICATE_API_TOKEN"],
    "grok": ["GROK_API_KEY"],
    "deepgram": ["DEEPGRAM_API_KEY"],
    "bedrock": [
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
    ],
    "ollama": ["OLLAMA_BASE_URL", "OLLAMA_DEFAULT_MODEL"],
    # Notion is API-key OR OAuth; we accept a pasted internal token here too
    "notion": ["NOTION_ACCESS_TOKEN"],
}


def _adapter_for(service: str):
    return {
        "elevenlabs": fb.elevenlabs,
        "higgsfield": fb.higgsfield,
        "grok": fb.grok,
        "notion": fb.notion,
        "deepgram": fb.deepgram,
        "bedrock": fb.bedrock,
        "ollama": fb.ollama,
    }.get(service)


@app.get("/oauth/notion/start")
async def oauth_notion_start(request: Request):
    if not (fb.notion.client_id and fb.notion.client_secret):
        raise HTTPException(
            400,
            "Notion OAuth not configured. Set NOTION_CLIENT_ID and "
            "NOTION_CLIENT_SECRET, or paste an internal integration "
            "token directly on the Settings page.",
        )
    redirect_uri = _public_redirect_uri(request, "notion")
    state = secrets.token_urlsafe(16)
    url = fb.notion.build_authorize_url(redirect_uri, state)
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("notion_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/oauth/notion/callback")
async def oauth_notion_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    if error:
        raise HTTPException(400, f"Notion auth error: {error}")
    if not code:
        raise HTTPException(400, "Missing ?code parameter")
    _verify_oauth_state(request, "notion_oauth_state", state)
    redirect_uri = _public_redirect_uri(request, "notion")
    result = fb.notion.exchange_code(code, redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(400, f"Token exchange failed: {result}")
    _store_tokens({"NOTION_ACCESS_TOKEN": token})
    fb.notion.access_token = token
    response = RedirectResponse(url="/settings", status_code=303)
    response.delete_cookie("notion_oauth_state")
    return response


@app.post("/ai/{service}/connect", response_class=HTMLResponse)
async def ai_connect(request: Request, service: str):
    """Save API-key credentials for an AI service.

    Validates by re-instantiating the adapter and calling ``ping``. If
    the ping fails the keys are NOT persisted — we don't want to lock
    users into bad credentials.
    """
    if service not in AI_SERVICE_FIELDS:
        raise HTTPException(404, f"Unknown service: {service}")
    form = await request.form()
    updates: dict[str, str] = {}
    for key in AI_SERVICE_FIELDS[service]:
        value = (form.get(key) or "").strip()
        if value:
            updates[key] = value
    if not updates:
        raise HTTPException(400, "No fields supplied")

    # Tentatively apply to env so the freshly-built adapter sees them
    saved_env = {k: os.environ.get(k) for k in updates}
    for k, v in updates.items():
        os.environ[k] = v
    fb.reload_ai_services()
    adapter = _adapter_for(service)
    info = adapter.ping() if adapter else {"connected": False, "error": "no adapter"}
    if not info.get("connected"):
        # Roll back env changes; do NOT persist
        for k, prev in saved_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
        fb.reload_ai_services()
        return HTMLResponse(
            f'<span class="conn-status off">✗ {info.get("error", "Connect failed")}</span>',
            status_code=400,
        )
    # Validation passed — persist
    _store_tokens(updates)
    return HTMLResponse(
        '<span class="conn-status ok">✓ Connected</span>',
        headers={"HX-Refresh": "true"},
    )


@app.post("/ai/{service}/disconnect")
async def ai_disconnect(request: Request, service: str):
    if service not in AI_SERVICE_FIELDS:
        raise HTTPException(404, f"Unknown service: {service}")
    keys_to_clear = list(AI_SERVICE_FIELDS[service])
    if TOKENS_PATH.exists():
        existing: dict[str, str] = {}
        for line in TOKENS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() not in keys_to_clear:
                existing[k.strip()] = v.strip()
        TOKENS_PATH.write_text(
            "\n".join(f"{k}={v}" for k, v in existing.items()) + ("\n" if existing else ""),
            encoding="utf-8",
        )
    for key in keys_to_clear:
        os.environ.pop(key, None)
    fb.reload_ai_services()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/ai/{service}/test", response_class=HTMLResponse)
async def ai_test(request: Request, service: str):
    if service not in AI_SERVICE_FIELDS:
        raise HTTPException(404, f"Unknown service: {service}")
    adapter = _adapter_for(service)
    info = adapter.ping() if adapter else {"connected": False, "error": "no adapter"}
    connected = bool(info.get("connected"))
    detail = (
        info.get("default_model")
        or info.get("workspace")
        or info.get("model")
        or info.get("provider")
        or info.get("region")
        or info.get("base_url")
        or info.get("tier")
        or info.get("error", "")
    )
    return HTMLResponse(
        f'<span class="conn-status {"ok" if connected else "off"}">'
        f'{"✓ Connected · " + str(detail) if connected else "✗ " + str(detail)}'
        f'</span>'
    )


def _ai_services_status() -> list[dict[str, Any]]:
    """Return a list of dicts describing each AI service for the
    Settings page renderer.

    Pings every adapter concurrently so the worst-case latency is the
    slowest single adapter, not the sum of all of them.
    """
    from concurrent.futures import ThreadPoolExecutor

    descriptors = [
        ("elevenlabs", "ElevenLabs", "Text-to-speech and voice cloning", "key", False),
        ("higgsfield", "HiggsField / Replicate", "AI video generation", "key", False),
        ("grok", "Grok (xAI)", "Prompt enhancement and post rewriting", "key", False),
        ("notion", "Notion", "Sync drafts to a Notion database", "key+oauth", True),
        ("deepgram", "Deepgram", "Speech-to-text and captions", "key", False),
        ("bedrock", "Amazon Bedrock", "Claude / Stable Diffusion / Titan via AWS", "aws", False),
        ("ollama", "Ollama", "Local LLM for free prompt enhancement", "url", False),
    ]

    def _safe_ping(service: str) -> dict[str, Any]:
        adapter = _adapter_for(service)
        if adapter is None:
            return {"connected": False, "error": "no adapter"}
        try:
            return adapter.ping()
        except Exception as exc:  # ping() should never raise but be defensive
            return {"connected": False, "error": f"ping crashed: {exc}"}

    services = [d[0] for d in descriptors]
    with ThreadPoolExecutor(max_workers=len(services)) as ex:
        results = list(ex.map(_safe_ping, services))

    rows: list[dict[str, Any]] = []
    for (service, label, desc, kind, has_oauth), info in zip(descriptors, results):
        rows.append(
            {
                "service": service,
                "label": label,
                "description": desc,
                "kind": kind,
                "has_oauth": has_oauth,
                "connected": bool(info.get("connected")),
                "info": info,
                "fields": AI_SERVICE_FIELDS.get(service, []),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    fb_info = _safe_page_info()
    ig_info = _safe_ig_info()
    wa_info = _safe_wa_info()
    threads_info = _safe_threads_info()
    accounts = []
    accounts.append({
        "platform": "facebook",
        "platform_label": "Facebook",
        "icon_class": "fb",
        "icon_label": "f",
        "name": fb_info.get("name", "—"),
        "id": fb_info.get("id", "—"),
        "connected": bool(fb_info.get("id") and fb_info.get("name")),
        "details": fb_info.get("category", ""),
    })
    accounts.append({
        "platform": "instagram",
        "platform_label": "Instagram",
        "icon_class": "ig",
        "icon_label": "IG",
        "name": f"@{ig_info.get('username')}" if ig_info.get("connected") else "Not connected",
        "id": ig_info.get("id", "—"),
        "connected": bool(ig_info.get("connected")),
        "details": (
            f"{ig_info.get('followers_count', 0):,} followers · {ig_info.get('media_count', 0)} posts"
            if ig_info.get("connected") else ig_info.get("error", "")
        ),
    })
    accounts.append({
        "platform": "whatsapp",
        "platform_label": "WhatsApp",
        "icon_class": "wa",
        "icon_label": "W",
        "name": wa_info.get("verified_name", "—") if wa_info.get("connected") else "Not connected",
        "id": wa_info.get("display_phone_number", "—"),
        "connected": bool(wa_info.get("connected")),
        "details": (
            f"Quality: {wa_info.get('quality_rating', 'UNKNOWN')}"
            if wa_info.get("connected") else wa_info.get("error", "")
        ),
    })
    accounts.append({
        "platform": "threads",
        "platform_label": "Threads",
        "icon_class": "th",
        "icon_label": "@",
        "name": f"@{threads_info.get('username')}" if threads_info.get("connected") else "Not connected",
        "id": threads_info.get("id", "—"),
        "connected": bool(threads_info.get("connected")),
        "details": (
            threads_info.get("name", "")
            if threads_info.get("connected") else threads_info.get("error", "")
        ),
    })
    linkedin_info = _safe_linkedin_info()
    accounts.append({
        "platform": "linkedin",
        "platform_label": "LinkedIn",
        "icon_class": "li",
        "icon_label": "in",
        "name": linkedin_info.get("name", "Not connected") if linkedin_info.get("connected") else "Not connected",
        "id": linkedin_info.get("id", "—"),
        "connected": bool(linkedin_info.get("connected")),
        "details": (
            linkedin_info.get("email", "")
            if linkedin_info.get("connected") else linkedin_info.get("error", "")
        ),
    })
    tiktok_info = _safe_tiktok_info()
    accounts.append({
        "platform": "tiktok",
        "platform_label": "TikTok",
        "icon_class": "tt",
        "icon_label": "TT",
        "name": (
            f"@{tiktok_info.get('username')}"
            if tiktok_info.get("connected") and tiktok_info.get("username")
            else (tiktok_info.get("name", "Not connected") if tiktok_info.get("connected") else "Not connected")
        ),
        "id": tiktok_info.get("id", "—"),
        "connected": bool(tiktok_info.get("connected")),
        "details": (
            f"{tiktok_info.get('follower_count', 0):,} followers"
            if tiktok_info.get("connected") else tiktok_info.get("error", "")
        ),
    })
    youtube_info = _safe_youtube_info()
    accounts.append({
        "platform": "youtube",
        "platform_label": "YouTube",
        "icon_class": "yt",
        "icon_label": "YT",
        "name": youtube_info.get("name", "Not connected") if youtube_info.get("connected") else "Not connected",
        "id": youtube_info.get("id", "—"),
        "connected": bool(youtube_info.get("connected")),
        "details": (
            f"{youtube_info.get('subscriber_count', 0):,} subscribers · {youtube_info.get('video_count', 0)} videos"
            if youtube_info.get("connected") else youtube_info.get("error", "")
        ),
    })
    accounts.append({
        "platform": "x",
        "platform_label": "X / Twitter",
        "icon_class": "x",
        "icon_label": "\U0001d54f",
        "name": "Not connected",
        "id": "—",
        "connected": False,
        "details": "Adapter planned — paid API tier required ($100/mo Basic).",
    })

    env_summary = {
        "META_APP_ID": os.getenv("META_APP_ID", ""),
        "META_APP_SECRET": "set" if os.getenv("META_APP_SECRET") else "missing",
        "FACEBOOK_PAGE_ID": os.getenv("FACEBOOK_PAGE_ID", ""),
        "FACEBOOK_ACCESS_TOKEN": "set" if os.getenv("FACEBOOK_ACCESS_TOKEN") else "missing",
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID", "—"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "—"),
        "THREADS_APP_ID": os.getenv("THREADS_APP_ID", "—"),
        "THREADS_ACCESS_TOKEN": "set" if os.getenv("THREADS_ACCESS_TOKEN") else "missing",
        "LINKEDIN_CLIENT_ID": os.getenv("LINKEDIN_CLIENT_ID", "—"),
        "LINKEDIN_CLIENT_SECRET": "set" if os.getenv("LINKEDIN_CLIENT_SECRET") else "missing",
        "LINKEDIN_ACCESS_TOKEN": "set" if os.getenv("LINKEDIN_ACCESS_TOKEN") else "missing",
        "TIKTOK_CLIENT_KEY": os.getenv("TIKTOK_CLIENT_KEY", "—"),
        "TIKTOK_CLIENT_SECRET": "set" if os.getenv("TIKTOK_CLIENT_SECRET") else "missing",
        "TIKTOK_ACCESS_TOKEN": "set" if os.getenv("TIKTOK_ACCESS_TOKEN") else "missing",
        "YOUTUBE_CLIENT_ID": os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID") or "—",
        "YOUTUBE_CLIENT_SECRET": "set" if (os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")) else "missing",
        "YOUTUBE_ACCESS_TOKEN": "set" if os.getenv("YOUTUBE_ACCESS_TOKEN") else "missing",
        "YOUTUBE_REFRESH_TOKEN": "set" if os.getenv("YOUTUBE_REFRESH_TOKEN") else "missing",
    }
    ai_services = _ai_services_status()
    ctx = _base_context("settings")
    ctx.update(
        {
            "accounts": accounts,
            "env": env_summary,
            "ai_services": ai_services,
        }
    )
    return templates.TemplateResponse(request, "settings.html", ctx)


@app.post("/settings/test/{platform}", response_class=HTMLResponse)
async def test_connection(request: Request, platform: str):
    """Re-check connection for a given platform; return updated status row."""
    if platform == "facebook":
        info = _safe_page_info()
        connected = bool(info.get("id"))
        message = info.get("name", "Page check failed") if connected else "Token may have expired"
    elif platform == "instagram":
        info = _safe_ig_info()
        connected = bool(info.get("connected"))
        message = f"@{info.get('username')}" if connected else info.get("error", "Not linked")
    elif platform == "whatsapp":
        info = _safe_wa_info()
        connected = bool(info.get("connected"))
        message = info.get("verified_name", "OK") if connected else info.get("error", "")
    elif platform == "threads":
        info = _safe_threads_info()
        connected = bool(info.get("connected"))
        message = f"@{info.get('username')}" if connected else info.get("error", "Not linked")
    elif platform == "linkedin":
        info = _safe_linkedin_info()
        connected = bool(info.get("connected"))
        message = info.get("name", "OK") if connected else info.get("error", "Not linked")
    elif platform == "tiktok":
        info = _safe_tiktok_info()
        connected = bool(info.get("connected"))
        message = (
            f"@{info.get('username')}" if connected and info.get("username")
            else info.get("name", "OK") if connected
            else info.get("error", "Not linked")
        )
    elif platform == "youtube":
        info = _safe_youtube_info()
        connected = bool(info.get("connected"))
        message = info.get("name", "OK") if connected else info.get("error", "Not linked")
    else:
        connected, message = False, "Adapter not implemented"
    response = HTMLResponse(
        f'<span class="conn-status {"ok" if connected else "off"}">'
        f'{"✓ Connected · " + message if connected else "✗ " + message}'
        f'</span>'
    )
    response.headers["HX-Trigger"] = json.dumps({
        "toast": {
            "kind": "success" if connected else "error",
            "message": f"{platform.title()}: {message}",
        }
    })
    return response


# ---------------------------------------------------------------------------
# Scheduler routes
# ---------------------------------------------------------------------------

@app.post("/schedule/{post_id}", response_class=HTMLResponse)
async def schedule_post(request: Request, post_id: int, at: str = Form("")):
    """Schedule a pending post for future publication."""
    from datetime import datetime, timezone as tz

    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] not in ("pending", "scheduled"):
        raise HTTPException(409, f"Post is {post['status']}, cannot schedule")

    at = at.strip()
    if not at:
        raise HTTPException(400, "Missing 'at' — provide an ISO-8601 datetime")

    try:
        run_at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=tz.utc)
    except ValueError:
        raise HTTPException(400, f"Bad datetime: {at}")

    if run_at <= datetime.now(tz.utc):
        raise HTTPException(400, "Scheduled time must be in the future")

    scheduler.schedule_post(post_id, run_at)
    return _refresh_all(
        request,
        toast=("success", f"Scheduled post #{post_id} for {run_at:%Y-%m-%d %H:%M} UTC"),
    )


@app.post("/unschedule/{post_id}", response_class=HTMLResponse)
async def unschedule_post(request: Request, post_id: int):
    """Cancel a scheduled post and return it to pending."""
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if post["status"] != "scheduled":
        raise HTTPException(409, f"Post is {post['status']}, not scheduled")

    removed = scheduler.cancel_post(post_id)
    if removed:
        toast = ("info", f"Post #{post_id} unscheduled — back to pending")
    else:
        toast = ("warning", f"Post #{post_id} job not found, reset to pending")
    return _refresh_all(request, toast=toast)


@app.get("/schedules", response_class=HTMLResponse)
async def list_schedules(request: Request):
    """Return all scheduled posts + active APScheduler jobs."""
    scheduled = db.list_scheduled()
    jobs = scheduler.list_jobs()
    return templates.TemplateResponse(
        request,
        "_schedules.html",
        {"scheduled": scheduled, "jobs": jobs},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_all(request: Request, toast: tuple[str, str] | None = None) -> HTMLResponse:
    pending_singles, pending_groups = db.list_pending_grouped()
    response = templates.TemplateResponse(
        request,
        "_columns.html",
        {
            "pending": pending_singles,
            "pending_groups": pending_groups,
            "published": db.list_posts(status="published", limit=10),
            "failed": db.list_posts(status="failed", limit=5),
            "rejected": db.list_posts(status="rejected", limit=5),
            "stats": db.stats(),
        },
    )
    if toast:
        kind, message = toast
        response.headers["HX-Trigger"] = json.dumps({"toast": {"kind": kind, "message": message}})
    return response


def _safe_page_info() -> dict:
    """Lookup Facebook page info; safe fallback when token is missing/expired.

    Returns the API result with `connected=True` on success, or a dict with
    `connected=False` and an error string when the call fails. Other helpers
    in this module follow the same shape.
    """
    try:
        info = fb.get_page_info() if hasattr(fb, "get_page_info") else None
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    if isinstance(info, dict) and info.get("id") and info.get("name"):
        # Mark explicitly connected so consumers don't have to infer
        info = {**info, "connected": True}
        return info
    return {"connected": False, "error": "Facebook page check returned no name/id"}


def _safe_ig_info() -> dict:
    """Lookup Instagram account; safe fallback when token is missing/expired."""
    try:
        info = fb.get_instagram_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_wa_info() -> dict:
    """Lookup WhatsApp Business phone-number info."""
    try:
        info = fb.get_whatsapp_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_threads_info() -> dict:
    """Lookup Threads account; safe fallback when token is missing/expired."""
    try:
        info = fb.get_threads_account_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_linkedin_info() -> dict:
    """Lookup LinkedIn profile; safe fallback when token is missing/expired."""
    try:
        info = fb.get_linkedin_profile()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_tiktok_info() -> dict:
    """Lookup TikTok profile; safe fallback when token is missing/expired."""
    try:
        info = fb.get_tiktok_profile()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_youtube_info() -> dict:
    """Lookup YouTube channel info; safe fallback when token is missing/expired."""
    try:
        info = fb.get_youtube_channel_info()
        return info if isinstance(info, dict) else {"connected": False}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _safe_wa_templates() -> list[dict]:
    try:
        return [t for t in fb.list_whatsapp_templates() if t.get("status") == "APPROVED"]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import uvicorn

    port = int(os.getenv("DASHBOARD_PORT", "7651"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
