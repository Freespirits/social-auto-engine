# Changelog

All notable changes to social-auto-engine will be recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely, dates use ISO format, and the project adheres to [Semantic Versioning](https://semver.org/) once it leaves early-alpha.

## [Unreleased]

### Added
- **Multi-platform broadcast composer.** Compose once, fan out to every selected platform. Each platform's publish is tracked independently so partial failures (one platform's token expired, others succeed) are reported honestly. ([design](docs/specs/2026-05-06-company-grouped-ui-and-multi-platform-compose-design.md))
- **Company-grouped sidebar.** Connected accounts now sit under collapsible Meta / LinkedIn / TikTok / YouTube / X sections instead of a flat list.
- **Composer split into Broadcast and Direct message tabs.** WhatsApp's 1:1 messaging keeps its dedicated form, the broadcast tab handles the cross-platform fan-out flow.
- **LinkedIn adapter** (`linkedin_api.py`). Member-tier OAuth (text, image, article posts via the UGC API). Connect at `/oauth/linkedin/start`.
- **TikTok adapter** (`tiktok_api.py`). Inbox-upload tier with `PULL_FROM_URL` and chunked `FILE_UPLOAD` modes. Direct-post tier deferred until full TikTok app review. Connect at `/oauth/tiktok/start`.
- **YouTube adapter** (`youtube_api.py`). Simple multipart video upload via Data API v3. Defaults `privacyStatus='private'` so the user reviews before going live. Refresh-token aware. Connect at `/oauth/youtube/start`.
- **Shared OAuth callback infrastructure.** `_store_tokens` writes to `~/.social-auto-engine/tokens.env` and patches the live adapter instances so the running dashboard sees new tokens without restart. State cookie defends against CSRF on every callback.
- **Dashboard password authentication** (opt-in). Sets a signed session cookie when `DASHBOARD_PASSWORD` is set in the environment. Transparent when unset.
- **Test suite** (`tests/`). 46 tests covering the persistence layer, the compose HTTP flow, OAuth callback flow, adapter import smoke checks, and the `_store_tokens` helper.
- **CI Pytest job** in `.github/workflows/ci.yml`.
- **`docs/platform-tiers.md`** — single source of truth for what each platform's API tiers grant, what they cost, and how the dashboard should surface tier capabilities.
- **`docs/audit-2026-05-06.md`** — quality-sweep-style audit of the codebase, ranked findings.
- **`TERMS.md` and `PRIVACY.md`** — required for TikTok and LinkedIn developer-app submissions.

### Changed
- **README hero copy** now lists five live channels (Facebook, Instagram, Threads, WhatsApp, LinkedIn) plus two code-complete adapters awaiting review (TikTok, YouTube) and one paid-tier adapter explicitly deferred (X). Replaces the earlier overclaim.
- **README roadmap table** refreshed to reflect the multi-platform work landing.

### Fixed
- **`_safe_page_info` no longer fakes a connected Facebook page on API failure.** The previous fallback returned a hard-coded "Hack-Tech / Education website" dict that made the dashboard report Facebook as connected even when the token was missing or expired. Now returns `connected=False` consistent with every other platform helper.
- **OAuth state validation closes a CSRF window.** All three callbacks (LinkedIn, TikTok, YouTube) now reject requests where the state cookie is missing or doesn't match the supplied `?state` parameter. Previously LinkedIn skipped the check entirely and TikTok / YouTube accepted any state when the cookie was missing.
- **`YouTubeAPI.upload_video` no longer recurses infinitely** if a refresh-then-retry hits another 401. Now retries at most once per call.
- **`TikTokAPI._init_and_upload_file` rejects 0-byte files** instead of dividing by zero in the chunk-count calculation.

## [2026-05-05] Polish for awesome-list traffic

### Added
- "About the maintainer" section in the README crediting Vet Flow, Hagai Hen's `facebook-mcp-server`, and Charlie Hills's `social-media-skills`.
- 2026-05-05 status update section at the top of the master plan.
- `CLAUDE.md` for AI-assisted contribution guidance, derived from Andrej Karpathy's behavioural guidelines.

### Restored
- `docs/specs/2026-05-02-multi-channel-platform-master-plan.md`
- `docs/specs/2026-05-02-approval-queue-and-dashboard-mvp-design.md`
- `docs/integrations.md` (24 OSS projects we learn from)

## [2026-05-04] Awesome-list submission

### Added
- Listed on TensorBlock/awesome-mcp-servers, social-media category (PR #479, merged then later force-pushed off in a maintainer cleanup sweep on 2026-05-05).

## [2026-05-03] Dashboard MVP

### Added
- Approval queue dashboard (`dashboard/app.py`) with FastAPI + Jinja2 + HTMX. SQLite persistence at `~/.social-auto-engine/dashboard.db`. WAL mode. Compose, approve, reject, schedule, and connection-status views.
- Scheduler integration (`dashboard/scheduler.py`) using APScheduler with its own SQLite jobstore.
- Threads adapter (`threads_api.py`) — full OAuth 2.0 flow plus text, image, video, and reply-control posting.

## Earlier history

This project began life as a focused Facebook MCP server in March 2026. The Instagram, WhatsApp, and Threads adapters landed before this changelog was started. See `git log` for the full narrative.
