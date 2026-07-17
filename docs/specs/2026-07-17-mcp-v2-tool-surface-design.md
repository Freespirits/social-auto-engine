# MCP v2 tool surface design

**Date:** 2026-07-17
**Status:** Approved design, awaiting implementation plan
**Owner:** maintainer

## 1. Problem

The MCP server (`server.py`) currently exposes 46 tools. Forty of them are inherited from the original `facebook-mcp-server` fork and have three structural problems.

1. **They bypass the approval queue.** Tools such as `post_to_facebook`, `delete_post` and `bulk_delete_comments` write directly to Facebook. This contradicts the architectural spine in CLAUDE.md section 5, which requires every external write to go through the approval queue or be opt-in with a clearly visible warning.
2. **They bloat the model's context.** Six separate tools exist just to count individual reaction types, and four more for individual impression metrics, even though consolidated equivalents exist. A 46-tool surface degrades an LLM's tool selection accuracy and wastes context on every session.
3. **They have no error handling.** Graph API failures (expired token, deprecated metric, rate limit) return raw JSON error payloads with no guidance. Meta removed many post-level insight metrics during 2024 and 2025, so several tools now fail on every call.

There is also a confirmed bug. The documented environment variable is `FACEBOOK_ACCESS_TOKEN` (per `.env.example` and `config.py`) but `socialblast_status` in `server.py` and `dashboard/health.py` check `FACEBOOK_PAGE_ACCESS_TOKEN`, so both always report Facebook as unconfigured even when publishing works.

## 2. Goals

- The MCP surface respects the approval queue by default. Direct writes exist only behind an explicit opt-in flag.
- Tool count drops from 46 to 15 core tools plus 4 flag-gated tools, with no loss of real capability.
- Every tool returns a uniform success or error envelope with actionable hints.
- The server is packaged as a usable product feature: registration instructions, migration table, updated README and CHANGELOG.

## 3. Non-goals

- No changes to `facebook_api.py` semantics. The dashboard consumes it and must be unaffected.
- No new platform adapters. Multi-platform drafting goes through the queue, which already supports a platform column.
- No sentiment analysis replacement for `filter_negative_comments`. The calling LLM analyses sentiment on raw comments better than a keyword list.

## 4. Tool surface

### 4.1 Pipeline and queue tools (11, always registered)

Six existing tools are kept unchanged in behaviour: `socialblast_status`, `socialblast_generate_campaign`, `socialblast_enrich_post`, `socialblast_enrich_campaign`, `socialblast_predict_virality`, `socialblast_list_pending`.

Five new tools wrap existing functions in `dashboard/db.py`:

| Tool | Signature | Wraps |
|---|---|---|
| `socialblast_create_draft` | `(message: str, platform: str, image_url: str \| None, video_url: str \| None, scheduled_time: str \| None)` | `db.create_post(status="pending")` |
| `socialblast_edit_pending` | `(post_id: int, message: str \| None, image_url: str \| None, video_url: str \| None, scheduled_time: str \| None)` | `db.update_post` |
| `socialblast_reject_pending` | `(post_id: int)` | `db.reject_post` |
| `socialblast_search_posts` | `(q: str, status: str \| None, limit: int)` | `db.search_posts` |
| `socialblast_queue_stats` | `()` | `db.stats` and `db.list_scheduled` |

Guard rails:

- `socialblast_edit_pending` and `socialblast_reject_pending` refuse to touch posts whose status is not `pending`. The error hint explains that approved and published posts are managed from the dashboard.
- `socialblast_create_draft` validates `platform` against the known platform list and validates `scheduled_time` as ISO 8601.
- No MCP tool can approve or publish a post. Approval stays human-only in the dashboard.

### 4.2 Facebook read-only tools (4, always registered)

| Tool | Notes |
|---|---|
| `facebook_get_posts` | Accepts `limit` and an `after` pagination cursor. Optional `include_scheduled` flag folds in the old `get_scheduled_posts`. |
| `facebook_get_post_engagement` | One call returns reaction breakdown, comment count, share count, permalink and impressions. Metrics Meta has deprecated return `null` with a note instead of failing the whole call. |
| `facebook_get_comments` | Accepts `include_replies`. Replaces `get_post_comments`, `get_comment_replies` and `get_number_of_comments`. |
| `facebook_get_page_info` | Includes `fan_count`. Replaces `get_page_info` and `get_page_fan_count`. |

