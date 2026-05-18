---
name: socialblast-pipeline
description: >
  Plan and create a week of social media content for any business using
  SocialBlast AI's MCP tools. Use this skill when the user says "create a
  campaign", "generate a week of content", "make me posts for my business",
  "plan content for", or asks Claude to enrich pending posts with AI media.
  Drives the SocialBlast MCP toolkit (campaign generation, post enrichment,
  virality prediction, queue inspection) end-to-end while respecting the
  approval queue spine.
---

# SocialBlast Pipeline

## What this skill does

Given a one-sentence business description, you produce a 7-day social media
campaign with AI captions, optional AI images, optional AI videos, and an
optional virality score. Every output goes into the approval queue — no
post ever publishes without the human pressing Approve. This is not
optional. It is the architectural spine.

## Tool surface

You have these MCP tools from `server.py`:

| Tool | Purpose |
|---|---|
| `socialblast_status` | Read which backends and platforms are configured |
| `socialblast_generate_campaign(business_description, platforms)` | Create 7 pending posts per platform from a single sentence |
| `socialblast_enrich_post(post_id, with_video=False)` | Run caption -> image (+ optional video) on one pending post |
| `socialblast_enrich_campaign(group_id, with_video=False)` | Batch enrich every pending post in a campaign |
| `socialblast_predict_virality(prompt, platform)` | Score a caption (requires HiggsField) |
| `socialblast_list_pending` | Read-only queue inspector |

The legacy `post_to_facebook`, `get_page_posts`, and 30+ other Facebook tools
are available too, but you should not call publish-style tools directly. The
approval queue is the only path to live.

## Workflow

### Step 1 — Check what's connected

Always start with `socialblast_status`. Tell the user what they have and what
they are missing. If `video.active_backend` is `none` and `images.replicate`
is also false, only captions will work. Be honest about that.

### Step 2 — Get the business sentence

Ask one question:

> What does your business do? One sentence is enough. For example:
> "Coffee shop in London that roasts in-house."

Wait for the answer. Do not generate placeholder content if the user has
not answered.

### Step 3 — Confirm platforms

Default to all five broadcast platforms: facebook, instagram, threads,
linkedin, tiktok. Show the user the list and let them remove platforms
they do not want. Skip WhatsApp unless they ask (it is direct-message,
not broadcast).

### Step 4 — Generate the campaign

Call `socialblast_generate_campaign(business_description, platforms)`. The
response includes:
- `group_id` — keep this, you need it for enrichment
- `count` — total posts created (7 days × platforms)
- `preview` — first three captions, for showing the user

Show the user the three preview captions immediately. Do not show all 7 —
the wizard shows the rest in its result feed when they visit /wizard.

### Step 5 — Offer to enrich (optional)

Ask:

> Want me to also generate AI images for each post? It costs a few credits
> per image but makes the queue much more impressive.
>
> Add AI videos too? Slower (about a minute per post) and more expensive
> but the result is cinema-quality.

If yes to images only: `socialblast_enrich_campaign(group_id, with_video=False)`
If yes to videos too: `socialblast_enrich_campaign(group_id, with_video=True)`

Each call returns counts of how many enrichment steps succeeded.

### Step 6 — Score virality (if HiggsField is active)

Check the status from step 1. If `video.active_backend == "higgsfield"`, then
the virality predictor is available. Loop over the previews and call
`socialblast_predict_virality(caption, platform="instagram")`. Show the user
which captions scored highest.

### Step 7 — Hand off to the human

Tell the user:

> Done. {count} posts are waiting in your approval queue at
> http://localhost:8501/. Click Publish on each one to send it live, or
> Reject to discard. Nothing publishes without you pressing Approve — that
> is by design.

## Rules

1. **Never publish.** Even if the user asks "just post it for me", refuse and
   explain the approval queue is the safety story. Send them to the inbox.
2. **Be honest about configuration.** If HiggsField is not configured, do not
   pretend you can generate videos. Run `socialblast_status` first.
3. **British English.** No em dashes. No semicolons in prose.
4. **One sentence is enough.** Do not interrogate the user with a five-question
   form. The whole point of the wizard is that one sentence works.
5. **Show, do not promise.** When you tell the user about preview captions,
   paste the actual captions. When you tell them about virality, paste the
   actual score.

## When this skill does not apply

- The user wants to publish a single ad-hoc post — direct them to the
  compose form on the inbox, not the wizard.
- The user wants to manage existing posts (edit, reject, reschedule) —
  use the standard inbox actions, not this skill.
- The user is asking about analytics — that is a separate skill.
