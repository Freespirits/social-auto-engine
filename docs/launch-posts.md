# Launch posts — copy-paste and submit

All posts below are ready to go. Each one targets a different audience.
Post them all on the same day for maximum signal overlap.

---

## 1. Show HN (Hacker News)

**Where:** https://news.ycombinator.com/submit
**Why:** Single biggest source of developer traffic on the internet. One front-page hit = 10K-50K visits in 24 hours.

**Title (max 80 chars):**
```
Show HN: Open-source social media manager with AI video gen and human approval queue
```

**URL:** `https://github.com/Freespirits/social-auto-engine`

**First comment (post this immediately after submitting):**

```
Hey HN — I built Social Auto Engine because every social media tool I tried
was either great at scheduling but terrible at content (Buffer, Hootsuite),
or great at AI drafts but couldn't actually post anywhere (Jasper, Copy.ai).

This is the missing middle:

- 5 platforms live (Facebook, Instagram, WhatsApp, Threads, LinkedIn),
  TikTok and YouTube code-complete awaiting their app reviews
- 7 AI services for content generation (text, image, video)
- 37 MCP tools so Claude can manage your social media directly
- Every single write action goes through a human approval queue.
  Nothing publishes without a human pressing Approve.

Stack: FastAPI + HTMX + Jinja2 + SQLite. No SPA, no Node.js, no build step.
pip install and you're running in 60 seconds.

Live demo (read-only, dummy data):
https://huggingface.co/spaces/Warpfreespirit/social-auto-engine

Marketing site with AI-generated video demos:
https://freespirits.github.io/social-auto-engine/

The AI video generation (via HiggsField) is genuinely mind-blowing.
You upload a face photo and it generates cinema-quality video clips
of that person in any scene. Combined with the approval queue,
an agency could produce a week of social content in an hour.

Looking for contributors — especially someone who's been through
TikTok's developer app review process. MIT licensed.
```

---

## 2. Reddit — r/selfhosted

**Where:** https://www.reddit.com/r/selfhosted/submit
**Why:** 500K+ members who specifically want self-hosted alternatives to SaaS.

**Title:**
```
I built an open-source, self-hosted alternative to Buffer/Hootsuite with AI video generation and a human approval queue
```

**Body:**

```
Been building this for a few months. It's called Social Auto Engine.

What it does:
- Post to Facebook, Instagram, WhatsApp, Threads, LinkedIn from one dashboard
- AI drafts text, generates images, and creates video (HiggsField, ElevenLabs, Deepgram, etc.)
- Every post goes through an approval queue — nothing publishes without you clicking Approve
- 37 MCP tools for Claude integration (you can literally say "schedule a post about X for Thursday" and it does it)

Stack: Python, FastAPI, HTMX, SQLite. No Docker required (though there's a Dockerfile). No external DB. No build step.

git clone → pip install → python -m dashboard.app → done.

It's MIT licensed, self-hosted, all data stays on your machine. No telemetry, no analytics, no SaaS dependency.

GitHub: https://github.com/Freespirits/social-auto-engine
Live demo: https://huggingface.co/spaces/Warpfreespirit/social-auto-engine
Site: https://freespirits.github.io/social-auto-engine/

Looking for contributors if anyone's interested. The TikTok and YouTube adapters are code-complete but stuck in app review hell.
```

---

## 3. Reddit — r/opensource

**Where:** https://www.reddit.com/r/opensource/submit
**Why:** 200K+ members, specifically interested in new open-source projects.

**Title:**
```
Social Auto Engine — open-source social media manager with AI content generation (MIT, Python, no SaaS dependency)
```

**Body:**

```
Just shipped the public demo of Social Auto Engine, an open-source social media management tool.

The core idea: AI drafts your content, you approve it, the system publishes it. No silent automation.

- 5 platforms live (Facebook, IG, WhatsApp, Threads, LinkedIn)
- 7 AI services (text gen, image gen, video gen via HiggsField)
- 37 MCP tools for Claude Desktop/Code integration
- Human approval queue as the safety spine

Self-hosted. SQLite. No build step. MIT licensed.

Demo: https://huggingface.co/spaces/Warpfreespirit/social-auto-engine
GitHub: https://github.com/Freespirits/social-auto-engine

Happy to answer any questions. Looking for contributors — especially anyone familiar with TikTok's developer review process.
```

---

## 4. Reddit — r/artificial

**Where:** https://www.reddit.com/r/artificial/submit
**Why:** 1M+ members interested in AI applications.

**Title:**
```
I connected 7 AI services (HiggsField, ElevenLabs, Deepgram, etc.) to a social media dashboard with a human-in-the-loop approval queue. Here's what I learned.
```

**Body:**

```
The project is Social Auto Engine — an open-source tool that connects AI content generation to social media publishing, with a mandatory human approval step.

The AI stack:
- HiggsField: Video generation from face photos. This is the standout. You upload a photo and it generates cinema-quality video of that person in any scene. Expensive but mind-blowing.
- ElevenLabs: Voice synthesis for video narration
- Deepgram: Speech-to-text for caption generation
- OpenAI / Anthropic: Text drafting in the user's voice
- FAL / Replicate: Image generation

The key design decision: every AI-generated piece of content lands in an approval queue. A human reviews it. Only then does it publish. This isn't a setting you can turn off — it's baked into the architecture.

Why: because AI-generated social media content without human oversight is how brands get destroyed. The approval queue is the product.

GitHub: https://github.com/Freespirits/social-auto-engine
Live demo: https://huggingface.co/spaces/Warpfreespirit/social-auto-engine

It's MIT licensed and self-hosted. All data stays on your machine.
```

