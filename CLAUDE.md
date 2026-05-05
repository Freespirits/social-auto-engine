# CLAUDE.md

Behavioural and project-specific guidance for any Claude Code session working on `social-auto-engine`.

This file has two parts. **Part A (sections 1-4)** is the widely-circulated behavioural CLAUDE.md derived from Andrej Karpathy's observations on common LLM coding pitfalls, published by forrestchang at [github.com/forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (112k+ stars). It is reproduced here verbatim as the universal behavioural layer.

**Part B (sections 5+)** is the project-specific layer for `social-auto-engine`.

---

# Part A — Universal behavioural guidelines

> *Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.*
>
> *Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.*

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

*End of Part A. Original at [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md). Reproduced here under fair use with attribution.*

---

# Part B — `social-auto-engine` specific guidance

## 5. The architectural spine (non-negotiable)

**No silent automation.** Every write action that touches an external platform must go through the approval queue, or be opt-in with a clearly visible warning. The approval queue is the safety story we tell agencies, regulated industries, and the awesome-list audience that brought traffic here. Bypassing it is the only way to permanently lose this project's trust.

If a feature requires a write API call, the answer is always:

1. The dashboard composes a draft
2. The draft lands in the approval queue with status `pending`
3. A human approves
4. The publish function runs against the platform adapter

No exceptions. If a feature seems to require silent automation, the design is wrong.

## 6. Project conventions

### Voice and copy
- **British English** in all user-facing copy (README, dashboard text, error messages, docs).
- **No em dashes** in prose. Replace with full stops or commas.
- **No semicolons** in prose. (Semicolons in code are fine where the language requires them.)
- **Default to no comments.** Only comment when the *why* is non-obvious. Don't restate what well-named code already says.

### Code style (Python)
- Python 3.11+ throughout. Use `from __future__ import annotations` in new files.
- Type hints on public functions.
- Black-compatible formatting (no auto-formatter enforced yet but keep things readable).
- Match existing patterns. The dashboard uses FastAPI + Jinja2 + HTMX. No SPA framework, no Node.js dependency, no build step.
- SQLite in WAL mode for persistence. APScheduler with its own SQLite jobstore for scheduled jobs.

### Adapter pattern
New platform adapters mirror the shape of `instagram_api.py`:
1. A class with `__init__(self)` reading credentials from env
2. A `_request(method, endpoint, **kwargs)` wrapper with error handling
3. Public publish methods that return `{"success": bool, "id"|"error": ...}`
4. Wired into `manager.py` as passthrough methods
5. Branched into `dashboard/app.py` `_publish_post()`
6. Env vars added to `.env.example`

## 7. Repository map

```
server.py                        FastMCP entry. 37 Facebook MCP tools.
manager.py                       Facade over all platform adapters.
facebook_api.py                  Facebook Graph API wrapper.
instagram_api.py                 Instagram Graph API. Reference shape for new adapters.
whatsapp_api.py                  WhatsApp Business Cloud API.
threads_api.py                   Threads API. Full OAuth flow.
linkedin_api.py                  LinkedIn API (in flight on dashboard-addons branch).
config.py                        Env-driven config loader.

dashboard/
  app.py                         FastAPI routes. Inbox, compose, settings, calendar.
  db.py                          SQLite persistence. Post lifecycle.
  scheduler.py                   APScheduler integration. Date-trigger jobs.
  auth.py                        Cookie-based password auth (in flight).
  templates/                     Jinja2 + HTMX. Server-rendered. No SPA.
  static/styles.css              Editorial-terminal design system.

skills/                          17 Claude Skills. Each is a single SKILL.md.
docs/specs/                      Architecture specs. Read before contributing.
docs/integrations.md             24 OSS projects we learn from.
docs/meta-survival-guide.md      Meta token / app review walkthrough.
references/postiz/               Git submodule. Pattern study only.
.env.example                     Documented env-var template.
```

## 8. What NOT to do (project-specific)

- **Do not claim aspirational features as live in user-facing copy.** The README has been disciplined about saying what is shipped (Facebook, Instagram, WhatsApp, Threads) versus what is in flight or planned (LinkedIn, X, TikTok). Match this discipline. If a platform's adapter is not in `main`, it is not "supported."
- **Do not bypass the approval queue.** See section 5.
- **Do not introduce a build step.** No Node.js, no Webpack, no SPA framework. HTMX over Jinja2 is the choice. If you reach for a JS bundler, the design is wrong.
- **Do not commit secrets.** Tokens go to `~/.social-auto-engine/tokens.env` (loaded by `config.py`) or to `.env` (gitignored). The `.env.example` is the documented template only, never a real value.
- **Do not silently widen scope.** A bug fix is a bug fix. A feature is a feature. Don't roll an unrelated refactor into a small PR without saying so.
- **Do not delete documents linked from the README.** If you remove `docs/specs/...` files referenced anywhere in the README or CONTRIBUTING, fix the links in the same commit.
- **Do not change voice rules.** British English, no em dashes, no semicolons in prose. These are baked into the project's character.

## 9. Where to start (for any new contributor)

1. Read [README.md](README.md) for what the project is.
2. Read [docs/specs/2026-05-02-multi-channel-platform-master-plan.md](docs/specs/2026-05-02-multi-channel-platform-master-plan.md) for the strategic plan.
3. Read [docs/specs/2026-05-02-approval-queue-and-dashboard-mvp-design.md](docs/specs/2026-05-02-approval-queue-and-dashboard-mvp-design.md) for the dashboard's safety spine.
4. Skim [docs/integrations.md](docs/integrations.md) before reinventing anything.
5. See [CONTRIBUTING.md](CONTRIBUTING.md) for branch conventions, commit format, and the issue-first workflow.

## 10. AI assistance disclosure

This project is built with Claude Code. The maintainer is open about it and welcomes other contributors using AI tooling. The behavioural guidelines in Part A exist precisely to make AI-assisted contributions tighter, more surgical, and more trustworthy than the average human PR.

If you are using Claude (or any LLM agent) to contribute:
- Follow Part A's guidelines.
- Follow Part B's project conventions.
- Disclose AI assistance in your PR description if substantial. Honesty is the project culture.
- Review every line before opening the PR. The agent is your tool, not your judgment.
