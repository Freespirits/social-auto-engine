# Spec: Approval Queue + Dashboard MVP (Slice 2)

**Date:** 2026-05-02
**Status:** Draft, awaiting user review

## Background

`facebook-mcp-server` exposes ~37 tools an LLM agent can call against a Facebook Page (post, reply, hide/delete comments, schedule posts, fetch insights). Today the agent acts unsupervised — anything Claude calls hits Facebook immediately. The user wants a control plane: every write/destructive call should pause for human approval before it leaves the local machine, with a UI to review and edit proposed actions.

This document specifies **Slice 2** of a multi-slice plan. Slice 1 (foundation hardening) is deferred except for the minimum subset the queue depends on. Slices 3+ (audit log, webhooks, Messenger inbox, sentiment, video/Reels, saved replies, advanced dashboard) are out of scope here.

## Goals

1. Every write/destructive tool call blocks until a human approves, rejects, or 30 minutes elapses.
2. Read tools execute immediately — no queue interaction, no dashboard dependency.
3. Each tool's policy (`auto` / `approve` / `approve_confirm`) is configurable per-tool with sensible tier-based defaults.
4. The human can: approve as-is, approve with edits to the args, approve with a free-text note back to the agent, or reject with a reason.
5. The dashboard process survives Claude Desktop restarts.
6. Auto-launch the dashboard from the MCP on first need — zero manual setup beyond `pip install`.

## Non-goals

- Webhook receiver, Messenger inbox listing, video/Reel publishing, real sentiment, multi-Page support, FB OAuth, dashboard authentication — all later slices.
- Notifications beyond visual cues in the dashboard tab. No sound, OS toast, Slack, email.
- Audit log query/filter/export. The History page in v1 is a passive, paginated read-only list of recent actions.
- Pagination, retries with backoff, full structured logging — slice 1, deferred.

## Architecture

Two processes on the same machine:

```
┌─────────────────────────┐    stdio/JSON-RPC     ┌──────────────┐
│  facebook-mcp-server    │ ◄───────────────────► │ Claude Desk. │
│  (started by Claude)    │                       └──────────────┘
│                         │
│  - Read tools: execute  │       HTTP long-poll
│  - Write/Destructive:   │ ◄───────────────────┐
│    enqueue + wait       │                     │
└─────────────────────────┘                     │
            ▲                                   │
            │ auto-launch on first need         │
            ▼                                   │
┌───────────────────────────────────────────────┴──┐
│  facebook-mcp-dashboard (long-lived)             │
│  - FastAPI on 127.0.0.1:7651                     │
│  - Owns SQLite at ~/.facebook-mcp/state.db       │
│  - Inbox / Settings / History UI (Jinja + HTMX)  │
│  - Holds long-poll connections from MCP          │
│  - **Executes approved Facebook API calls**      │
└──────────────────────────────────────────────────┘
            │
            ▼
       Facebook Graph API
```

**MCP server (`facebook-mcp-server`).** Started by Claude Desktop on stdio. Owns the agent-facing tool surface. For read tools: executes directly. For write/destructive tools: enqueues a request to the dashboard, long-polls for the decision, relays the result.

**Dashboard (`facebook-mcp-dashboard`).** Long-lived FastAPI process bound to `127.0.0.1:7651`. Owns the SQLite database at `~/.facebook-mcp/state.db`. Renders the human-facing UI. Holds the long-poll connections from the MCP. **Executes the actual Facebook API call on approval** — this matters for durability: an action the human approved still completes if Claude Desktop restarts mid-wait.

**Auto-launch.** On first write/destructive call, the MCP reads the dashboard's port from `~/.facebook-mcp/dashboard.port` (default `7651` if absent) and attempts to reach `127.0.0.1:<port>/health`. If unreachable, it spawns the dashboard as a detached child (using `subprocess.Popen` with platform-specific detach flags), waits up to 5s for `/health` to respond, then proceeds. A PID file at `~/.facebook-mcp/dashboard.pid` plus an exclusive file lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) prevents double-spawn under concurrent first-calls.

**Port fallback.** If `7651` is already in use, the dashboard tries `7652`, `7653`, … up to `7700` before failing. The chosen port is written to `~/.facebook-mcp/dashboard.port` so subsequent MCP starts find it without a discovery scan.

## Component layout

