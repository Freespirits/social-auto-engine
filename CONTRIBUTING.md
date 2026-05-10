# Contributing to Social Auto Engine

Thanks for the interest. This is the kind of project where one focused weekend can move the entire trajectory. Here's how to plug in.

## Before you write code

**1. Read [the master plan](docs/specs/2026-05-02-multi-channel-platform-master-plan.md).** Even a skim. It's the architectural contract — every PR should fit somewhere in it.

**2. Look at [docs/integrations.md](docs/integrations.md).** We've already curated 24 OSS projects to learn from or borrow patterns. If your idea is "let's build X from scratch," check there first.

**3. Open an issue describing what you want to build.** Saves rework. Tag it `proposal`.

## Quick start (development)

```bash
git clone https://github.com/Freespirits/social-auto-engine.git
cd social-auto-engine
pip install -r requirements.txt
cp .env.example .env  # then add your Facebook tokens
python -m dashboard.app
```

Open http://127.0.0.1:7651.

To run the MCP server (for Claude Desktop / Cursor / any MCP client):
```bash
python server.py
```

### Refreshing the Facebook Page token

Graph API Explorer hands out short-lived user tokens that expire in about an hour. When the dashboard starts returning 401s on Facebook calls, paste a fresh user token from [Graph API Explorer](https://developers.facebook.com/tools/explorer/) and run:

```bash
python -m scripts.refresh_token <SHORT_LIVED_USER_TOKEN>
```

This requires `META_APP_ID`, `META_APP_SECRET`, and `FACEBOOK_PAGE_ID` in `.env`. The script exchanges the short-lived user token for a long-lived (60-day) one, derives the never-expiring Page access token via `/me/accounts`, and writes it back to `.env` as `FACEBOOK_ACCESS_TOKEN`. Restart the dashboard and you are back online.

The same logic is exposed as `Manager.refresh_facebook_token(short_lived_user_token)` for use from the dashboard on a 401 response.

### Wiring an AI provider for the compose Sparkles button

The `POST /generate` endpoint (and `content.generator.generate_post`) routes to one of three providers, picked by `AI_PROVIDER` in `.env`:

- `claude` (default). Needs `ANTHROPIC_API_KEY` and `pip install anthropic`.
- `openai`. Needs `OPENAI_API_KEY` and `pip install openai`.
- `gemini`. Needs `GOOGLE_AI_API_KEY` and `pip install google-generativeai`.

Only the SDK for your chosen provider needs to be installed. Voice tuning is automatic. If `about-me.md` or `voice.md` exist at the project root they get prepended to every prompt as the voice profile.

## Project structure

```
server.py              # FastMCP entry point — 37 Facebook tools
manager.py             # Facade over platform adapters
facebook_api.py        # Facebook Graph API wrapper
instagram_api.py       # Instagram Graph API wrapper
config.py              # Env-driven config

dashboard/             # FastAPI + HTMX dashboard
  app.py               # Routes
  db.py                # SQLite + lifecycle helpers
  templates/           # Jinja2 + HTMX
  static/              # CSS, favicon

skills/                # 17 markdown content workflows
docs/specs/            # Architecture specs (read before contributing)
docs/integrations.md   # Curated OSS projects
```

## How to contribute

### 🎯 Open issues to start with

Run `gh issue list --label "good first issue"` or check the [issues page](https://github.com/Freespirits/social-auto-engine/issues?q=is%3Aopen+label%3A%22good+first+issue%22).

### Branch & PR conventions

- `git checkout -b feat/<short-name>` for features
- `git checkout -b fix/<short-name>` for bug fixes
- `git checkout -b docs/<short-name>` for documentation
- One PR per logical chunk. Don't lump 5 features into one PR.
- Reference the issue in the PR description: `Closes #42`.

### Commit messages

```
<type>: <short summary in imperative mood>

<longer description if needed, wrapped at 72 chars>
```

Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`.

Examples:
- `feat: add LinkedIn adapter with company-page posting`
- `fix: token refresh crash when refresh_token is null`
- `docs: clarify approval-queue lifecycle in master plan`

### Code style

- Python 3.11+. Use `from __future__ import annotations` in new files.
- Type hints on public functions.
- Black-compatible formatting (we don't run a formatter automatically yet, but keep it readable).
- British English in user-facing copy.
- **No em dashes.** No semicolons in the prose. (Rules baked into the voice system; consistency matters.)

### Approval-queue spine — non-negotiable

The whole platform's safety story is "no silent automation." If your change adds a write action, it MUST go through the approval queue, OR be opt-in with a clearly visible warning. Read [docs/specs/2026-05-02-approval-queue-and-dashboard-mvp-design.md](docs/specs/2026-05-02-approval-queue-and-dashboard-mvp-design.md).

## What we're looking for

### High-impact, ready to start

- New platform adapters (LinkedIn, X, TikTok) following `instagram_api.py` shape
- AI provider integration (Claude / OpenAI / Gemini) wired into `/compose`
- Scheduler (cron-style queue with optimal-time suggestions)
- Token refresh helpers (long-lived exchange, automatic rotation)
- Test suite (no tests exist yet — green field)
- Docker + docker-compose
- Authentication for the dashboard (currently single-user)
- Better empty-state illustrations / onboarding flow

### Smaller, very welcome

- More skills under `skills/` (each is a single SKILL.md)
- Bug fixes in the existing Facebook tools
- Type hints / docstrings on the manager class
- Examples in `docs/examples/` showing real usage
- README polish (screenshots, GIFs, demo videos)

## Testing your changes

Until we have a test suite (good first issue!), at minimum:

1. Run the dashboard and click through compose → approve → publish.
2. Check the MCP server boots: `python server.py` should not error.
3. If you changed an adapter, smoke-test against a real (test) account.

## Questions

Open a [GitHub Discussion](https://github.com/Freespirits/social-auto-engine/discussions) or drop into the issue you opened.

## Code of Conduct

Be kind. Assume good faith. Disagreement is fine, contempt is not.
