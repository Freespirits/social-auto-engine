# Integrations & accelerators

Curated list of open-source projects that can accelerate Social Auto Engine. These aren't dependencies yet — they're a shortlist of "if we want X, here's the project that already solved it."

Last updated: 2026-05-02

## Top 3 — if we could only pick three

1. **[Postiz](https://github.com/gitroomhq/postiz-app)** — direct competitor, ~22k stars. Study their provider abstraction layer end-to-end before designing ours.
2. **[CRUDAdmin](https://github.com/benavlabs/crudadmin)** — FastAPI + HTMX admin with auth and event tracking. Drop in over our SQLite tables and ship the accounts/posts CRUD weeks earlier.
3. **[python-statemachine](https://github.com/fgmacedo/python-statemachine)** — replaces our string status flags with a proper state machine: `draft → pending → approved → scheduled → posted → failed`. Has a literal `ApprovalWorkflow` example.

---

## Open-source social media schedulers

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | ~22k | AGPL-3.0 | Direct competitor; supports 30+ platforms with AI scheduling | Study provider abstraction & approval/team UX patterns |
| [inovector/mixpost](https://github.com/inovector/mixpost) | ~2.1k | MIT (Lite) | Self-hosted Buffer alternative, Laravel | Mirror multi-account/workspace data model and media-library schema |
| [growchief/growchief](https://github.com/growchief/growchief) | ~3k | AGPL-3.0 | OSS social automation focused on outreach | Workflow node system for chained "post → comment → DM" sequences |

## Meta / Facebook Graph API libraries

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [facebook/facebook-python-business-sdk](https://github.com/facebook/facebook-python-business-sdk) | ~1.2k | Custom (Meta) | Official Meta SDK, auto-generated, always current | Use directly for Ads/Insights instead of hand-rolling endpoints |
| [sns-sdks/python-facebook](https://github.com/sns-sdks/python-facebook) | ~700 | Apache-2.0 | Maintained Graph API wrapper covering Pages, IG, Threads | Drop-in replacement for our 37 Graph tools' transport layer |

## Multi-platform posting libraries

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [subzeroid/instagrapi](https://github.com/subzeroid/instagrapi) | ~5.8k | MIT | Reverse-engineered IG private API; reaches what Graph API can't | Optional adapter for Reels/Stories the official API restricts |
| [tweepy/tweepy](https://github.com/tweepy/tweepy) | ~11k | MIT | Battle-tested X/Twitter v2 client | Wrap as our X provider, supports media upload |
| [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api) | ~5.2k | MIT | Unofficial TikTok scraper for analytics/trends (not posting) | Trend monitoring and competitor watch |
| [linkedin-developers/linkedin-api-python-client](https://github.com/linkedin-developers/linkedin-api-python-client) | ~400 | Apache-2.0 | Official LinkedIn client | Personal-profile + company-page posting |

## AI content generation

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | ~50k | Apache-2.0 | LLM-friendly markdown crawler | Power "ingest URL → draft 5 hooks" feature |
| [abilzerian/LLM-Prompt-Library](https://github.com/abilzerian/LLM-Prompt-Library) | ~1.5k | MIT | Curated, regularly updated prompt collection | Hook generator and copy templates for our 17-skill system |
| [microsoft/prompt-engine-py](https://github.com/microsoft/prompt-engine-py) | ~1k | MIT | Structured prompt construction with persona/voice descriptors | Foundation for `BrandVoice` class that ships voice to LLM calls |

## MCP server collections

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [oliverames/meta-mcp-server](https://github.com/oliverames/meta-mcp-server) | small/active | MIT | 200+ Meta tools (Pages, IG, Threads, Ads) | Borrow tool definitions for Threads, Ad Library, Conversions API |
| [TensorBlock/awesome-mcp-servers](https://github.com/TensorBlock/awesome-mcp-servers) | ~1.5k | MIT | [Social-media + content section](https://github.com/TensorBlock/awesome-mcp-servers/blob/main/docs/social-media--content-platforms.md) | Index for finding Reddit/YouTube/LinkedIn MCPs to add |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | ~70k | MIT | Reference servers + best-practice patterns | Borrow auth, transport, and tool-registration patterns |

## HTMX / FastAPI admin & dashboards

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [benavlabs/crudadmin](https://github.com/benavlabs/crudadmin) | ~700 | MIT | FastAPI + HTMX admin with auth and event tracking | Drop-in admin for users/accounts/posts CRUD |
| [jowilf/starlette-admin](https://github.com/jowilf/starlette-admin) | ~1.7k | MIT | File-field, multi-DB, rich filtering | Media library management UI |
| [aminalaee/sqladmin](https://github.com/aminalaee/sqladmin) | ~2.7k | BSD-3 | Lightweight SQLAlchemy admin | Quickest zero-config CRUD over our tables |
| [volfpeter/fastapi-htmx-tailwind-example](https://github.com/volfpeter/fastapi-htmx-tailwind-example) | ~300 | MIT | SSE streaming, dialogs, lazy tables | Live approval-queue updates without JS framework |

## Apify alternatives (self-hosted scraping)

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [apify/crawlee-python](https://github.com/apify/crawlee-python) | ~7k | Apache-2.0 | Apify's OSS framework — Playwright + proxy rotation | Self-hosted competitor/audience scraping, replaces SaaS calls |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) | ~55k | BSD-3 | Reference Python crawler | High-volume scheduled scrapes (top posts, hashtag trends) |

## Approval queue / workflow

| Repo | Stars | License | Why it matters | How we'd use it |
|------|-------|---------|----------------|-----------------|
| [fgmacedo/python-statemachine](https://github.com/fgmacedo/python-statemachine) | ~1.8k | MIT | Has explicit `ApprovalWorkflow` example | Model post lifecycle: `draft → pending → approved → scheduled → posted → failed` |
| [PrefectHQ/prefect](https://github.com/PrefectHQ/prefect) | ~19k | Apache-2.0 | Workflow orchestrator with retries, scheduling, observability | Replace cron + ad-hoc retries for post execution |

## Awesome lists

| Repo | Stars | License | Why it matters |
|------|-------|---------|----------------|
| [mjhea0/awesome-fastapi](https://github.com/mjhea0/awesome-fastapi) | ~10k | CC0 | Source of FastAPI extensions (auth, rate-limit, events) we'll need |

---

## Recommended integration order (next 3 PRs)

1. **`python-facebook`** — replaces our hand-rolled Graph API code in `facebook_api.py`. Smaller surface area, less to maintain, follows Meta's spec changes automatically. ~1 day of work.

2. **`python-statemachine`** — refactor `dashboard/db.py` so post status uses a state machine instead of strings. Catches invalid transitions at compile/test time (e.g. you can't go `published → pending`). ~half a day.

3. **`instagrapi` adapter** — adds Instagram publishing as a sibling to the Facebook flow. Your current Page Token already includes `instagram_content_publish` scope, so the API access is handled. ~2 days.

After those three, the platform meaningfully expands without rewriting much.
