# Development setup

Everything you need to run Social Auto Engine locally, contribute, and not break things.

## Prerequisites

- Python 3.11+
- Git
- A Meta developer account (free) at https://developers.facebook.com

## Clone and install

```bash
git clone https://github.com/Freespirits/social-auto-engine.git
cd social-auto-engine
git submodule update --init  # pulls Postiz reference under references/postiz/

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

| Variable | Where to get it | Required? |
|----------|----------------|-----------|
| `FACEBOOK_PAGE_ID` | Your Page's About section or Graph API `/me/accounts` | Yes |
| `FACEBOOK_ACCESS_TOKEN` | [Graph API Explorer](https://developers.facebook.com/tools/explorer/) | Yes |
| `META_APP_ID` | Meta App Dashboard | For token refresh |
| `META_APP_SECRET` | Meta App Dashboard (Settings > Basic) | For token refresh |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp section of your Meta App | For WhatsApp only |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp section of your Meta App | For WhatsApp only |

### Getting a Facebook token

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app from the dropdown
3. Click the "User or Page" dropdown and select **your Page** (not User Token)
4. Add these permissions: `pages_manage_posts`, `pages_read_engagement`, `pages_manage_engagement`, `pages_read_user_content`
5. For Instagram add: `instagram_basic`, `instagram_content_publish`
6. Click **Generate Access Token**
7. Paste the token into `.env` as `FACEBOOK_ACCESS_TOKEN`

Note: Graph API Explorer tokens expire in ~1 hour. For long-lived tokens you need `META_APP_SECRET` and can run the exchange via the API (see issue #2).

## Run the dashboard

```bash
python -m dashboard.app
```

Open http://127.0.0.1:7651

The dashboard uses SQLite (stored at `~/.social-auto-engine/dashboard.db`). The database is created automatically on first run.

## Run the MCP server

For Claude Desktop or any MCP client:

```bash
python server.py
```

This starts the FastMCP server over stdio with 37 Facebook Graph API tools.

### Claude Desktop config

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "social-auto-engine": {
      "command": "python",
      "args": ["C:/path/to/social-auto-engine/server.py"],
      "env": {
        "FACEBOOK_PAGE_ID": "your-page-id",
        "FACEBOOK_ACCESS_TOKEN": "your-token"
      }
    }
  }
}
```

## Project structure

```
server.py                  # FastMCP entry point (37 Facebook tools)
manager.py                 # Facade over all platform adapters
facebook_api.py            # Facebook Graph API
instagram_api.py           # Instagram Graph API (two-step publish)
whatsapp_api.py            # WhatsApp Business Cloud API
config.py                  # Env config loader

dashboard/
  app.py                   # FastAPI routes
  db.py                    # SQLite persistence (WAL mode)
  templates/
    index.html             # Main inbox page
    settings.html          # Connected accounts + env overview
    _columns.html          # HTMX partial: pending/published/log
    _toast.html            # Toast notification component
  static/
    styles.css             # Dark-mode design system (~1200 lines)
    favicon.svg            # Brand gradient SVG

skills/                    # Markdown content workflows (17 skills)
docs/specs/                # Architecture specs
docs/integrations.md       # Curated OSS projects
references/postiz/         # Git submodule: Postiz for pattern study
```

## Adding a new platform adapter

Follow the pattern in `instagram_api.py`:

1. Create `<platform>_api.py` in the project root
2. Class with `__init__(self)` that reads tokens from env
3. `_request(method, endpoint, **kwargs)` wrapper with error handling
4. Public methods: `get_account_info()`, `publish_*()`, etc.
5. Wire it into `manager.py` (import + delegate methods)
6. Add the `elif platform == "<platform>"` branch in `dashboard/app.py` `_publish_post()`
7. Add env vars to `.env.example`
8. Add the platform icon CSS already exists in `styles.css` (`.platform-icon.li`, `.x`, `.tt`)

## Running lint

```bash
pip install ruff
ruff check .
```

## Running tests

```bash
pip install pytest pytest-asyncio httpx
pytest
```

(Test suite is being built in issue #6.)

## Database

SQLite in WAL mode at `~/.social-auto-engine/dashboard.db`. To reset:

```bash
rm ~/.social-auto-engine/dashboard.db
python -m dashboard.app  # recreates it
```

The `post` table schema:

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key, autoincrement |
| platform | TEXT | facebook, instagram, whatsapp |
| account_name | TEXT | Display name |
| message | TEXT | Post body |
| image_url | TEXT | For Instagram (required) |
| recipient | TEXT | For WhatsApp (E.164 phone) |
| template_name | TEXT | For WhatsApp templates |
| status | TEXT | pending, published, failed, rejected |
| platform_post_id | TEXT | ID returned by the platform |
| error_message | TEXT | If failed |
| permalink_url | TEXT | Link to the live post |
| created_at | TEXT | ISO 8601 |
| decided_at | TEXT | When approved/rejected |
| published_at | TEXT | When actually published |

## Common issues

**Token expired**: Graph API Explorer tokens last ~1 hour. You'll see `OAuthException` errors. Generate a new token and update `.env`.

**Instagram publish fails**: Instagram requires a publicly accessible image URL. Local file paths won't work. Use an image hosting service or a direct link.

**WhatsApp "outside 24h window"**: Free-form messages only work within 24 hours of the user's last message to you. Use templates for outbound messages.

**Dashboard won't start**: Make sure you're running from the project root so `manager.py` and `facebook_api.py` are importable. Check `python -c "from manager import Manager; print('ok')"`.

**Port already in use**: Set `DASHBOARD_PORT=7652` in `.env` or kill the existing process.
