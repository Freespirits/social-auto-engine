# Multi-Channel Social Media Platform: Master Plan

**Date:** 2026-05-02
**Status:** Draft (v2, gaps addressed)
**Scope:** Integration architecture for Facebook, Instagram, LinkedIn, TikTok, and X into a single dashboard with AI content generation, approval workflows, and automation at scale (1 to 100 pages/profiles).

---

## 1. Executive summary

Merge `facebook-mcp-server` (Facebook Graph API tooling, approval queue design) and `social-media-skills` (voice system, content generation, scoring, research) into one platform. The platform publishes to five channels from a single dashboard, generates content with multiple AI providers, and gates every action behind a human approval queue that scales to 100 managed pages.

The existing Slice 2 approval-queue spec (`2026-05-02-approval-queue-and-dashboard-mvp-design.md`) becomes one component inside this broader architecture. This document is Slice 0: the integration master plan that everything else fits inside.

### Scope note: "1 to 100 pages"

The platform manages 1 to 100 pages or profiles that already exist on each platform. These pages may be brand new (created today, zero posts, empty bio) and need to be fully built out from scratch. The platform handles everything after the page exists: populating the profile (via profile-optimizer skill), filling the feed with content, building an audience through consistent posting, and scaling that process across all connected accounts.

What the platform does not do is create the page or account itself. Platform APIs do not support programmatic page/account creation. The user creates the page on Facebook, Instagram, LinkedIn, X, or TikTok, then connects it to the dashboard. From that point, the platform takes over: generating content, scheduling posts, filling empty feeds, and scaling that workflow from 1 account to 100.

---

## 2. Platform API reality

Each platform has different API access requirements. The plan must be honest about what is available today, what requires application review, and what costs money.

### 2.1 Facebook (ready now)

- **API:** Graph API v22.0
- **Access:** Page Access Token via Facebook Developer App
- **Capabilities:** Post text/image/video, schedule posts, read insights, manage comments, send DMs, bulk operations
- **Limits:** 200 calls per user per hour (standard), 4800 per hour (approved app)
- **Cost:** Free
- **Current state:** Fully implemented in `facebook-mcp-server`

### 2.2 Instagram (ready now, via Facebook)

- **API:** Instagram Graph API (subset of Facebook Graph API)
- **Access:** Facebook Page linked to Instagram Professional Account, same app
- **Capabilities:** Publish photos/carousels/reels, read insights, manage comments, read mentions
- **Limits:** 25 content publishing API calls per 24 hours per account. This is the hardest constraint in the system.
- **Cannot do via API:** Stories (only via Content Publishing API for business accounts with approval), DMs (only via Messenger Platform for approved apps), live video
- **Cost:** Free
- **Gap:** Reels publishing requires video hosted at a public URL. The platform needs an upload-then-publish pipeline.

### 2.3 LinkedIn (requires app review)

- **API:** LinkedIn Marketing Developer Platform (v2 REST, transitioning to versioned API)
- **Access:** OAuth 2.0 three-legged flow. Posting to org pages requires `w_organization_social` scope, which needs Marketing Developer Platform approval (takes 2 to 8 weeks).
- **Capabilities:** Post text/image/video/articles/polls, read analytics, comment management
- **Limits:** 100 API calls per user per day for content creation. 1000 per day for reading.
- **Cannot do via API:** Carousel posts (only native), newsletter publishing, live video
- **Cost:** Free for approved apps
- **Gap:** App review is a blocking dependency. Plan for a manual posting fallback during the review period.

### 2.4 X / Twitter (costs money)

- **API:** X API v2
- **Access:** OAuth 2.0 or OAuth 1.0a. Basic tier is free but read-only (no posting).
- **Capabilities (Pro tier):** Post tweets/threads/polls, upload media, read timeline, manage lists
- **Limits:** Pro tier: 100 posts per 15 minutes, 300k tweet reads per month
- **Cost:** Pro tier is $200/month per app. This is non-negotiable for write access.
- **Cannot do via API:** Spaces (hosting), Communities posting, X Premium features
- **Gap:** The $200/month cost must be acknowledged to the user before enabling X integration. Do not silently assume this cost.

### 2.5 TikTok (requires app review)

- **API:** TikTok Content Posting API
- **Access:** OAuth 2.0. Requires app registration and review by TikTok (takes 2 to 6 weeks). The "Direct Post" scope requires additional review.
- **Capabilities:** Upload and publish videos (Direct Post or Inbox method), read video insights
- **Limits:** Varies by app approval level. Inbox method: users must manually confirm publish in TikTok app.
- **Cannot do via API:** Image posts (TikTok is video-only API), live streaming, duets, stitches, TikTok Shop
- **Cost:** Free for approved apps
- **Gap:** TikTok's "Inbox" method means the video goes to the user's TikTok drafts and they tap publish manually. "Direct Post" requires higher-level approval. The dashboard must clearly indicate which mode is active.

### 2.6 Platform readiness summary

| Platform  | API ready | Write access | Review needed | Monthly cost | Posting limit              |
|-----------|-----------|--------------|---------------|--------------|----------------------------|
| Facebook  | Yes       | Yes          | No            | Free         | 200 calls/hr               |
| Instagram | Yes       | Yes          | No            | Free         | 25 publishes/24hr/account  |
| LinkedIn  | Partial   | Needs review | 2-8 weeks     | Free         | 100 creates/day            |
| X         | Yes       | Pro tier     | No            | $200/month   | 100 posts/15min            |
| TikTok    | Partial   | Needs review | 2-6 weeks     | Free         | Varies by approval         |

