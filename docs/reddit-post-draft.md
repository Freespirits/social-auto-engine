# Reddit post draft

**Subreddit:** r/selfhosted (post first), then r/opensource, r/Python, r/SocialMediaMarketing

**Title:** I built an open-source social media manager that lets you publish to Facebook, Instagram, and WhatsApp from one dashboard. No cloud accounts, runs on localhost.

---

**Body:**

Been managing a bunch of social media pages and got tired of paying for tools that do half the job. So I built my own.

**Social Auto Engine** is a self-hosted social media management dashboard. You write a post, pick the platform, hit "send for approval" and it sits in a queue until you approve it. Nothing publishes without you clicking the button. No surprises.

**What it does right now:**

- Publish to Facebook, Instagram, and WhatsApp from one compose box
- Approval queue with approve/reject per post
- Settings page that shows which accounts are connected and lets you test each connection live
- MCP server with 37 Facebook Graph API tools (works with Claude Desktop, Claude Code, Cursor)
- 17 AI content skills for writing posts in your own voice, scoring drafts against your real engagement data, reverse-engineering competitor reels
- Dark mode dashboard, runs on localhost:7651

**Stack:** Python, FastAPI, HTMX, Jinja2, SQLite. No React, no Node, no build step. Clone, pip install, run.

**What's being worked on:**

- LinkedIn adapter (contributor PR incoming)
- Test suite (another contributor working on it)
- Threads integration (just got the API credentials)
- AI-powered compose (wire Claude/OpenAI/Gemini into the textarea)
- Cron-based scheduler

The whole thing started from merging two smaller projects: a Facebook MCP server (37 Graph API tools) and a set of content creation skills from someone running a 350k-follower system. The dashboard came after.

It's early alpha but everything listed as "working" actually works. I've been posting to my own pages through it for the past few days.

**Links:**

- GitHub: https://github.com/Freespirits/social-auto-engine
- Curated tools list: https://github.com/Freespirits/awesome-social-auto-engine
- Development setup: https://github.com/Freespirits/social-auto-engine/blob/main/DEVELOPMENT.md

MIT licensed. Looking for contributors, especially people who've worked with the LinkedIn or TikTok APIs. Issues are labeled with "good first issue" if you want to start small.

Happy to answer questions about the architecture or the Meta API stuff.

---

**Notes for posting:**

- r/selfhosted: use the "New Project" flair if available, otherwise "Self Hosted"
- r/opensource: standard post, no special flair needed
- r/Python: flair as "I Made This"
- r/SocialMediaMarketing: frame it as "free alternative to Buffer/Hootsuite" angle
- Post Tuesday-Thursday, 9-11am ET for best engagement
- Don't crosspost within 24 hours, space them out over a few days
- Reply to every comment in the first 2 hours
