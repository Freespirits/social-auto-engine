# ngrok setup for local OAuth and media

OAuth providers (LinkedIn, TikTok, YouTube, Notion) and most publishing
platforms (Instagram, LinkedIn, TikTok) require **publicly reachable**
URLs:

* OAuth callbacks must match the exact URL registered in the developer
  portal. `http://localhost:8000/oauth/...` does not match a portal
  entry like `https://socialengine.example.com/oauth/...`.
* Media uploads are not posted directly to the platform. Instagram and
  LinkedIn fetch the asset themselves from the URL we provide, so the
  URL must be reachable from the public internet.

ngrok solves both. It opens a tunnel from a public URL to your local
dashboard. Free tier is fine for testing; the URL changes each restart
unless you reserve a static one.

---

## 1. Install

**Windows (winget)**

```powershell
winget install ngrok.ngrok
```

**macOS (Homebrew)**

```bash
brew install ngrok
```

**Linux**

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update && sudo apt install ngrok
```

Verify:

```powershell
ngrok version
```

---

## 2. Authenticate (one-off)

Sign up at <https://dashboard.ngrok.com/signup>, copy your authtoken
from <https://dashboard.ngrok.com/get-started/your-authtoken>, then:

```powershell
ngrok config add-authtoken <your-token>
```

Token is stored at `%USERPROFILE%\AppData\Local\ngrok\ngrok.yml` on
Windows, `~/.config/ngrok/ngrok.yml` on macOS / Linux.

---

## 3. Start the dashboard

In one terminal:

```powershell
cd C:\Users\hoya2\facebook\social-engine
uvicorn dashboard.app:app --host 127.0.0.1 --port 8000 --reload
```

The dashboard is at <http://127.0.0.1:8000>.

---

## 4. Open the tunnel

In a second terminal:

```powershell
ngrok http 8000
```

ngrok prints a public URL such as `https://1a2b3c4d.ngrok-free.app`.
**Copy it without the trailing slash.**

If you have a paid reserved domain:

```powershell
ngrok http --domain=socialengine.your-name.ngrok.app 8000
```

---

## 5. Tell the dashboard about the public URL

Add the public URL to `~/.social-auto-engine/tokens.env` so OAuth
callback construction and media URLs both pick it up:

```powershell
notepad $HOME\.social-auto-engine\tokens.env
```

Add (or update):

```
OAUTH_REDIRECT_BASE_URL=https://1a2b3c4d.ngrok-free.app
MEDIA_PUBLIC_BASE_URL=https://1a2b3c4d.ngrok-free.app
```

`MEDIA_PUBLIC_BASE_URL` is optional — it falls back to
`OAUTH_REDIRECT_BASE_URL` when not set. Define it separately only when
you want media served from a different host than OAuth callbacks.

Restart `uvicorn` (Ctrl+C, re-run) so the new env vars are picked up.

---

## 6. Register the public callback in each provider portal

Use these URLs (substitute your ngrok host):

| Provider  | Callback URL                                                                |
| --------- | --------------------------------------------------------------------------- |
| LinkedIn  | `https://<host>/oauth/linkedin/callback`                                    |
| TikTok    | `https://<host>/oauth/tiktok/callback`                                      |
| YouTube   | `https://<host>/oauth/youtube/callback`                                     |
| Notion    | `https://<host>/oauth/notion/callback`                                      |

Where to register:

* **LinkedIn** — <https://www.linkedin.com/developers/apps> → your app
  → **Auth** → **Authorized redirect URLs**.
* **TikTok** — <https://developers.tiktok.com/apps/> → your app →
  **Login Kit** → **Redirect URI**. Also add the URL prefix under
  **URL prefixes** if you use the URL-prefix verification flow (see
  `TIKTOK_VERIFY_FILENAME` / `TIKTOK_VERIFY_TOKEN` in `.env.example`).
* **YouTube / Google** — <https://console.cloud.google.com/apis/credentials>
  → your OAuth 2.0 Client ID → **Authorized redirect URIs**.
* **Notion** — <https://www.notion.so/profile/integrations> → your
  public integration → **OAuth Domain & URIs** → **Redirect URIs**.

Each portal accepts multiple URLs, so you can keep a localhost entry
and a tunnel entry side by side.

---

## 7. Connect from the Settings page

Open <https://1a2b3c4d.ngrok-free.app/settings> (the public URL, not
localhost — cookies set during OAuth need to come back to the same
origin) and click **Connect** on each provider. You should be bounced
to the provider, asked to grant permission, and bounced back to the
Settings page with `Connected` showing.

---

## 8. Inspect what's flying through the tunnel

ngrok serves a request inspector at <http://127.0.0.1:4040>. Useful
for debugging OAuth failures: you can replay any request, see exact
headers, response bodies, and cookies. If you see `401` or `redirect
mismatch` errors, check the `redirect_uri` query parameter sent to the
provider against what's registered in the portal.

---

## Troubleshooting

**`HTTPException(400, "OAuth flow not properly initiated")`** — the
state cookie is missing. Cookies are set on the same origin, so make
sure you started the OAuth flow from the **public URL**, not from
localhost.

**`redirect_uri mismatch`** — the dashboard built one URL but the
provider's registered URL is different. Compare exactly. Common
mismatch causes:

* Trailing slash difference (`/callback` vs `/callback/`).
* `http` vs `https`.
* `127.0.0.1` vs `localhost`.

**Instagram / LinkedIn fail to publish images** — they could not fetch
the URL. Check `MEDIA_PUBLIC_BASE_URL` is set and points at the
running tunnel. Open the URL in a private browser window to confirm
it returns the image with `Content-Type: image/...`.

**ngrok URL changed after restart** — free tier rotates the domain on
every restart. Update `OAUTH_REDIRECT_BASE_URL`, `MEDIA_PUBLIC_BASE_URL`
**and** the registered URL in every provider portal. Or upgrade to a
reserved domain.

**Webhook payloads from Meta show wrong URL** — the verification
challenge uses whatever URL is registered. Re-register on the
ngrok URL each time the tunnel changes, or pay for a reserved domain
to make it stable.

---

## Production note

Do not run ngrok in production. For production:

* Buy a real domain.
* Put the dashboard behind nginx / Caddy with TLS (Let's Encrypt).
* Set `OAUTH_REDIRECT_BASE_URL=https://yourdomain.com`.
* Register the same URL in every provider portal.

ngrok is a development tool. Production needs a stable origin, and
that is cheaper than ngrok's paid tier once you commit to running
this for real.