---

## 3. Architecture

### 3.1 System overview

```
+-------------------------------------------------------------------+
|                        User's browser                              |
|                  Dashboard (FastAPI + HTMX)                        |
|                  http://127.0.0.1:7651                             |
+-------------------------------------------------------------------+
        |                    |                    |
        v                    v                    v
+---------------+  +------------------+  +------------------+
| Approval      |  | Content          |  | Analytics        |
| Queue         |  | Generation       |  | Engine           |
| (SQLite)      |  | (multi-AI)       |  | (per-platform)   |
+---------------+  +------------------+  +------------------+
        |                    |                    |
        v                    v                    v
+-------------------------------------------------------------------+
|                    Platform Router                                  |
|         Routes approved actions to platform adapters               |
+-------------------------------------------------------------------+
    |          |           |          |          |
    v          v           v          v          v
+--------+ +--------+ +--------+ +--------+ +--------+
|Facebook| |Insta-  | |LinkedIn| |  X     | |TikTok  |
|Graph   | |gram    | |Market- | |  API   | |Content |
|API     | |Graph   | |ing API | |  v2    | |Post API|
+--------+ +--------+ +--------+ +--------+ +--------+
```

### 3.2 Component breakdown

**Layer 1: Dashboard (FastAPI + Jinja2 + HTMX)**
- Server-rendered pages, no SPA build step
- HTMX for reactive updates (SSE for approval queue, polling for analytics)
- Serves on 127.0.0.1:7651 (port fallback 7651-7700)
- All state in SQLite, no external database dependency

**Layer 2: Core services**

| Service              | Responsibility                                                    |
|----------------------|-------------------------------------------------------------------|
| Approval Queue       | Human-in-the-loop gate for all write operations (Slice 2 spec)   |
| Content Generator    | Multi-AI content creation (text, image, video)                   |
| Voice Engine         | Loads voice.md + about-me.md, enforces voice consistency         |
| Scheduler            | Cron-style scheduling with per-platform optimal time suggestions |
| Analytics Engine     | Pulls insights from each platform, normalises into common schema |
| Scraper              | Apify-backed research for trends, competitor analysis, outliers  |

**Layer 3: Platform adapters**

Each platform gets its own adapter module implementing a common interface:

```python
class PlatformAdapter:
    async def publish_text(self, account_id: str, content: PostContent) -> PublishResult
    async def publish_image(self, account_id: str, content: PostContent, media: MediaRef) -> PublishResult
    async def publish_video(self, account_id: str, content: PostContent, media: MediaRef) -> PublishResult
    async def get_insights(self, account_id: str, post_id: str) -> InsightsData
    async def get_comments(self, account_id: str, post_id: str) -> list[Comment]
    async def delete_post(self, account_id: str, post_id: str) -> bool
    def get_rate_limits(self) -> RateLimitInfo
    def get_capabilities(self) -> set[Capability]
```

The `get_capabilities()` method returns what this platform can actually do. The dashboard uses this to show/hide UI elements per platform (e.g., no "post image" button for TikTok, no "carousel" for LinkedIn via API).

### 3.3 Directory structure

```
facebook-mcp-server/
  facebook_mcp/
    __init__.py
    server.py                   # FastMCP entry point (existing, extended)
    config.py                   # Env vars, platform credentials
    models.py                   # SQLAlchemy models (request, tool_policy, account, post)
    
    adapters/
      __init__.py
      base.py                   # PlatformAdapter ABC
      facebook.py               # Facebook Graph API (migrated from facebook_api.py)
      instagram.py              # Instagram Graph API
      linkedin.py               # LinkedIn Marketing API
      x.py                      # X API v2
      tiktok.py                 # TikTok Content Posting API
    
    approval/
      __init__.py
      queue.py                  # Approval queue (from Slice 2 spec)
      policy.py                 # Tool tiering: read/write/destructive
      field_hints.py            # Edit UX hints per field
    
    content/
      __init__.py
      generator.py              # Multi-AI content generation orchestrator
      voice.py                  # Voice system loader (about-me.md, voice.md)
      hooks.py                  # Hook generator (6 types)
      scorer.py                 # Post scorer (5 criteria)
      research.py               # Niche research via Apify/web
    
    media/
      __init__.py
      image_gen.py              # Image generation (DALL-E, Gemini, etc.)
      video_gen.py              # Video generation (ElevenLabs, HeyGen, Remotion)
      uploader.py               # Media upload to platform-required hosting
    
    dashboard/
      __init__.py
      app.py                    # FastAPI app
      routes/
        inbox.py                # Approval inbox (SSE)
        compose.py              # Multi-platform compose
        accounts.py             # Account management
        analytics.py            # Cross-platform analytics
        settings.py             # Tool policies, AI provider config
        history.py              # Action history log
      templates/
        base.html
        inbox.html
        compose.html
        accounts.html
        analytics.html
        settings.html
      static/
        styles.css
        htmx.min.js
    
    scheduler/
      __init__.py
      cron.py                   # Scheduled post execution
      optimal_times.py          # Per-platform best posting times
    
    analytics/
      __init__.py
      collector.py              # Pull insights from all platforms
      normaliser.py             # Common schema for cross-platform comparison
```