### 4.3 Direct-write tools (4, registered only when flag is set)

Registered only when `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` is present in the environment. Each tool's docstring opens with a warning that it bypasses the approval queue.

| Tool | Consolidates |
|---|---|
| `facebook_publish_now` | `post_to_facebook`, `post_image_to_facebook`, `schedule_post` (via optional `scheduled_publish_time`) |
| `facebook_manage_post` | `update_post`, `delete_post` (via `action` parameter) |
| `facebook_moderate_comment` | `reply_to_comment`, `hide_comment`, `unhide_comment`, `delete_comment`, `delete_comment_from_post` and the three bulk variants (accepts a list of comment ids and an `action` parameter) |
| `facebook_send_dm` | `send_dm_to_user` |

### 4.4 Removed without replacement

- `filter_negative_comments`. Keyword matching gives worse results than the calling LLM reading `facebook_get_comments` output.
- `get_post_top_commenters`. Trivially computed by the caller from comments output.
- The six per-reaction and four per-impression metric tools. Covered by `facebook_get_post_engagement`.

## 5. Error envelope

A single decorator in a new `mcp_support.py` wraps every tool:

```python
{"success": true, "data": ...}
{"success": false, "error": {"code": str, "message": str, "hint": str}}
```

Behaviour:

- The decorator inspects results from `facebook_api.py` for a Graph API `error` key and rewraps it. `facebook_api.py` itself is not modified.
- Known Graph error codes map to hints. Code 190 (expired or invalid token) points to `scripts/refresh_token.py` and the dashboard settings page. Code 100 on an insights call lists the metrics that remain supported. Codes 4, 17 and 32 (rate limits) advise waiting.
- Missing configuration is caught before any network call. The error names the exact environment variable to set.
- Unexpected exceptions are caught and returned as `{"success": false}` envelopes so a tool call never crashes the MCP server process.

## 6. Environment variable fix

`FACEBOOK_ACCESS_TOKEN` is the canonical name everywhere. `socialblast_status` and `dashboard/health.py` are updated to check it first and fall back to `FACEBOOK_PAGE_ACCESS_TOKEN` for anyone who configured the wrong documented name. `.env.example` gains `SOCIALBLAST_ALLOW_DIRECT_WRITES=false` with a comment explaining what enabling it does.

## 7. File plan

| File | Change |
|---|---|
| `server.py` | Rewritten around the new surface. Tool definitions only, roughly 350 lines. |
| `mcp_support.py` | New. Error envelope decorator, Graph error mapping, flag check, config validation helpers. |
| `manager.py` | Gains `get_post_engagement`. Methods used only by removed MCP tools are deleted after a grep confirms the dashboard does not call them. |
| `dashboard/health.py` | Env var fix (section 6). |
| `.env.example` | New flag documented. |
| `tests/test_mcp_socialblast_tools.py` | Extended (section 8). |
| `README.md` | MCP section rewritten: tool table, registration instructions, flag documentation. |
| `CHANGELOG.md` | v0.7 entry marked BREAKING with a migration table from old tool names to new ones. |

## 8. Testing

Extend `tests/test_mcp_socialblast_tools.py` following its existing patterns:

- Queue tools run against a temporary SQLite database. Cover create, edit, reject, search and stats, plus the pending-only guard.
- The error envelope is tested against mocked Graph responses: expired token, deprecated metric, rate limit and a healthy response.
- Direct-write tools are absent from the registered tool list when the flag is unset and present when it is set.
- `facebook_get_post_engagement` degrades gracefully when an insights metric returns an error.

## 9. Compatibility and rollout

This is a breaking change for users who adopted the server from the awesome-mcp listings.

- Version becomes 0.7.
- The CHANGELOG entry includes a migration table mapping every removed tool to its replacement, and states that setting `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` restores direct-write capability through the consolidated tools.
- The README MCP section shows how to register the server with `claude mcp add` and with a `.mcp.json` snippet.
- User-facing copy follows project voice rules: British English, no em dashes, no semicolons in prose.

## 10. Success criteria

- `socialblast_status` reports Facebook as configured when `FACEBOOK_ACCESS_TOKEN` is set.
- With no flag set, the registered tool list contains exactly 15 tools and none of them can write to an external platform.
- A Graph API failure returns a `{"success": false}` envelope with a non-empty hint, never a raw traceback or raw Graph JSON.
- All new and existing tests pass.
