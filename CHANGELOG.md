# Changelog

All notable changes to social-auto-engine will be recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely, dates use ISO format, and the project adheres to [Semantic Versioning](https://semver.org/) once it leaves early-alpha.

## [v0.6] - 2026-05-15

### Added
- **Campaign Wizard** at `/wizard`. One sentence + one face photo = a 7-day, multi-platform pending campaign in the approval queue. Single-screen form, full-screen scroll-snap result feed, no forced steps. Premium hand-tuned templates work without an OpenAI key.
- **HiggsField native adapter** in `ai_services/higgsfield.py`. HTTP Basic Auth with `HIGGSFIELD_API_KEY_ID` + `HIGGSFIELD_API_KEY_SECRET`. Unlocks 10+ premium video models (Veo 3.1, Kling 3.0, Seedance 2.0, Minimax Hailuo, Wan 2.7, Grok Imagine, more). Replicate stays as a clean fallback. Backwards-compatible `api_key` and `default_model` properties.
- **ElevenLabs voice cloning** in `ai_services/elevenlabs.py`. New methods: `clone_voice(name, audio_paths)`, `delete_voice(voice_id)`, `get_user()`. Brand Kit accepts a new `voice` asset type. Uploading a voice sample auto-clones it via ElevenLabs and stores the resulting `voice_id`.
- **Post enrichment pipeline.** `enrich_post(post_id)` chains caption → image → optional video. `enrich_campaign(group_id)` batch enriches every post in a group. `Enhance` button on every pending post card. Inline `Listen` button plays the caption via ElevenLabs TTS. Pending posts with `video_url` auto-play on hover.
- **Virality predictor** wrapper. Calls HiggsField's virality scorer; returns a stub on other backends.
- **Status endpoint** `GET /api/status`. Sectioned by video, voice, captions, images, platforms. No secrets exposed.
- **Settings page Backend status widget.** Live read of `/api/status` with green/red dots and an `ACTIVE` pill on the selected video backend.
- **CLI health check.** `python -m dashboard.health` prints a coloured (or ASCII fallback) status table. Loads `~/.social-auto-engine/tokens.env` automatically.
- **Six new MCP tools** in `server.py`: `socialblast_generate_campaign`, `socialblast_enrich_post`, `socialblast_enrich_campaign`, `socialblast_predict_virality`, `socialblast_status`, `socialblast_list_pending`.
- **Claude Skill** `skills/socialblast-pipeline/SKILL.md` documenting the end-to-end pipeline workflow for Claude Desktop / Claude Code.
- **Onboarding promotes the wizard.** First-run card step 3 is a gradient-pill link to `/wizard` with the headline "Create a week of content in 60 seconds". Hand-compose path demoted to step 4.
- **Test coverage.** 247 tests total. New: 25 pipeline tests, 10 health CLI tests, 18 MCP tool tests.

### Changed
- **Brand: Social Auto Engine → SocialBlast AI** in every user-facing surface (templates, locale files, FastAPI title, README frontmatter and body). GitHub URL, HuggingFace Space URL, package and module paths preserved.
- **Template captions upgraded.** The fallback used when no OpenAI key is set is now hand-tuned premium captions ("Three things nobody tells you about running X..." style) instead of generic "Did you know?" templates.
- **`.env.example`** documents the new `HIGGSFIELD_API_KEY_ID` and `HIGGSFIELD_API_KEY_SECRET` pair.

### Fixed
- **Test isolation.** `test_ollama_instantiate_no_env` now `monkeypatch.delenv`s `OLLAMA_BASE_URL` and `OLLAMA_MODEL` so a dev's `tokens.env` does not leak into the test.

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