---

## 5. Dev.to article

**Where:** https://dev.to/new
**Why:** Developer blog platform with built-in audience. Articles get indexed by Google and show up in dev search results for years.

**Title:**
```
I built an open-source Buffer alternative with AI video generation and 37 Claude MCP tools
```

**Tags:** `opensource`, `python`, `ai`, `webdev`

**Body:**

```markdown
## The problem

Every social media tool I tried fell into one of two camps:

1. **Schedulers** (Buffer, Hootsuite, Later) — great at queuing posts, terrible at helping you create content. You still write everything yourself.
2. **AI writers** (Jasper, Copy.ai) — great at generating drafts, terrible at getting them published. They don't connect to your accounts.

I wanted the missing middle: AI that drafts in my voice, connected to every platform, with a human approving every post before it goes live.

## What I built

**Social Auto Engine** — an open-source, self-hosted social media management dashboard.

### The stack

- **Backend:** Python 3.11, FastAPI, SQLite (WAL mode)
- **Frontend:** Jinja2 + HTMX (no SPA, no Node.js, no build step)
- **AI services:** 7 providers (HiggsField for video, ElevenLabs for voice, OpenAI/Anthropic for text)
- **Platforms:** Facebook, Instagram, WhatsApp, Threads, LinkedIn (live). TikTok + YouTube (code-complete, in app review).

### The safety spine

Every write action goes through a human approval queue. This is architectural, not a toggle. The flow is always:

1. AI (or human) composes a draft
2. Draft lands in the queue with status "pending"
3. A human reviews and approves
4. The system publishes

### The MCP server

The project ships with 37 MCP tools for Claude Desktop and Claude Code. You can literally type:

> "Schedule a post about our new product launch for Thursday at 2pm on Facebook and Instagram"

...and Claude composes the post, selects the platforms, and drops it into your approval queue. You approve with one click.

## Try it

**Live demo (read-only):** [huggingface.co/spaces/Warpfreespirit/social-auto-engine](https://huggingface.co/spaces/Warpfreespirit/social-auto-engine)

**Marketing site:** [freespirits.github.io/social-auto-engine](https://freespirits.github.io/social-auto-engine/)

**Get started in 60 seconds:**

```bash
git clone https://github.com/Freespirits/social-auto-engine.git
cd social-auto-engine
pip install -r requirements.txt
cp .env.example .env
python -m dashboard.app
```

Opens at http://127.0.0.1:7651.

## What's next

- TikTok app review (got declined once, reapplying with a better demo video)
- YouTube OAuth consent screen verification
- Company assets folder — upload your brand kit (logos, team photos) and the AI uses them across all generated content
- X/Twitter adapter (waiting on API cost justification)

**GitHub:** [github.com/Freespirits/social-auto-engine](https://github.com/Freespirits/social-auto-engine)

MIT licensed. Contributors welcome. Come build with us.
```

---

## 6. Twitter/X post

**Where:** Your personal account or project account.

```
I built an open-source alternative to Buffer with AI video generation.

- 5 platforms live
- 7 AI services
- 37 Claude MCP tools
- Human approval queue (no silent automation)

Self-hosted. MIT licensed. No SaaS dependency.

Demo: https://freespirits.github.io/social-auto-engine/
GitHub: https://github.com/Freespirits/social-auto-engine

Looking for contributors 🔧
```

---

## 7. LinkedIn post

**Where:** Your LinkedIn profile.

```
I've been building Social Auto Engine — an open-source social media management tool that connects AI content generation to every major platform.

The core idea: AI drafts your social media content (text, images, video), you approve it, the system publishes it. Nothing goes live without a human pressing Approve.

What's live today:
→ Facebook, Instagram, WhatsApp, Threads, LinkedIn publishing
→ 7 AI services including HiggsField (AI video generation — this one is a game changer)
→ 37 MCP tools for Claude integration
→ Self-hosted, MIT licensed, no SaaS lock-in

What's next:
→ TikTok and YouTube (code done, in platform review)
→ Company brand kit folder (upload logos + team photos, AI uses them in generated content)

For agencies managing multiple brands, this could replace 3-4 separate tools.

Try the live demo: https://huggingface.co/spaces/Warpfreespirit/social-auto-engine
GitHub: https://github.com/Freespirits/social-auto-engine

Looking for contributors — especially anyone who's navigated TikTok's developer review process.

#opensource #socialmedia #AI #python
```

---

## Posting order (same day)

1. **Show HN** first (morning, US Pacific time for best visibility)
2. **Dev.to article** second (takes 10 min to format, do it while HN is gaining traction)
3. **Reddit posts** — space them 30 min apart to avoid spam filters
4. **LinkedIn** and **Twitter** — share the HN link and dev.to article
5. **Facebook post** on your own page (use Social Auto Engine to post it, screenshot that for meta points)

---

## After posting

- Reply to every comment within the first 2 hours (HN and Reddit rank based on engagement)
- If someone asks a technical question, answer in detail — helpful replies build reputation
- Do NOT ask friends to upvote (HN detects vote rings and kills the post)
- Do NOT post the same link to multiple subreddits at the same time (Reddit flags this as spam)