```
facebook_mcp/
├── config.py              # Existing + dashboard config (port, db path)
├── facebook_api.py        # Existing + minimum hardening (timeout, status check, immutable params)
├── manager.py             # Existing
├── policy.py              # NEW — tier classification, per-tool policy resolution
├── field_hints.py         # NEW — registry: tool name → {field name → widget hints}
├── server.py              # FastMCP entry; wraps write/destructive tools with the approval gate
├── queue_client.py        # NEW — MCP-side: enqueue, long-poll for decision, relay result
└── dashboard/
    ├── app.py             # FastAPI app + auto-launcher logic
    ├── db.py              # SQLAlchemy models + session factory
    ├── executor.py        # NEW — runs approved actions via FacebookAPI; updates queue rows
    ├── routes/
    │   ├── api.py         # POST /api/enqueue, GET /api/wait/{id}, POST /api/decide/{id}
    │   ├── inbox.py       # HTMX views for pending requests
    │   ├── settings.py    # Per-tool policy + timeout config UI
    │   └── history.py     # Read-only log of past actions
    ├── templates/         # Jinja2
    └── static/            # HTMX + CSS
```

Two console-script entry points: `facebook-mcp-server` (stdio for Claude) and `facebook-mcp-dashboard` (HTTP for humans, also auto-launched).

## Tech stack

- Python 3.11+
- FastMCP (existing)
- FastAPI + Uvicorn — dashboard HTTP server
- Jinja2 + HTMX — server-rendered UI with reactive widgets, no SPA build
- SQLAlchemy + SQLite — persistent queue + tool policies
- Pydantic — internal request/response schemas
- httpx — MCP→dashboard long-poll client (async, handles long-running connections cleanly)
- `pyproject.toml` replacing `requirements.txt`

## Data model

Two SQLite tables.

### `request`

Records every write/destructive tool call the agent makes.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID4 |
| `tool_name` | TEXT NOT NULL | e.g. `post_to_facebook` |
| `tier` | TEXT NOT NULL | `read` / `write` / `destructive` (denormalized for filtering) |
| `args_proposed` | TEXT NOT NULL | Agent's args as JSON |
| `args_executed` | TEXT NULL | What the executor actually ran. Set when state ≥ `approved`; equals `args_proposed` if no edits, else the edited version. The executor only reads from this column. |
| `state` | TEXT NOT NULL | `pending` / `approved` / `rejected` / `timed_out` / `executing` / `completed` / `failed` |
| `decision` | TEXT NULL | `approve` / `reject` / `timeout`. "Edits" and "notes" are not separate decisions — they're optional extras on top of `approve`, derived from whether `args_executed != args_proposed` and whether `note IS NOT NULL`. |
| `note` | TEXT NULL | Free-text from human (with `approve_with_note`) |
| `reject_reason` | TEXT NULL | Free-text from human (with `reject`) |
| `result` | TEXT NULL | Facebook API JSON response after execution |
| `error` | TEXT NULL | Error envelope if execution failed |
| `parent_request_id` | TEXT NULL | If this is a retry of a prior rejected/timed_out request |
| `created_at` | TIMESTAMP NOT NULL | When agent enqueued |
| `decided_at` | TIMESTAMP NULL | When human acted |
| `executed_at` | TIMESTAMP NULL | When the FB call returned |

Indexes: `(state, created_at)` for fast inbox queries, `(parent_request_id)` for retry chains, `(decided_at DESC)` for History.

### `tool_policy`

| Column | Type | Notes |
|--------|------|-------|
| `tool_name` | TEXT PK | |
| `policy` | TEXT NOT NULL | `auto` / `approve` / `approve_confirm` |
| `timeout_seconds` | INTEGER NULL | NULL = use default (1800 = 30 min) |
| `updated_at` | TIMESTAMP | |

Bootstrapped from tier defaults on first run. Editable from Settings page; changes apply on the next call (no MCP restart).

## Request lifecycle

```
[agent calls tool]
        │
        ▼
   ┌─────────┐
   │ pending │──── timeout (30 min default) ────► [timed_out]
   └─────────┘
        │
        │ human clicks Approve / Approve+Edits / Approve+Note
        ▼
   ┌──────────┐
   │ approved │
   └──────────┘
        │
        │ dashboard executor picks it up
        ▼
   ┌───────────┐
   │ executing │
   └───────────┘
        │
        │ Facebook call returns
        ▼
   ┌────────────────────┐
   │ completed / failed │
   └────────────────────┘

   pending ──── human clicks Reject ────► [rejected]
```

