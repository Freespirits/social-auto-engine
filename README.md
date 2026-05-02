<p align="center">
  <img src="assets/banner.svg" alt="Social Auto Engine - One dashboard, five platforms, every post approved" width="100%"/>
</p>

<p align="center">
  <a href="#quick-start"><img src="https://img.shields.io/badge/status-early%20alpha-orange?style=for-the-badge" alt="status"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="license"/></a>
  <a href="docs/specs/2026-05-02-multi-channel-platform-master-plan.md"><img src="https://img.shields.io/badge/master%20plan-read-7b61ff?style=for-the-badge" alt="master plan"/></a>
  <a href="#help-wanted"><img src="https://img.shields.io/badge/contributors-wanted-ff4d8d?style=for-the-badge" alt="contributors wanted"/></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="python"/></a>
</p>

<h2 align="center">The open-source operating system for your social media.</h2>

<p align="center">
Write once, publish to <b>Facebook</b>, <b>Instagram</b>, <b>LinkedIn</b>, <b>X</b>, and <b>TikTok</b>. AI drafts the post, you approve it, the system publishes it. Built to scale from your one personal page to managing 100 client accounts without losing your mind.
</p>

---

## Why this exists

Most social media tools fall into two camps:

- **Schedulers** (Buffer, Hootsuite, Later) — great at queuing, terrible at content. You still write everything yourself.
- **AI writers** (Jasper, Copy.ai) — great at drafts, terrible at execution. They don't post anywhere.

Social Auto Engine is the missing middle. The AI knows your voice (because you trained it on your samples), the dashboard knows your platforms (because every account is connected), and a human approves every single thing before it leaves the door. No silent automation. No "trust the algorithm." Just a faster version of the workflow you'd run by hand.

**Pitch in one sentence:** It's the post pipeline a solo creator and a 100-page agency can run on the same software.

---

## What's inside

### The MCP server (`server.py` + 37 tools)
Drop-in tools for Claude Desktop, Claude Code, Cursor, or any MCP client. Post, schedule, fetch insights, manage comments, run bulk actions on your Facebook page from inside chat.

### 17 content skills (`skills/`)
Markdown workflows Claude executes. Build your voice, generate hooks, score drafts against your real performance data, reverse-engineer outlier reels, write captions, design graphics, plan a content matrix.

### Master plan (`docs/specs/`)
14-section design doc covering the full multi-channel architecture: dashboard, approval queue, AI provider routing, batch workflows for 100 pages, ad creation, analytics. Read it before you contribute.

---

## What works today

| Capability                           | Status            | Notes                                            |
|--------------------------------------|-------------------|--------------------------------------------------|
| Facebook publishing (text/image/video) | ✅ Working        | 37 Graph API tools, MCP-ready                   |
| Facebook insights & comments         | ✅ Working        | Including bulk hide/delete, sentiment filtering |
| Voice profile system                 | ✅ Working        | `voice-builder` skill produces about-me + voice |
| AI post writing in your voice        | ✅ Working        | Via skills: post-writer, post-formatter, hooks  |
| Post scoring vs real data            | ✅ Working        | Apify-backed, scores against your top 10%       |
| Reels reverse-engineering            | ✅ Working        | Apify scrape + Gemini 2.5 Flash analysis        |
| Graphic generation                   | ✅ Working        | HTML/CSS or AI infographic styles               |
| Instagram publishing                 | 🟡 Adapter planned | Foundation done via Facebook Graph API         |
| LinkedIn publishing                  | 🟡 Adapter planned | Awaiting Marketing Developer Platform review   |
| X / Twitter publishing               | 🟡 Adapter planned | Requires Pro tier ($200/mo)                    |
| TikTok publishing                    | 🟡 Adapter planned | Awaiting Content Posting API review            |
| Approval queue dashboard             | 🟡 Spec done       | Slice 2 design ready to build                  |
| Cross-platform analytics             | ⚪ Designed       | Phase 5 of the master plan                     |
| Ad boosting (Meta)                   | ⚪ Designed       | Phase 6 of the master plan                     |

---

## Quick start

### 1. Run the MCP server (Facebook tools, working now)

```bash
git clone https://github.com/Freespirits/social-auto-engine.git
cd social-auto-engine
pip install -r requirements.txt
```

Create a `.env` file:

```env
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_ACCESS_TOKEN=your_long_lived_page_token
```

Add to `~/.config/Claude/claude_desktop_config.json` (or the Windows equivalent):

```json
{
  "mcpServers": {
    "social-auto-engine": {
      "command": "python",
      "args": ["/absolute/path/to/social-auto-engine/server.py"],
      "env": {
        "FACEBOOK_PAGE_ID": "...",
        "FACEBOOK_ACCESS_TOKEN": "..."
      }
    }
  }
}
```

Restart Claude Desktop. Try: *"Show me my last 5 Facebook posts and their engagement."*

### 2. Use the skills (any Claude project)

Drop the `skills/` folder into a Claude project, then say:

