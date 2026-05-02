# Social Engine

Multi-channel social media platform that manages Facebook, Instagram, LinkedIn, TikTok, and X from a single dashboard. AI-powered content generation, human approval workflows, and automation that scales from 1 to 100 pages.

## What this does

- **Publish everywhere from one place.** Write a post once, adapt it for five platforms, approve it, and publish.
- **AI content generation.** Claude, OpenAI, Gemini, DALL-E, ElevenLabs, and more. Voice-matched to sound like you.
- **Human-in-the-loop.** Every post goes through an approval queue. Skip approval if you want, but the system warns you.
- **Scale to 100 pages.** Batch compose, batch approve, staggered publishing, rate limit awareness.
- **17 content skills.** Voice profiling, post writing, hook generation, scoring against real data, niche research, reels scripting, graphic design.
- **Analytics.** Cross-platform metrics in one dashboard.

## Project structure

```
social-engine/
  server.py              # FastMCP entry point (Facebook Graph API tools)
  config.py              # Environment variables and API config
  facebook_api.py        # Facebook Graph API wrapper
  manager.py             # Business logic layer (37 tool methods)
  requirements.txt       # Python dependencies

  skills/                # 17 content creation skills
    voice-builder/       # Foundation: builds about-me.md + voice.md
    newsletter-voice/    # Newsletter-specific voice rules
    post-writer/         # LinkedIn post drafting (4 frameworks)
    post-formatter/      # Additional frameworks (AIDA, BAB, STAR, SLAY)
    hook-generator/      # 6 hook variations per topic
    post-scorer/         # Score drafts against real performance data
    graphic-designer/    # HTML/CSS graphics or AI image prompts
    gemini-infographic/  # Whiteboard-style infographics
    gemini-carousel/     # Slide-by-slide carousels
    quote-post/          # Quote + image generation
    reels-scripting/     # Reverse-engineer reels, write new scripts
    youtube-thumbnail/   # Video thumbnail prompts
    niche-research/      # Browser-driven trend research
    content-matrix/      # Pillar x format ideation (32+ ideas)
    analytics-dashboard/ # LinkedIn analytics to interactive dashboard
    profile-optimizer/   # LinkedIn profile rebuild
    pinned-comment/      # Meme-style pinned comments

  docs/
    specs/
      2026-05-02-multi-channel-platform-master-plan.md
      2026-05-02-approval-queue-and-dashboard-mvp-design.md

  assets/
    banner.svg
```

## Architecture

See [docs/specs/2026-05-02-multi-channel-platform-master-plan.md](docs/specs/2026-05-02-multi-channel-platform-master-plan.md) for the full 14-section plan covering:

- Platform API constraints and readiness per channel
- Dashboard UI design (FastAPI + HTMX, no SPA build step)
- Approval queue with four tiers
- AI provider routing (Claude, OpenAI, Gemini, DALL-E, ElevenLabs, HeyGen)
- Content pipeline from topic to published post
- Batch workflows for 100 pages
- Advertising (Meta boost-top-performers in v1)
- Skill-to-component mapping
- 6-phase implementation roadmap (24 weeks)

## Quick start

### MCP server (Facebook tools, working now)

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```
PAGE_ACCESS_TOKEN=your_facebook_page_token
PAGE_ID=your_page_id
```

Run via Claude Desktop or any MCP client:

```bash
python server.py
```

### Skills (content generation)

Skills are markdown workflows that Claude executes. Start with voice-builder:

1. Open a Claude project
2. Say "build my voice"
3. Complete the interview and paste 3-5 writing samples
4. The system creates `about-me.md` and `voice.md`
5. Every other skill reads these files to match your voice

## Platform support

| Platform  | Status     | What works now                                      |
|-----------|------------|-----------------------------------------------------|
| Facebook  | Ready      | Full Graph API: post, schedule, comments, insights  |
| Instagram | Ready      | Via Facebook Graph API: photos, carousels, reels    |
| LinkedIn  | Needs review | App review required (2-8 weeks) for write access  |
| X         | Needs $200/mo | Pro tier required for posting                    |
| TikTok    | Needs review | App review required (2-6 weeks) for posting       |

## Origins

This project merges two repositories:

- **facebook-mcp-server** - MCP server with 37 Facebook Graph API tools, approval queue design
- **social-media-skills** - 17 content creation skills by [Charlie Hills](https://charliehills.substack.com)

## License

MIT