**Happy path with sync wait:**

1. Agent calls `post_to_facebook(message="...")` via MCP.
2. MCP looks up the tool's policy. If `auto`, executes directly and returns the FB result.
3. Otherwise, MCP `POST /api/enqueue` with `{tool_name, args_proposed, tier}`. Dashboard inserts a row in state `pending`, returns `{request_id}`.
4. MCP issues `GET /api/wait/{request_id}?max_seconds=1800` — a long-poll that holds the connection.
5. Dashboard renders the new row in the Inbox; human approves with optional edits/note.
6. Dashboard updates the row to `approved` (with `args_executed` if edited), unblocks the long-poll handler.
7. Dashboard's executor moves the row to `executing`, calls `FacebookAPI.<tool>(...)` with `args_executed`, records the result (or error) in `completed` or `failed` state.
8. Long-poll response returns to MCP with the final result + decision metadata.
9. MCP returns the appropriate response shape (below) to the agent.

**Reject path:** dashboard moves row to `rejected`, long-poll returns immediately, no FB call is made.

**Timeout path:** if no decision after `timeout_seconds`, dashboard moves row to `timed_out` and returns. The row stays visible in the Inbox marked "expired" so the human can still see what was missed.

**Claude Desktop restart mid-wait:** MCP's long-poll drops. Dashboard detects connection drop but does NOT cancel the request — the human's decision still gets recorded and the action still executes when approved (durability win). The agent's conversation is gone, so the response is never delivered to Claude — but the side effect happens. The orphaned row's result is recorded in `completed` and visible in History.

## Response shapes the agent receives

Three top-level shapes, keyed on `status`. The `approved` shape carries optional `edited` / `note` / `execution_error` fields so any combination (as-is / edited / with note / execution failed) collapses cleanly into one structure.

```json
// 1. Approved (covers as-is, edited, with-note, and any combination)
{
  "status": "approved",
  "request_id": "...",
  "edited": false,                    // true iff args_executed != args_proposed
  "args_executed": { "...": "..." },  // always present; equals proposed if not edited
  "diff": null,                       // present and non-null only when edited
  "note": null,                       // present and non-null only when human added one
  "result": { "<fb response>": "..." },
  "execution_error": null             // present and non-null if FB call failed after approval
}

// 2. Rejected
{
  "status": "rejected",
  "request_id": "...",
  "reason": "tone too casual for this audience"
}

// 3. Timed out
{
  "status": "timed_out",
  "request_id": "...",
  "elapsed_seconds": 1800
}
```

The agent treats `rejected`, `timed_out`, and `approved` with non-null `execution_error` as recoverable — it can retry with adjusted args; the new request gets a fresh `request_id` with `parent_request_id` set to the prior id.

## Tool tiering and policy resolution

### Tier classification

Tools are classified by side-effect severity:

| Tier | Tools | Default policy |
|------|-------|----------------|
| **read** | All `get_*` tools (page posts, comments, insights, page info, fan count, share count, scheduled posts, comment replies, post permalink, top commenters, reactions breakdown, number of comments, number of likes) — and the pure-compute `filter_negative_comments` (no FB call) | `auto` |
| **write** | `post_to_facebook`, `post_image_to_facebook`, `reply_to_comment`, `update_post`, `schedule_post`, `send_dm_to_user`, `hide_comment`, `unhide_comment`, `bulk_hide_comments`, `bulk_unhide_comments` | `approve` |
| **destructive** | `delete_post`, `delete_comment`, `delete_comment_from_post`, `bulk_delete_comments` | `approve_confirm` |

Tier is set declaratively on each tool via a one-line decorator: `@policy.tool(tier="write")`. New tools must explicitly tag their tier; an untagged tool defaults to `approve` (fail-safe).

### Policy resolution

For each tool call:

1. Read `tool_policy` row by `tool_name`. If absent, fall back to tier default.
2. If `policy = auto`: execute directly.
3. If `policy = approve`: enqueue, normal approval flow.
4. If `policy = approve_confirm`: enqueue, dashboard renders the inbox card with destructive-action treatment (red header, second confirm-click required to approve).