- **"build my voice"** → walks you through the voice profile interview
- **"write a post about X"** → drafts in your voice with a chosen framework
- **"score my post"** → rates a draft against your real top performers
- **"script a reel"** → reverse-engineers a reference reel and writes yours

Each skill is a single SKILL.md file. Read it, edit it, fork it.

---

## Architecture in one picture

```
                 ┌──────────────────────────────────────────┐
                 │   Dashboard (FastAPI + HTMX + SQLite)    │
                 │   localhost:7651                         │
                 │   compose · inbox · accounts · analytics │
                 └──────────────────────────────────────────┘
                                     │
        ┌────────────────┬───────────┼───────────┬────────────────┐
        ▼                ▼           ▼           ▼                ▼
  ┌──────────┐    ┌──────────┐  ┌────────┐  ┌──────────┐    ┌──────────┐
  │ Approval │    │ Content  │  │ Voice  │  │Scheduler │    │Analytics │
  │  Queue   │    │ Generator│  │ Engine │  │          │    │          │
  └──────────┘    └──────────┘  └────────┘  └──────────┘    └──────────┘
        │                │           │           │                │
        └────────────────┴───────────┼───────────┴────────────────┘
                                     ▼
                  ┌────────────────────────────────────┐
                  │         Platform Adapters          │
                  │  Facebook · IG · LinkedIn · X · TT │
                  └────────────────────────────────────┘
```

Full breakdown — including SQL schemas, dashboard wireframes, AI provider routing, batch workflows for 100 pages, and the 6-phase roadmap — lives in **[docs/specs/2026-05-02-multi-channel-platform-master-plan.md](docs/specs/2026-05-02-multi-channel-platform-master-plan.md)**.

---

## Help wanted

This project is the size where one weekend from the right person changes the trajectory. Here's where you can pick up a meaningful chunk:

### 🎯 High-impact, ready to start

| Area                          | What                                                           | Skills needed                |
|-------------------------------|----------------------------------------------------------------|------------------------------|
| **Dashboard MVP**             | FastAPI + HTMX shell with inbox, compose, accounts pages      | Python, HTMX, SQLite         |
| **Instagram adapter**         | Wrap IG Graph API behind the `PlatformAdapter` interface      | Python, Graph API            |
| **Approval queue**            | Implement Slice 2 spec (request lifecycle, SSE inbox)         | Python, FastAPI, SQLite      |
| **Voice loader**              | Parse about-me.md + voice.md, inject into AI calls            | Python                       |
| **OAuth flows**               | Account-add wizards for each platform                         | Python, OAuth 2.0            |

### 🧪 Solid second-tier

- LinkedIn / X / TikTok adapters (each one is its own PR)
- Compose page with multi-platform character-count + preview
- Cross-platform analytics collector
- Niche-research skill ported into a dashboard tab
- Test suite (no tests exist yet — green field)
- Docker / docker-compose setup
- Documentation: per-skill docs, architecture decision records

### 💡 Got a different idea?

Open an issue with the label `proposal`. The master plan is the north star but it's not law — if you have a sharper take, make the case.

### How to contribute

1. **Read** [the master plan](docs/specs/2026-05-02-multi-channel-platform-master-plan.md). Even a skim. It's the contract.
2. **Open an issue** describing what you want to build before you write code. Saves rework.
3. **Branch from main**, small focused PRs. One adapter per PR is fine.
4. **No silent automation.** If your change adds a write action, it must go through the approval queue or be opt-in with a warning. This is the project's spine.
5. **British English in user-facing copy.** No em dashes. Yes, even in PR descriptions. (You'll see why once you read voice.md.)

---

## Tech stack

- **Python 3.11+** — server, adapters, content pipeline
- **MCP (Model Context Protocol)** — tool layer, integrates with Claude / Cursor / any MCP client
- **FastAPI + HTMX + Jinja2** — dashboard (no SPA build step, no Node.js dependency)
- **SQLite (WAL mode)** — single-file persistence, zero ops
- **Apify** — Instagram / LinkedIn scraping for trend research and post-history scoring
- **AI providers** — Claude (via MCP), OpenAI GPT-4o, Gemini 2.5, DALL·E 3, ElevenLabs, HeyGen

---

## Project origins

Social Auto Engine merges two open-source projects:

- **[facebook-mcp-server](https://github.com/HagaiHen/facebook-mcp-server)** by Hagai Hen — MCP server with 37 Graph API tools and the approval queue spec.
- **[social-media-skills](https://github.com/charlie947/social-media-skills)** by [Charlie Hills](https://charliehills.substack.com) — 17 content skills behind a real 350k-follower content system.

Both still stand on their own. This repo is the integration: the MCP backbone meets the content pipeline meets a multi-channel dashboard.

---

## License

MIT. Use it, fork it, ship it commercially. Just don't pretend you wrote it from scratch — credit lives in [LICENSE](LICENSE) and the origin links above.

---

<p align="center">
  <i>Star the repo if you want this built faster. Open an issue if you want to build it with us.</i>
</p>
