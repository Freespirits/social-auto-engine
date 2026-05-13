# Try the MCP server in Claude

Five minutes from `git clone` to typing "List my recent Facebook posts" in
Claude Desktop or Claude Code and getting a real answer.

Social Auto Engine ships an MCP server (`server.py`) that exposes 37
Facebook Graph API tools and the approval queue. This page is the shortest
path to trying it.

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
tools dropdown with 37 Facebook tools.

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
* "Show the top commenters on my latest post."
* "Hide every comment containing the word 'spam'."
* "What is my Page's fan count?"

Every read tool runs immediately. Every **write** tool (post, reply,
schedule, hide, delete) lands in the dashboard's approval queue at
`http://127.0.0.1:7651` with status `pending`. Nothing publishes until a
human presses Approve. This is the project's safety spine, not a setting
you can flip.

---

## What's inside the MCP server

| Category    | Tool count | Examples |
|-------------|------------|----------|
| Publishing  | 4          | `post_to_facebook`, `schedule_facebook_post`, `delete_facebook_post`, `edit_facebook_post` |
| Comments    | 8          | `reply_to_comment`, `hide_comment`, `bulk_hide_comments`, `negative_sentiment_filter` |
| Analytics   | 9          | `get_page_insights`, `get_post_insights`, `get_top_commenters` |
| Messaging   | 3          | `send_private_message`, `mark_message_seen`, `list_threads` |
| Page admin  | 6          | `get_page_info`, `get_fan_count`, `list_subscribers` |
| Misc        | 7          | `search_posts`, `find_post_by_keyword`, `list_recent_media` |

Full reference: [`server.py`](../server.py) (every `@mcp.tool()` decorated
function is exposed automatically).

---

## See it before you install

A public read-only demo of the dashboard lives at
**[freespirits.github.io/social-auto-engine](https://freespirits.github.io/social-auto-engine/)** for the landing page
and on **[Hugging Face Spaces](https://huggingface.co/spaces/Freespirits/social-auto-engine)**
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
