# Try the MCP server in Claude

Five minutes from `git clone` to typing "List my recent Facebook posts" in
Claude Desktop or Claude Code and getting a real answer.

Social Auto Engine ships an MCP server (`server.py`) that exposes 15
always-on tools, 11 for the pipeline and approval queue plus 4 consolidated
Facebook Graph API read tools, and 4 more direct-write Facebook tools behind
an opt-in flag. This page is the shortest path to trying it.

---

## 1. Clone and install

```bash
git clone https://github.com/Freespirits/social-auto-engine.git
cd social-auto-engine
pip install -r requirements.txt
```

## 2. Add your Facebook Page token

Copy `.env.example` to `.env` and fill in two values:

```bash
FACEBOOK_PAGE_ID=your_page_id_here
FACEBOOK_ACCESS_TOKEN=your_long_lived_token_here
```

Don't have a long-lived Page token yet? Run the helper:

```bash
python -m scripts.refresh_token <SHORT_LIVED_USER_TOKEN>
```

It exchanges a short-lived user token (the kind Graph API Explorer gives
you) for a 60-day user token, then derives the Page token and writes it to
`.env` for you.

## 3. Wire the MCP server into Claude Desktop

Open `claude_desktop_config.json` (the path is shown in Claude Desktop →
Settings → Developer):

| OS      | Path                                                                |
|---------|---------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json`   |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                       |
| Linux   | `~/.config/Claude/claude_desktop_config.json`                       |

Add this entry under `mcpServers`, with the full path to your cloned repo:

```json
{
  "mcpServers": {
    "social-auto-engine": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/absolute/path/to/social-auto-engine"
    }
  }
}
```

Restart Claude Desktop. You should now see "social-auto-engine" in the
tools dropdown with 15 tools.

## 4. Wire it into Claude Code (alternative)

If you live in the terminal, Claude Code uses the same config schema:

```bash
claude mcp add social-auto-engine \
  --command python \
  --args -m server \
  --cwd "$(pwd)"
```

Or hand-edit `~/.config/claude/mcp.json` with the same JSON block as above.

## 5. Try it

In any conversation:

* "List my five most recent Facebook posts."
* "Show the top commenters on my latest post." (via `facebook_get_comments`)
* "What is my Page's fan count?" (via `facebook_get_page_info`)
* "Draft a Facebook post about our new feature." (via
  `socialblast_create_draft`, lands in the approval queue)
* "Hide every comment containing the word 'spam'." (requires the opt-in
  `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` flag and `facebook_moderate_comment`)

By default, the only way to get a post onto Facebook via MCP is
`socialblast_create_draft`. It lands in the dashboard's approval queue at
`http://127.0.0.1:7651` with status `pending`. Nothing publishes until a
human presses Approve. This is the project's safety spine, not a setting
you can flip.

The four direct-write tools (`facebook_publish_now`, `facebook_manage_post`,
`facebook_moderate_comment`, `facebook_send_dm`) are opt-in only, registered
solely when `SOCIALBLAST_ALLOW_DIRECT_WRITES=true` is set. When enabled,
they publish to Facebook immediately, with no approval-queue review step.
Only set that flag if you understand and accept that trade-off.

---

## What's inside the MCP server

**Pipeline and approval queue (11, always on)**

| Tool | What it does |
|---|---|
| `socialblast_status` | Which AI backends and platforms are configured |
| `socialblast_generate_campaign` | Generate a 7-day multi-platform campaign into the queue |
| `socialblast_enrich_post` | Run the AI media pipeline on one pending post |
| `socialblast_enrich_campaign` | Enrich every pending post in a campaign |
| `socialblast_predict_virality` | Score a caption's viral potential |
| `socialblast_list_pending` | List posts awaiting approval |
| `socialblast_create_draft` | Create a new pending post |
| `socialblast_edit_pending` | Edit a pending post's fields |
| `socialblast_reject_pending` | Reject a pending post |
| `socialblast_search_posts` | Full-text search across the queue |
| `socialblast_queue_stats` | Counts by status, plus the scheduled queue |

None of these tools can approve or publish a post. Approval stays
human-only, from the dashboard.

**Facebook read-only (4, always on)**

| Tool | What it does |
|---|---|
| `facebook_get_posts` | Recent Page posts, optionally including scheduled |
| `facebook_get_post_engagement` | Reactions, comments, shares, permalink, impressions in one call |
| `facebook_get_comments` | Comments on a post, optionally with reply threads |
| `facebook_get_page_info` | Extended Page metadata including fan count |

**Direct-write (4, opt-in only via `SOCIALBLAST_ALLOW_DIRECT_WRITES=true`)**

| Tool | What it does |
|---|---|
| `facebook_publish_now` | Publish text or image immediately, or via Graph's native scheduling |
| `facebook_manage_post` | Update or delete a live post |
| `facebook_moderate_comment` | Reply, hide, unhide, or delete one or more comments |
| `facebook_send_dm` | Send a Messenger DM immediately |

Full reference: [`server.py`](../server.py) (every `@mcp.tool()` decorated
function is exposed automatically), or the fuller MCP section in
[README.md](../README.md#mcp-server-15-tools-for-claude-4-more-behind-an-opt-in-flag).

---

## See it before you install

A public read-only demo of the dashboard lives at
**[freespirits.github.io/social-auto-engine](https://freespirits.github.io/social-auto-engine/)** for the landing page
and on **[Hugging Face Spaces](https://huggingface.co/spaces/Warpfreespirit/social-auto-engine)**
for the live dashboard (with dummy data, all writes disabled).

---

## Help, it broke

Common stumbles:

* **"OAuthException: error validating access token"** — your token expired.
  Run `python -m scripts.refresh_token <NEW_SHORT_LIVED_USER_TOKEN>`.
* **"FACEBOOK_PAGE_ID is required"** — `.env` not loaded. Make sure you ran
  `python -m server` from the repo root, not a different cwd.
* **Claude Desktop doesn't see the tools** — restart Claude Desktop after
  editing the config. The reload-on-save behaviour is not reliable yet.
* **"No module named server"** — your `cwd` in the MCP config is wrong.
  Use the absolute path to the repo root.

For anything else: [open an issue](https://github.com/Freespirits/social-auto-engine/issues).
