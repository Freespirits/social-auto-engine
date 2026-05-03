# Meta Business Suite Survival Guide

> Written for ops working with Social Engine. Meta dashboards rename buttons every quarter, so the *concepts* matter more than exact UI clicks.

---

## TL;DR — what you actually need

To make Social Engine publish to a real Meta channel you need exactly **three pieces** per channel:

| Channel    | Need #1               | Need #2                    | Need #3                       |
| ---------- | --------------------- | -------------------------- | ----------------------------- |
| Facebook   | Page ID               | Page Access Token (long)   | App with `pages_manage_posts` |
| Instagram  | IG Business User ID   | User Access Token (long)   | IG account linked to a Page   |
| WhatsApp   | Phone Number ID       | System User Access Token   | Approved message templates    |

Set them as env vars in `.env` (see end of this file). Adapters dry-run until they exist.

---

## 1. The mental model — why this is "hell"

You will see **five different dashboards** that all claim to do the same thing:

| Dashboard                         | What it's actually for                                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Meta Business Suite** (web/app) | Day-to-day posting, ads, inbox. **Not where you generate API tokens.** Skip for ops work.       |
| **Business Manager** (`business.facebook.com`) | Owns Pages, IG accounts, ad accounts, **System Users**. This is the ops console.    |
| **Meta for Developers** (`developers.facebook.com`) | Owns **Apps**. Each App has API access, secrets, webhook URLs.                  |
| **Graph API Explorer**            | Click-to-call any Graph endpoint with a token preview. Use this to debug 100% of token issues.  |
| **WhatsApp Manager**              | Phone numbers, message templates, deliverability. Only for WA-specific config.                  |

Rule of thumb:
- **Build/debug** → Meta for Developers + Graph API Explorer.
- **Permission/own/audit** → Business Manager.
- **Day-to-day human posting** → Business Suite. Ignore for our automation.

---

## 2. Tokens — short, long, page, system

Token types you'll meet, ranked from worst to best for automation:

| Type                       | Lifetime          | Use                                  | Verdict for Social Engine          |
| -------------------------- | ----------------- | ------------------------------------ | ---------------------------------- |
| User access token (short)  | 1–2 hours         | `Graph API Explorer` default         | ❌ never use in production         |
| User access token (long)   | ~60 days          | Web logins                           | ❌ rotates, breaks at 3 a.m.       |
| **Page access token (long)** | **Never expires** when derived from a long-lived user token | Posting to a Page | ✅ what we use for FB |
| **System User token**      | Never expires (until manually revoked) | Anything an SU is granted | ✅✅ best for WhatsApp + IG |

**Get a permanent Page Access Token** (the FB sweet spot):
1. Graph API Explorer → pick your App → request scopes `pages_show_list, pages_read_engagement, pages_manage_posts`.
2. Generate user token, then **Debug** it to verify scopes.
3. Exchange for a long-lived user token:
   ```
   GET /oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id={app-id}
       &client_secret={app-secret}
       &fb_exchange_token={short-user-token}
   ```
4. Get permanent Page tokens via:
   ```
   GET /me/accounts?access_token={long-user-token}
   ```
   Each Page in the response has its own long-lived `access_token`. **Store that** as `FB_PAGE_TOKEN`.
5. Sanity-check at Graph API Explorer → Debug Token. Expiration should read `Never`.

**Get a System User token** (the right answer for IG + WhatsApp):
1. Business Manager → Settings → Users → **System Users** → Create.
2. Give it admin role.
3. **Add Assets** → assign the Page, IG account, WhatsApp Business Account.
4. **Generate New Token** → pick the App → choose required permissions → **never expires**.
5. Store as `IG_TOKEN` and/or `WA_TOKEN`.

---

## 3. Permissions cheat sheet

What scope unlocks what endpoint:

| You want to…                   | Required permission                                  | App Review needed?  |
| ------------------------------ | ---------------------------------------------------- | ------------------- |
| Post text/photo to a FB Page   | `pages_manage_posts`, `pages_read_engagement`        | Yes for production  |
| Read a Page's recent posts     | `pages_read_engagement`                              | Yes for production  |
| Publish IG image post          | `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` | Yes |
| Send WhatsApp message          | `whatsapp_business_messaging`, `whatsapp_business_management` | Yes        |
| Read incoming WhatsApp webhook | (App-level subscription, not a token scope)          | No                  |

**App Review** is the gate. Until your App passes review, your tokens only work on:
- Users you've added as **Admins / Developers / Testers** in the App.
- Test phone numbers in the WA Manager.
- Test pages.

This is normal. Build with test assets, then submit for review.

---

## 4. WhatsApp Cloud API — minimum viable setup

The bit that catches everyone: **Cloud API ≠ On-Premises API**. Use Cloud.

1. **Meta for Developers** → Create App → type **Business**.
2. Add product → **WhatsApp**.
3. WhatsApp → **API Setup** page. You'll see:
   - A **temporary 24-hour access token** (good for first send).
   - A **test phone number** (sender) and a slot to add a recipient.
   - A **Phone number ID** (this is `WA_PHONE_ID`, NOT the actual phone number).
4. Send the canned `hello_world` template to your own phone to confirm wiring.
5. Move to a **System User token** (above) — never ship the temp token.
6. Add a real phone number (after you have a verified WA Business Account).

### Common WA errors and what they mean