### 3.4 Data model

SQLite database at `~/.facebook-mcp/platform.db`.

**accounts table**
```sql
CREATE TABLE accounts (
    id            TEXT PRIMARY KEY,         -- uuid
    platform      TEXT NOT NULL,            -- facebook|instagram|linkedin|x|tiktok
    display_name  TEXT NOT NULL,
    username      TEXT,
    access_token  TEXT NOT NULL,            -- encrypted at rest
    refresh_token TEXT,
    token_expiry  TEXT,
    page_id       TEXT,                     -- platform-specific page/profile ID
    capabilities  TEXT,                     -- JSON array of supported actions
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**posts table**
```sql
CREATE TABLE posts (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    platform        TEXT NOT NULL,
    content_text    TEXT,
    media_urls      TEXT,                   -- JSON array
    post_type       TEXT,                   -- text|image|video|carousel|reel
    platform_post_id TEXT,                  -- ID returned by platform after publish
    status          TEXT DEFAULT 'draft',   -- draft|queued|approved|published|failed
    scheduled_at    TEXT,
    published_at    TEXT,
    approval_id     TEXT REFERENCES request(id),
    ai_provider     TEXT,                   -- which AI generated this
    voice_score     REAL,                   -- voice match score if scored
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**request table** (from Slice 2 spec, extended)
```sql
CREATE TABLE request (
    id            TEXT PRIMARY KEY,
    tool_name     TEXT NOT NULL,
    arguments     TEXT NOT NULL,            -- JSON
    account_id    TEXT REFERENCES accounts(id),
    platform      TEXT,
    status        TEXT DEFAULT 'pending',   -- pending|approved|rejected|timed_out|executing|completed|failed
    result        TEXT,                     -- JSON
    edits         TEXT,                     -- JSON: fields the user modified
    notes         TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    decided_at    TEXT,
    completed_at  TEXT
);
```

---

## 4. Dashboard UI design

### 4.1 Layout

```
+------------------------------------------------------------------+
| LOGO   Inbox(3)  Compose  Accounts  Analytics  Settings   [user] |
+------------------------------------------------------------------+
|                                                                    |
|                     [Active page content]                          |
|                                                                    |
+------------------------------------------------------------------+
```

Top navigation bar with badge counts. No sidebar. Mobile-responsive via CSS grid.

### 4.2 Compose page (the core workflow)

This is where users create and queue posts. Single page, multi-platform.

```
+------------------------------------------------------------------+
| COMPOSE                                                    [Draft]|
+------------------------------------------------------------------+
| Platforms: [x] Facebook  [x] Instagram  [ ] LinkedIn             |
|            [ ] X         [ ] TikTok                               |
|                                                                    |
| Account:   [Dropdown: select page/profile per platform]           |
|            (shows only accounts with write capability)            |
+------------------------------------------------------------------+
| AI Generate:                                                      |
|  Topic: [___________________________________]                     |
|  Provider: [Claude v] [Gemini] [OpenAI] [Custom]                 |
|  Framework: [PAS v] [AIDA] [Story] [Contrarian] [Hook only]     |
|  [Generate]                                                       |
+------------------------------------------------------------------+
| Post content:                                                     |
| +--------------------------------------------------------------+ |
| | [Rich text editor with character count per platform]          | |
| | Facebook: 1247/63206 chars                                    | |
| | Instagram: 1247/2200 chars                                    | |
| |                                                                | |
| | Platform-specific preview tabs:                                | |
| | [Facebook] [Instagram] [LinkedIn] [X] [TikTok]               | |
| +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
| Media:                                                            |
|  [Upload image] [Generate image] [Upload video] [Generate video] |
|  Provider: [DALL-E v] [Gemini] [Nano Banana]                    |
|  (disabled buttons for platforms that don't support the format)   |
+------------------------------------------------------------------+
| Schedule: [Now v] [Pick date/time] [Optimal time]                |
+------------------------------------------------------------------+
| [Score post]  [Save draft]  [Submit for approval]                |
+------------------------------------------------------------------+
```

**Key behaviours:**
- Character count updates live per platform. Warns when content exceeds a platform's limit.
- Platform-specific preview tabs show how the post will look on each channel.
- "Generate" calls the selected AI provider with voice.md context.
- "Score post" runs the post-scorer skill against the user's historical data.
- "Submit for approval" creates one approval request per selected platform. Each can be approved or rejected independently.
- If only one platform is selected and the user has skip-approval enabled for that tool, it publishes immediately with a confirmation dialog: "This will publish immediately without approval. Are you sure?"

### 4.3 Inbox page (approval queue)

From the Slice 2 spec, extended for multi-platform:

```
+------------------------------------------------------------------+
| INBOX                                          [3 pending]        |
+------------------------------------------------------------------+
| +--------------------------------------------------------------+ |
| | [Facebook icon] Post to "Tech News Daily"                     | |
| | "5 AI tools that changed how I work this month..."            | |
| | Submitted 2 min ago                                           | |
| | [Edit] [Approve] [Reject]                                     | |
| +--------------------------------------------------------------+ |
| | [Instagram icon] Post to @techdaily                           | |
| | Same content, adapted for Instagram                           | |
| | Submitted 2 min ago                                           | |
| | [Edit] [Approve] [Reject]                                     | |
| +--------------------------------------------------------------+ |
| | [LinkedIn icon] Post to Tech News Company Page                | |
| | Same content, adapted for LinkedIn                            | |
| | Submitted 2 min ago                                           | |
| | [Edit] [Approve] [Reject]                                     | |
| +--------------------------------------------------------------+ |
```

Each approval card shows:
- Platform icon and account name
- Content preview (truncated, expandable)
- Media thumbnails if attached
- Edit button opens inline editor with platform-specific constraints
- Approve/reject with optional notes
- Bulk approve: select multiple and approve all

At 100 pages, the inbox needs filtering:
- Filter by platform
- Filter by account
- Filter by status
- Sort by submitted time (default) or platform
- "Approve all from [account]" batch action

### 4.4 Accounts page

```
+------------------------------------------------------------------+
| ACCOUNTS                                       [+ Add account]   |
+------------------------------------------------------------------+
| Platform    | Account           | Status    | Posts | Actions     |
|-------------|-------------------|-----------|-------|-------------|
| Facebook    | Tech News Daily   | Connected | 847   | [Manage]    |
| Facebook    | AI Weekly         | Connected | 234   | [Manage]    |
| Instagram   | @techdaily        | Connected | 156   | [Manage]    |
| LinkedIn    | Tech News Co.     | Pending   | 0     | [Auth]      |
| X           | @technews         | No plan   | 0     | [Setup]     |
| TikTok      | @techdaily        | In review | 0     | [Status]    |
+------------------------------------------------------------------+
```

"Add account" starts the OAuth flow for the selected platform. The dashboard handles the callback and stores tokens.

Status values:
- **Connected** - API access working, ready to post
- **Pending review** - App submitted to platform for review (LinkedIn, TikTok)
- **Token expired** - Needs re-authentication
- **No plan** - Platform requires paid tier (X Pro at $200/month)
- **In review** - Application under platform review
- **Disconnected** - User removed access

### 4.5 Analytics page

Cross-platform analytics with normalised metrics:

```
+------------------------------------------------------------------+
| ANALYTICS                          [Last 30 days v] [Export CSV] |
+------------------------------------------------------------------+
| Total reach: 245,892  | Engagement: 12,847  | Posts: 47          |
+------------------------------------------------------------------+
| [Engagement trend chart - all platforms stacked]                  |
+------------------------------------------------------------------+
| Best performing posts:                                            |
| 1. [FB] "5 AI tools..." - 3,421 reactions, 892 comments         |
| 2. [IG] Carousel: "The AI stack" - 2,104 likes, 341 comments    |
| 3. [LI] "Why I stopped..." - 1,872 reactions, 503 comments      |
+------------------------------------------------------------------+
| Platform breakdown:                                               |
| [Facebook chart] [Instagram chart] [LinkedIn chart] [X chart]    |
+------------------------------------------------------------------+
```

### 4.6 Settings page

```
+------------------------------------------------------------------+
| SETTINGS                                                          |
+------------------------------------------------------------------+
| Approval policies:                                                |
|   Post to Facebook:     [Require approval v]                     |
|   Post to Instagram:    [Require approval v]                     |
|   Delete any post:      [Require double confirm v]               |
|   Read insights:        [Auto-approve v]                         |
|                                                                    |
| AI providers:                                                     |
|   OpenAI API key:       [***********xyz]  [Test] [Remove]        |
|   Gemini API key:       [***********abc]  [Test] [Remove]        |
|   Claude API key:       [Using MCP session - no key needed]      |
|   DALL-E:               [Via OpenAI key]                         |
|   Nano Banana API:      [Not configured]  [Add]                  |
|                                                                    |
| Apify token:            [***********def]  [Test] [Remove]        |
|                                                                    |
| Voice system:                                                     |
|   about-me.md:          [Loaded] [View] [Rebuild]                |
|   voice.md:             [Loaded] [View] [Rebuild]                |
|   newsletter-voice.md:  [Not found] [Build]                     |
|                                                                    |
| Default schedule:                                                 |
|   Facebook:  [09:00 v] [13:00] [18:00] (3x daily)               |
|   Instagram: [11:00 v] [19:00] (2x daily, within 25/day limit)  |
|   LinkedIn:  [08:00 v] [17:00] (2x daily)                       |
+------------------------------------------------------------------+
```

---

## 5. Automation workflow

### 5.1 Content creation pipeline

```
Topic/idea
    |
    v
[Voice engine loads about-me.md + voice.md]
    |
    v
[AI provider generates draft]
  - Claude (via MCP, free with subscription)
  - OpenAI GPT-4o (API key, ~$0.01 per post)
  - Gemini 2.5 Flash (API key, free tier available)
    |
    v
[Platform adapter adjusts per channel]
  - Facebook: full text, links expanded
  - Instagram: 2200 char max, no links in caption, hashtags
  - LinkedIn: professional tone adjustment, 3000 char max
  - X: 280 char limit, thread if longer
  - TikTok: script format for video, 150 char caption
    |
    v
[Post scorer validates quality]
  - Score against user's historical top performers
  - Flag voice mismatches
  - Suggest hook improvements with data
    |
    v
[Media generation if needed]
  - Image: DALL-E, Gemini, Nano Banana
  - Video: ElevenLabs (voice) + HeyGen (avatar) + Remotion (motion)
  - Graphic: HTML/CSS structured or AI infographic
    |
    v
[Approval queue]
  - One request per platform per account
  - User reviews, edits, approves/rejects each
  - Dashboard shows preview per platform
    |
    v
[Platform router publishes]
  - Respects rate limits per platform
  - Retries on transient failures
  - Records platform post ID for tracking
    |
    v
[Analytics collection begins]
  - Polls insights at 1hr, 24hr, 7d intervals
  - Feeds back into scorer for future posts
```

### 5.2 Batch workflow (scaling to 100 pages)

When managing many pages, the compose workflow changes:

1. **Template mode:** Write one post, select 10 accounts. The system creates 10 platform-adapted variants.
2. **Batch approval:** Inbox groups related posts. "Approve all 10 variants" button.
3. **Staggered publishing:** Posts go out at different times to avoid looking automated. Configurable jitter (5 to 60 minutes between posts).
4. **Rate limit awareness:** The scheduler checks remaining API quota before queuing. If Instagram has 3 publishes left today across 5 accounts, it queues the rest for tomorrow.
5. **Priority accounts:** Mark high-value accounts as priority. These get published first when rate limits are tight.

### 5.3 Approval system design

The approval system must handle the tension between "every post requires approval" and "100 pages."

**Approval tiers (per tool, per account):**

| Tier                | Behaviour                                              | Use case                        |
|---------------------|--------------------------------------------------------|---------------------------------|
| `require_approval`  | Queued, waits for human approve/reject                 | Default for all write actions   |
| `approve_confirm`   | Queued, requires approve + "are you sure" confirmation | Delete, bulk operations         |
| `auto_approve`      | Executes immediately, logged in history                | Read operations, insights pulls |
| `skip_approval`     | Executes immediately with warning banner               | Power users, trusted automation |

**Skip-approval safeguards:**
- Enabling skip_approval shows a permanent warning banner: "Approval is disabled for [tool] on [account]. Posts will publish immediately."
- First post after enabling skip shows a one-time interstitial: "This post will publish to [platform] without review. Content: [preview]. Publish now?"
- Skip-approval can be set per tool per account, not globally. You can skip approval for Facebook reads but still require it for Facebook posts.
- Audit log records every skip-approval action with full content snapshot.

**At scale (50+ accounts):**
- Batch approve with content preview carousel
- "Approve all similar" groups posts from the same template
- Daily digest email: "You have 47 posts pending approval across 12 accounts"
- Auto-reject after configurable timeout (default 72 hours) with notification
- Dashboard shows approval SLA: average time from submit to decision

---

## 6. AI provider integration

### 6.1 Provider matrix

| Provider       | Capability        | Cost model          | Best for                          |
|----------------|-------------------|---------------------|-----------------------------------|
| Claude (MCP)   | Text generation   | Included with sub   | Voice-matched posts, long form    |
| OpenAI GPT-4o  | Text generation   | ~$0.01/post         | Bulk generation, threads          |
| Gemini 2.5     | Text + video      | Free tier + paid    | Video analysis, image gen         |
| DALL-E 3       | Image generation  | $0.04-0.12/image    | Post graphics, thumbnails         |
| Nano Banana*   | Image generation  | Per-image pricing   | Alternative image styles          |
| ElevenLabs     | Voice synthesis   | Per-character        | Reel voiceovers                   |
| HeyGen         | Avatar video      | Subscription        | Talking head videos               |

### 6.2 Provider selection logic

```python
def select_provider(task: str, user_preference: str = None) -> str:
    if user_preference:
        return user_preference
    
    # Default routing
    if task == "text_generation":
        return "claude"           # Best voice matching via MCP context
    elif task == "image_generation":
        return "dall-e"           # Most reliable for structured prompts
    elif task == "video_analysis":
        return "gemini-2.5-flash" # Native video understanding
    elif task == "voice_synthesis":
        return "elevenlabs"       # Highest quality TTS
    elif task == "infographic":
        return "gemini"           # Best for whiteboard/branded styles
```

The user can override this per-post via the compose page dropdown.

### 6.3 Voice system integration

Every AI text generation call includes voice context:

1. Load `about-me.md` (who, audience, topics, POV, brand promise, off-limits)
2. Load `voice.md` (tone, rhythm, hooks, signature phrases, absence signals)
3. Load `newsletter-voice.md` if the content originates from newsletter repurposing
4. Inject as system context for the AI provider
5. Post-generation: run scorer to verify voice match before queuing

Claude has a natural advantage here because the voice files are already in the MCP project context. For OpenAI/Gemini, the voice content is injected into the system prompt.

---

## 7. Per-platform post examples

### 7.1 Facebook post

```
Input topic: "5 AI tools I replaced my marketing team with"

Generated post:
-----------------------------------------------
Last month I cancelled three software subscriptions
and replaced them with AI tools that cost $47/month total.

Here is what changed:

1. Content calendar: ChatGPT + a custom prompt
   replaced a $200/month planning tool
2. Social graphics: Gemini image generation
   replaced a $50/month design subscription
3. Email sequences: Claude projects
   replaced a copywriter retainer
4. Analytics reports: Custom GPT
   replaced manual spreadsheet work
5. Video captions: Whisper API
   replaced a transcription service

Total before: $1,240/month
Total after: $47/month

The tools are not the point.
The point is knowing which tasks
AI actually does better than humans.

What would you replace first?
-----------------------------------------------
Platform: Facebook
Format: Text post
Character count: 612/63,206
Hashtags: None (Facebook penalises hashtag-heavy posts)
Media: Optional HTML/CSS infographic with the cost comparison
```

### 7.2 Instagram post

```
Adapted from same topic:
-----------------------------------------------
I replaced 5 marketing tools with AI.

Monthly cost went from $1,240 to $47.

Here is the swap list:

1. Content calendar: ChatGPT custom prompt
2. Social graphics: Gemini
3. Email sequences: Claude
4. Analytics: Custom GPT
5. Video captions: Whisper

The tools change every month.
The skill of knowing what to automate does not.

Save this for when you are ready to cut costs.

#AItools #marketingautomation #contentcreation
-----------------------------------------------
Platform: Instagram
Format: Carousel (each tool = 1 slide) or single image
Character count: 418/2,200
Hashtags: 3-5 relevant tags (Instagram algorithm favours fewer, targeted hashtags)
Media: Branded infographic or carousel slides
CTA: "Save this" (Instagram's algorithm rewards saves)
```

### 7.3 LinkedIn post

```
Adapted from same topic:
-----------------------------------------------
I cut $1,193/month from my marketing stack last month.

Not by finding cheaper tools.
By replacing them with AI that costs $47/month total.

The 5 swaps:

Content calendar: $200/month tool replaced with ChatGPT + a structured prompt
Social graphics: $50/month design sub replaced with Gemini image generation
Email copy: Copywriter retainer replaced with Claude projects
Analytics: Manual spreadsheets replaced with a Custom GPT
Video captions: Transcription service replaced with Whisper API

Here is what surprised me:

The AI versions are not just cheaper.
Three of them produce better output than what I was paying for.

The other two are 80% as good at 5% of the cost.

Knowing which is which is the actual skill.

What is the first tool you would swap?
-----------------------------------------------
Platform: LinkedIn
Format: Text post
Character count: 682/3,000
Hashtags: None (LinkedIn organic reach drops with hashtags in 2026)
Media: Optional
CTA: Question to drive comments
```

### 7.4 X post

```
Adapted from same topic:
-----------------------------------------------
Replaced 5 marketing tools with AI.

$1,240/month -> $47/month

The surprising part: 3 of the AI versions
produce better output than what I was paying humans for.

Thread with the full swap list:
-----------------------------------------------
Platform: X
Format: Tweet (thread opener)
Character count: 201/280
Thread: 5 follow-up tweets, one per tool swap
Media: None for opener, screenshot per thread tweet
```

### 7.5 TikTok script

```
Adapted from same topic:
-----------------------------------------------
# Reel: 5 AI Tools That Replaced My Marketing Team

## Duration target
30-35 seconds

## Hook (0-3s)
"This $47 AI stack replaced $1,240 in marketing tools."

## Point 1 (3-18s)
"The first three swaps actually produce better work.
ChatGPT replaced my content calendar.
Gemini replaced my design subscription.
Claude replaced my email copywriter.
All three, better output, fraction of the cost."

## Point 2 (18-28s)
"The other two are 80% as good at 5% of the price.
That is the real skill here.
Knowing which tasks AI does better
and which ones just need to be cheaper."

## CTA (28-35s)
"Comment STACK and I will send you the full swap list
with the exact prompts I use."

## Comment trigger
STACK
-----------------------------------------------
Platform: TikTok
Format: Video (talking head or screen recording)
Duration: 30-35 seconds
Caption: Mirror of script, 150 chars max for preview
```

---

## 8. Advertising and ad creation

Ad creation was part of the original requirements. This section documents what the platform APIs offer and what this platform will support.

### 8.1 Platform advertising APIs

| Platform  | Ads API                          | Access requirements                        | Capabilities via API                                        |
|-----------|----------------------------------|--------------------------------------------|-------------------------------------------------------------|
| Facebook  | Meta Marketing API               | Marketing API access via Business Manager   | Create/manage campaigns, ad sets, ads. Audience targeting. Budget management. Performance reporting. |
| Instagram | Meta Marketing API (same as FB)  | Same access as Facebook                    | Same as Facebook, scoped to Instagram placements             |
| LinkedIn  | LinkedIn Ads API                 | Marketing Developer Platform approval       | Sponsored Content, Message Ads, campaign management, reporting |
| X         | X Ads API                        | Separate from content API, requires approval| Promoted tweets, campaign management, audience targeting     |
| TikTok    | TikTok Marketing API             | Separate app review, TikTok Business Center | Campaign creation, ad management, audience tools, reporting  |

### 8.2 What this platform will support (v1)

Ad creation is deferred to Phase 6 with limited scope:

- **"Boost top performer" workflow:** One-click promotion of an organic post that exceeded engagement thresholds. Uses Meta Marketing API for Facebook/Instagram. This is the simplest ads integration and delivers the most value.
- **Budget guardrails:** Hard spending cap per boost, configurable in settings. Default $50. Approval queue applies to all ad spend.
- **Performance dashboard:** Pull ad performance metrics into the analytics page alongside organic metrics.

### 8.3 What is explicitly out of scope for v1

- Full campaign builders for any platform (use each platform's native ads manager instead)
- Audience creation and lookalike targeting
- A/B testing ad creative
- Cross-platform ad budget optimisation
- LinkedIn, X, and TikTok ad creation (only Meta boosting in v1)

Full multi-platform ad management is a separate product. This platform focuses on organic content publishing with a "boost what works" shortcut for Meta platforms. Expanding ads support to other platforms would be a Phase 7+ initiative after the core content system is stable.

---

## 9. Skill-to-component mapping

The `social-media-skills` project already implements most of the content pipeline. This table maps each existing skill to where it fits in the platform architecture, avoiding redundant development.

| Skill               | Platform component          | Integration approach                                                        |
|----------------------|-----------------------------|-----------------------------------------------------------------------------|
| voice-builder        | content/voice.py            | Core dependency. Produces about-me.md + voice.md that every generation call loads. |
| newsletter-voice     | content/voice.py            | Extension of voice engine. Loaded when repurposing newsletter content.      |
| post-writer          | content/generator.py        | 4 frameworks (PAS, How-to, Story, Contrarian) become selectable in compose page. |
| post-formatter       | content/generator.py        | Additional frameworks (AIDA, BAB, STAR, SLAY) added to compose dropdown.   |
| hook-generator       | content/hooks.py            | Standalone module. Called from compose page "Generate hooks" button.        |
| post-scorer          | content/scorer.py           | Standalone module. Called from compose page "Score post" button.            |
| graphic-designer     | media/image_gen.py          | HTML/CSS path runs server-side. AI prompt path feeds into image gen.        |
| gemini-infographic   | media/image_gen.py          | Whiteboard prompt template. Selectable in compose media section.           |
| gemini-carousel      | media/image_gen.py          | Carousel generator with approval gate. Maps to Instagram carousel format.  |
| quote-post           | media/image_gen.py          | Quote + image pipeline. Option in compose for quote-style posts.           |
| reels-scripting      | content/generator.py + media/video_gen.py | Apify scrape + Gemini analysis + script writing. Full workflow in compose. |
| youtube-thumbnail    | media/image_gen.py          | Thumbnail prompt builder. Relevant for video posts across platforms.       |
| niche-research       | content/research.py         | Browser-driven research. Dashboard research page triggers it.              |
| content-matrix       | content/generator.py        | Pillar x format ideation. Dashboard feature for content planning.          |
| analytics-dashboard  | analytics/collector.py      | React dashboard logic migrates to the platform analytics page.             |
| profile-optimizer    | Not directly integrated     | Standalone skill. Accessible via MCP but not embedded in dashboard.        |
| pinned-comment       | Not directly integrated     | Standalone skill. Accessible via MCP but not embedded in dashboard.        |

**Key insight:** 15 of 17 skills map directly to platform components. The content pipeline is already built in skill form. The platform wraps these skills in a dashboard UI, adds multi-platform adapters, and connects them through the approval queue.

---

## 10. Implementation roadmap

### Phase 1: Foundation (weeks 1-3)

**Goal:** Multi-platform adapter layer + dashboard shell

- [ ] Refactor `facebook_api.py` into `adapters/facebook.py` implementing `PlatformAdapter`
- [ ] Build `adapters/instagram.py` (shares Facebook Graph API, different endpoints)
- [ ] Build adapter stubs for LinkedIn, X, TikTok (with clear "not yet configured" states)
- [ ] Migrate approval queue from Slice 2 spec into `approval/` module
- [ ] Build dashboard shell: FastAPI + HTMX, accounts page, settings page
- [ ] SQLite schema: accounts, posts, request, tool_policy tables
- [ ] Account management: add/remove accounts, store tokens, test connections

**Deliverable:** Dashboard where you can connect Facebook + Instagram accounts and see them listed. Approval queue working for Facebook posts.

### Phase 2: Content generation (weeks 4-6)

**Goal:** Multi-AI content creation in the dashboard

- [ ] Voice engine: load and parse about-me.md + voice.md
- [ ] Content generator: Claude (MCP), OpenAI, Gemini text generation
- [ ] Compose page with multi-platform preview
- [ ] Platform content adaptation (character limits, hashtag rules, format constraints)
- [ ] Hook generator integration (6 types from hook-generator skill)
- [ ] Post scorer integration (5 criteria from post-scorer skill)
- [ ] Image generation: DALL-E + Gemini prompt builder
- [ ] Graphic designer: HTML/CSS path integrated into compose

**Deliverable:** Write a post in the dashboard, generate it with AI, score it, preview per platform, submit for approval.

### Phase 3: Publishing + scheduling (weeks 7-9)

**Goal:** Approved posts actually publish

- [ ] Facebook publishing (text, image, video)
- [ ] Instagram publishing (photo, carousel, reel)
- [ ] Scheduler: cron-style with optimal time suggestions
- [ ] Rate limit tracking and enforcement per platform per account
- [ ] Staggered publishing for batch operations
- [ ] Retry logic for transient API failures
- [ ] Post status tracking: draft to published pipeline in the database

**Deliverable:** End-to-end flow: compose, approve, publish, verify.

### Phase 4: Scale + remaining platforms (weeks 10-14)

**Goal:** 100-page support + LinkedIn, X, TikTok

- [ ] LinkedIn adapter (once Marketing Developer Platform approval received)
- [ ] X adapter (once Pro tier subscription activated)
- [ ] TikTok adapter (once Content Posting API approval received)
- [ ] Batch compose: one post to N accounts
- [ ] Batch approval: approve groups of related posts
- [ ] Priority accounts and rate limit arbitration
- [ ] Template system: save and reuse post templates across accounts

**Deliverable:** All five platforms publishing. Batch operations working across 10+ accounts.

### Phase 5: Analytics + intelligence (weeks 15-18)

**Goal:** Cross-platform insights and automated optimisation

- [ ] Analytics collector: pull insights from all connected platforms
- [ ] Normalised metrics schema for cross-platform comparison
- [ ] Analytics dashboard page with charts (Recharts or Chart.js via CDN)
- [ ] Niche research integration (Apify-backed trend scanning)
- [ ] Content matrix: pillar x format ideation in the dashboard
- [ ] Reels scripting workflow: reference reel analysis to script
- [ ] Feedback loop: publish results improve future scoring

**Deliverable:** Full analytics dashboard. AI-driven content suggestions based on what performs.

### Phase 6: Advanced automation (weeks 19-24)

**Goal:** Hands-off operation for power users

- [ ] Comment management: auto-reply templates, sentiment filtering
- [ ] Ad creation workflow: "boost top performer" via Meta Marketing API (see 8)
- [ ] Cross-posting intelligence: learn which content works on which platform
- [ ] Video pipeline: ElevenLabs + HeyGen + Remotion integration
- [ ] Notification system: email/Slack alerts for pending approvals, performance milestones
- [ ] Multi-user support: team roles (creator, approver, admin)

**Deliverable:** Platform runs with minimal daily attention. AI suggests, human approves, system publishes.

---

## 11. Technical decisions

### 11.1 Why not a SPA?

- No build step. Jinja2 + HTMX is deployable with `pip install` and no Node.js.
- SSE for real-time updates is simpler than WebSocket state management.
- The dashboard is a local tool for one user, not a public web app. Server-rendered is fine.
- The existing Slice 2 spec already chose this stack.

### 11.2 Why SQLite?

- Zero configuration. No database server to install.
- Single file, easy to back up.
- WAL mode handles concurrent reads from dashboard + MCP server.
- At 100 accounts with 10 posts/day each, we are at ~1000 rows/day. SQLite handles millions.

### 11.3 Why adapters over a unified API?

Each platform's API is different enough that a generic abstraction leaks. The adapter pattern lets each platform implement its own quirks (Instagram's container-based publishing, TikTok's inbox method, LinkedIn's URN-based entity system) while the dashboard code only calls the common interface.

### 11.4 Token security

- Access tokens stored encrypted in SQLite (Fernet symmetric encryption, key derived from a user-provided master password or machine-specific secret).
- Tokens never logged in approval queue history.
- Refresh token rotation handled per platform's OAuth spec.
- `.env` file for API keys (OpenAI, Gemini, Apify) with `.gitignore` protection.

---

## 12. Risks and mitigations

| Risk                                          | Impact  | Mitigation                                                                 |
|-----------------------------------------------|---------|----------------------------------------------------------------------------|
| LinkedIn app review rejected or delayed       | High    | Manual posting fallback. Prepare app submission documentation early.       |
| TikTok app review rejected                    | Medium  | Inbox method (user confirms in app) as permanent fallback.                |
| X Pro tier cost ($200/month) rejected by user | Low     | X integration is optional. Dashboard works without it.                    |
| Instagram 25 publish/day limit hit            | High    | Rate limit tracking. Queue overflow to next day. Priority account system. |
| AI provider API outage                        | Medium  | Multiple providers. Fallback chain: Claude -> OpenAI -> Gemini.          |
| Token expiry during batch publish             | Medium  | Pre-flight token validation. Auto-refresh where supported.               |
| 100 accounts overwhelms approval inbox        | High    | Batch approve, filters, templates, skip-approval option with safeguards. |
| Voice drift across AI providers               | Medium  | Post-scorer validates voice match. Flag mismatches before approval.      |

---

## 13. Dependencies and prerequisites

**Required before Phase 1:**
- Python 3.11+
- Facebook Developer App with Page Access Token
- Instagram Professional Account linked to Facebook Page

**Required before Phase 2:**
- At least one AI provider API key (OpenAI, Gemini, or Claude via MCP)
- Voice system built (run voice-builder skill)

**Required before Phase 4:**
- LinkedIn Marketing Developer Platform application submitted
- X API Pro tier subscription ($200/month)
- TikTok Developer Account with Content Posting API application submitted
- Apify API token (for research and scraping features)

**Optional (enhances but not required):**
- ElevenLabs API key (voice synthesis for video)
- HeyGen account (avatar video generation)
- Nano Banana API key (alternative image generation)*
- GOOGLE_AI_API_KEY (Gemini 2.5 Flash for video analysis)

---

## 14. Success criteria

The platform is complete when a user can:

1. Connect accounts across all five platforms from the dashboard
2. Write one post and publish adapted versions to all connected platforms
3. Generate post content using any of three AI providers with voice matching
4. Generate images using DALL-E or Gemini from the compose page
5. Score any draft against real historical performance data
6. Review and approve every post before it publishes (or consciously skip approval)
7. Schedule posts at optimal times per platform
8. Manage 100 accounts without the approval queue becoming unusable
9. View cross-platform analytics in a single dashboard
10. Research trending topics and generate content ideas from the dashboard

---

*\* Nano Banana is user-mentioned and not yet evaluated. The pricing model and API availability have not been verified. Treat as a placeholder until confirmed.*

*This document is the integration master plan. Each phase will produce its own detailed spec as implementation begins. The Slice 2 approval-queue spec is the first such detailed spec and fits inside Phase 1 of this roadmap.*