The Settings page lets the human override any tool's policy and timeout. Changes take effect on the next call.

## Edit UX — introspection-driven forms with per-field hints

When the human picks **Approve with edits**, the dashboard renders a form built by introspecting the tool's signature:

- `str` → `<input type="text">` (or `<textarea>` per hint)
- `int` → `<input type="number">` (or `<input type="datetime-local">` per hint for unix-timestamp fields)
- `list[str]` → tag chip multi-input
- `dict[str, Any]` → JSON textarea (rare; only `filter_negative_comments`)

### Field hint registry

Hints live in a registry keyed by `(tool_name, field_name)`, populated at import time:

```python
# field_hints.py
from .field_hints import register_hint

register_hint("post_to_facebook", "message", widget="textarea", rows=4)
register_hint("post_image_to_facebook", "image_url", widget="image_preview")
register_hint("post_image_to_facebook", "caption", widget="textarea", rows=3)
register_hint("schedule_post", "publish_time",
              widget="datetime",
              note="Facebook requires 10 min < publish_time < 6 months")
register_hint("send_dm_to_user", "message", widget="textarea")
register_hint("update_post", "new_message", widget="textarea")
```

Registry pattern (not decorator stacking) is chosen so hint coupling with `@mcp.tool()` ordering doesn't matter. The form generator queries `field_hints.get(tool_name, field_name)` and falls back to type-hint-based widget selection if no hint exists.

## Dashboard surfaces

### Inbox (`/`)

Real-time list of pending requests. Each card:

- Tool name + tier badge (write / destructive)
- Time pending + countdown to timeout
- Proposed args rendered as a labeled key-value table
- Action buttons: **Approve** | **Approve & Edit** | **Approve & Note** | **Reject**

Approve fires immediately. Approve & Edit opens an inline form (introspection-driven, with hints applied). Approve & Note opens a textarea. Reject opens a textarea for a reason.

For `approve_confirm` tier (destructive), Approve requires a second confirm click ("Are you sure?" overlay).

Live updates via HTMX SSE on `/sse/inbox`: new pending rows appear immediately, decided rows fade out. No manual refresh.

Visual-only: no sound, no OS notification (per slice scope decision).

### Settings (`/settings`)

Per-tool grid:

| Tool | Tier | Policy | Timeout |
|------|------|--------|---------|
| post_to_facebook | write | `approve` ▼ | `1800s` |
| delete_post | destructive | `approve_confirm` ▼ | `1800s` |
| ... | | | |

Policy is a dropdown (`auto` / `approve` / `approve_confirm`). Timeout is a number input in seconds (with a "default" toggle to use the global 1800s). Changes save via HTMX PATCH; no save button.

### History (`/history`)

Read-only paginated list of past requests, newest first. Each row: tool name, tier, decision, time decided, executed-or-not, result summary. Click a row to expand: full proposed args, executed args, diff, note, error if any.

Filter by decision type (approved / rejected / timed_out / failed) via URL query params; no fancy search in v1.

## Foundation hardening (minimum required for slice 2)

The queue depends on Facebook API calls returning structured results so the dashboard executor can record success/failure correctly. Three minimal fixes go in `facebook_api.py`:

1. **Add `timeout=30` to every `requests.request` call.** Without this, a stalled FB connection hangs the dashboard executor indefinitely.
2. **Check HTTP status before parsing JSON.** On 4xx/5xx, return a structured error envelope (`{"error": {"http_status": ..., "graph_error": ...}}`) instead of raw `response.json()`.
3. **Stop mutating caller's `params` dict** for token injection — build a new dict locally.

The rest of slice 1 (pagination, retries with backoff, full structured logging) stays deferred.

## Error handling and edge cases

### Dashboard not reachable when MCP wants to enqueue
- MCP's auto-launch logic kicks in. If launch succeeds, retry enqueue.
- If launch fails after exhausting the port-fallback range or the binary is missing, MCP returns `{"status": "error", "reason": "dashboard_unreachable", ...}` to the agent.

### Dashboard crashes mid-wait
- MCP's `httpx` long-poll raises `ReadError` / `RemoteProtocolError`.
- MCP retries the long-poll up to 3 times with exponential backoff (1s, 2s, 4s).
- If the dashboard auto-restarts, the request row in SQLite is still there; the long-poll resumes against the same `request_id`.
- If retries exhaust, MCP returns `{"status": "error", "reason": "dashboard_crashed", ...}`.