| Error code              | Meaning                                                  | Fix                                                   |
| ----------------------- | -------------------------------------------------------- | ----------------------------------------------------- |
| `(#100) Invalid parameter` | Body shape is wrong, often `to` not E.164             | Use full international format `+972...`                |
| `(#131009) Parameter value is not valid` | Template doesn't exist or wrong language     | Check WhatsApp Manager → Message Templates             |
| `(#132000) Number of parameters does not match expected number` | Template has variables you didn't fill | Pass `components` array with `parameters` |
| `(#133010) Account not registered` | Sender phone hasn't completed registration       | Re-register in WhatsApp Manager                       |
| `(#133016) Address is not registered`     | Recipient hasn't ever opted in / is a test number | Add to allowed list during dev                  |
| `(#368) Temporarily blocked for policy violations` | You sent unsolicited or off-template marketing | Wait it out; tighten templates              |
| `Rate limit hit (#80007 or #4)`           | Spamming                                          | Back off; respect Meta's per-number tier               |

### 24-hour customer service window

Once a user messages you, you have **24 hours** to send free-form `text` messages. After that you can only send **approved templates** (utility / marketing / authentication). Our adapter accepts both — pass `template_name` for templates, plain `message` for text.

---

## 5. Facebook Page posting — minimum viable setup

1. Have a Page (Business Manager → Pages → owns it).
2. App with `pages_manage_posts`.
3. Permanent Page Access Token (from §2).
4. `FB_PAGE_ID` = numeric id (visible in Page Settings → About → "Page ID").
5. Post:
   ```
   POST /{page-id}/feed
       message=hello world
       access_token=...
   ```
6. Photo:
   ```
   POST /{page-id}/photos
       url=https://...image.jpg
       caption=hello
       access_token=...
   ```

Our `FacebookAdapter` does both.

### Common FB errors

| Error           | Fix                                                                |
| --------------- | ------------------------------------------------------------------ |
| `(#10)`         | Permission issue. Run Token Debugger; check granted scopes.        |
| `(#190)`        | Token expired or revoked. Re-derive a Page token from a long user token. |
| `(#100) Object does not exist` | Wrong page id, or page is unpublished               |
| `(#368)`        | Page temporarily restricted by Meta for content policy             |

---

## 6. Instagram — the two-step trap

You **cannot** publish to IG with one call. It is always:

```
POST /{ig-user-id}/media          → returns creation_id
POST /{ig-user-id}/media_publish  → publishes that creation_id
```

You also need:
- An IG **Business** or **Creator** account (not personal).
- That IG account **linked to a Facebook Page** in IG settings.
- The Page owned by the same Business Manager as your App.
- A token with `instagram_content_publish`.
- The `image_url` must be **publicly reachable** by Meta's servers (no localhost, no auth).

### Common IG errors

| Error                                | Cause                                                     |
| ------------------------------------ | --------------------------------------------------------- |
| `(#9004) Image URL is not accessible` | Hosted on localhost or behind auth                       |
| `(#10) Application does not have permission` | Missing `instagram_content_publish`              |
| `(#36003) Caption too long`          | IG caption max ≈ 2200 chars                              |
| `(#368)`                             | Hashtag spam / temporary block                            |

---

## 7. Webhooks — receiving status

For delivery / read receipts / inbox, you subscribe to webhooks:

1. Meta for Developers → your App → **Webhooks**.
2. Add Subscription for **WhatsApp** / **Page** / **Instagram**.
3. Callback URL = `https://<your-public-host>/webhook/<channel>`.
4. **Verify Token** = a string you make up; Meta sends it back during handshake.
5. App listens at that path, returns `hub.challenge` on GET, parses POST events.

For local dev: use **`ngrok`** or **`cloudflared tunnel`** to expose your local FastAPI.

We have not yet added the webhook routes to Social Engine — Step F territory.

---

## 8. Operational tips that aren't in the docs

- **Token rotation** — even "permanent" tokens can be invalidated when the user changes their FB password. Run a daily health check: `GET /me?access_token=...` returning 200 is the only reliable test.
- **App Review** — submit a screen recording showing the dashboard's approval flow + a single approved post. That's enough for `pages_manage_posts`. WA permissions are stricter; expect 2 rounds.
- **WhatsApp tier** — new numbers are at 250 unique recipients/24h. Tier up by sustaining quality and volume. Plan launches around tier upgrades.
- **Don't use Page tokens for IG.** They look interchangeable but IG endpoints often want the *user* token even when posting to a business IG.
- **Edge case** — Pages that haven't been "published" (page settings → general → page visibility) silently fail at posting.
- **Date/time** — Meta APIs are UTC. Schedules in the dashboard are UTC. Don't mix in local TZ.
- **Test recipients** — keep a Business Manager-approved test phone (your own) for WA, and a private FB Page that nobody sees, for end-to-end sanity checks.

---

## 9. .env template

Drop this in `social-engine/.env` (and add `.env` to `.gitignore`):

```
# Facebook Page
FB_PAGE_ID=123456789012345
FB_PAGE_TOKEN=EAA...                # permanent page token

# Instagram Business
IG_USER_ID=178000000000000
IG_TOKEN=EAA...                     # system user token

# WhatsApp Business Cloud
WA_PHONE_ID=987654321098765
WA_TOKEN=EAA...                     # system user token
WA_DEFAULT_LANG=en_US

# Optional pin to a specific Graph API version
FB_GRAPH_VERSION=v21.0
IG_GRAPH_VERSION=v21.0
WA_GRAPH_VERSION=v21.0
```

Adapters auto-switch from dry-run to live the moment the matching env vars are present. No code changes required.

---

## 10. When stuck

1. Open **Graph API Explorer**.
2. Paste your token in.
3. Hit **Debug** — verify expiry, app id, scopes.
4. Make the exact API call by hand. If it fails here, it's not our adapter.
5. If it works there but fails in code, diff the request — usually it's a missing `Authorization` header or wrong content-type.

The adapter logs `error_message` straight from Meta's response. Read that text first; it's almost always self-explanatory once you know §3 above.