### MCP crashes mid-wait
- Long-poll connection drops on the dashboard side.
- Request row stays in `pending`. Human can still approve from the Inbox.
- If approved, dashboard executor still runs the FB call (durability).
- The agent that asked is gone; result is recorded but never delivered.

### Two concurrent first-calls race to auto-launch
- PID file at `~/.facebook-mcp/dashboard.pid` with an exclusive file lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows).
- Whichever MCP instance acquires the lock first spawns the dashboard. The other waits up to 5s for `/health` and proceeds.

### Facebook API call fails after approval
- Dashboard executor records `state=failed`, `error=<envelope>` on the row.
- Long-poll returns the approved-but-execution-failed shape (above).
- Agent can decide to retry — creates a new row with `parent_request_id`.

### Edits change the tool's invariants
- Example: human edits `publish_time` to be 1 minute from now, but Facebook requires ≥10 min.
- Dashboard does not pre-validate (validation rules are FB-specific and brittle to changes).
- The FB call returns an error; the row goes `failed`; agent sees the error envelope.
- Future slice can add per-tool client-side validation hints.

### Agent retries a previously rejected/timed_out request
- New row, new `request_id`, `parent_request_id` set.
- Dashboard inbox shows a "(retry of X)" badge.

## Testing strategy

### Unit
- `policy.resolve(tool_name)` returns correct policy under various override combinations.
- Field hint registry lookups.
- `FacebookAPI` error envelope generation under HTTP failures (mocked via `responses`).
- Tier classification: every tool in `server.py` has a tier tagged.

### Integration (in-memory SQLite, mocked Facebook API)
- Full request lifecycle: agent enqueues → dashboard renders → human approves → executor runs → result returns to agent.
- Reject path: no FB call is made.
- Timeout path: row marked `timed_out`, no FB call.
- Approve-with-edits: `args_executed` differs from `args_proposed`; FB call uses edits.
- Concurrent enqueue/decide: row state transitions are atomic.
- Retry creates new row with `parent_request_id`.

### End-to-end (real SQLite + real local dashboard, mocked FB API)
- Auto-launch from clean state, request flows end to end.
- MCP restart with pending row: row remains, human can still decide, FB call still happens.
- Dashboard restart with active long-poll: MCP retry succeeds, request flows end to end.

CI runs unit + integration on every PR; e2e on a manual workflow trigger.

## Risks and known issues

### Risks accepted by the user
- **30-min sync wait + visual-only notification combo.** If the human steps away from the dashboard tab, the agent hangs for up to 30 minutes per write call. Mitigation: `timed_out` response is well-defined; the agent recovers gracefully. The human can lower per-tool timeouts in Settings if they find this painful.
- **Slice scope is ~5–8× current repo size.** Implementation will likely take longer than a typical slice; expect to land it incrementally on a long-lived branch.

### Implementation risks to validate during build
- **Cross-platform detached subprocess** is fiddlier than the design implies. If implementation reveals significant trouble, fall back to requiring the user to run `facebook-mcp-dashboard` manually, and add auto-launch in a polish slice.
- **Long-running tool calls and Claude Desktop.** A 30-min tool call has not been verified against Claude Desktop's transport / model behavior. If issues surface, the per-tool timeout knob lets the user dial down without architecture changes.
- **HTMX SSE on a long-lived dashboard process** with many reconnects — generally fine but warrants a soak test.

## Deferred work / future slices

- **Slice 1 remainder:** pagination across listing tools, retry/backoff for transient FB 5xx, full structured logging, `pyproject.toml` polish.
- **Slice 3 — Audit log:** queryable history, filter/search, export to CSV/JSON, retention policy.
- **Slice 4 — Webhooks:** subscribe to FB page events; new comments/messages/mentions enqueue agent reflection prompts.
- **Slice 5 — Messenger inbox:** list conversations, thread view in dashboard.
- **Slice 6 — Real sentiment:** swap keyword filter for an LLM/model-based scorer; use it to triage the Inbox.
- **Slice 7 — Video / Reels publishing.**
- **Slice 8 — Saved-reply templates and moderation rules engine.**
- **Slice 9 — Advanced dashboard:** multi-Page support, Facebook OAuth, agent activity timeline, composer view.
