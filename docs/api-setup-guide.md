# API setup guide — every platform, zero to working token

> One document. All seven platforms. Copy-paste commands where possible.
> Estimated time per platform: 10-30 minutes (Meta takes longest because of App Review).

If you only use one or two platforms, skip the rest. Social Auto Engine
activates each adapter the moment its env vars are present. No code
changes, no config flags.

---

## Before you start

1. Copy `.env.example` to `.env` in the repo root.
2. You only fill in the sections for the platforms you want.
3. Tokens that come from OAuth (TikTok, LinkedIn, YouTube, Threads)
   are written automatically by the dashboard's OAuth callbacks.
   You just need the **client ID and secret** in `.env`.
4. Meta tokens (Facebook, Instagram, WhatsApp) are manual because
   Meta's token exchange is non-standard. The guide below walks through it.

---

## Facebook

**What you need:** a Facebook Page, a Meta App, and a permanent Page Access Token.

### Step 1 — Create (or pick) a Facebook Page

If you already have a Page, skip to Step 2. Otherwise: facebook.com > Pages > Create New Page.

### Step 2 — Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com/).
2. My Apps > Create App.
3. Choose "Other" > "Business".
4. Give it a name (e.g. "Social Engine"). Select your Business Portfolio if you have one.
5. Once created, note the **App ID** and **App Secret** (Settings > Basic). Put them in `.env`:
   ```
   META_APP_ID=123456789
   META_APP_SECRET=abc123...
   ```

### Step 3 — Get a permanent Page Access Token

This is the part that confuses everyone. Four token types exist. You want the last one.

| Token type | Lifetime | Use it? |
|---|---|---|
| Short-lived user token | 1-2 hours | No. Only for bootstrapping. |
| Long-lived user token | ~60 days | No. Expires at 3 a.m. and breaks your automation. |
| Short-lived page token | 1-2 hours | No. |
| **Long-lived page token** | **Never expires** | **Yes. This is the one.** |

**The exchange chain:**

```
Short user token  →  Long user token  →  Permanent page token
    (1 hour)           (60 days)           (never expires)
```

**Do it:**

1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Select your App from the dropdown.
3. Click "Generate Access Token". Grant these scopes:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_engagement`
   - `pages_read_user_content`
4. You now have a **short-lived user token**. Run the helper script:
   ```bash
   python -m scripts.refresh_token <PASTE_SHORT_TOKEN_HERE>
   ```
   This exchanges it for a long-lived user token, then derives the permanent page token, and writes both to `.env`.

5. Verify: open Graph API Explorer, paste the token, click **Debug**. Expiration should say **Never**.

**Manual alternative** (if you want to understand the plumbing):

```bash
# Exchange short → long user token
curl "https://graph.facebook.com/v21.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=YOUR_APP_ID&\
client_secret=YOUR_APP_SECRET&\
fb_exchange_token=YOUR_SHORT_USER_TOKEN"

# Get permanent page token from the long user token
curl "https://graph.facebook.com/v21.0/me/accounts?\
access_token=YOUR_LONG_USER_TOKEN"
```

The second call returns a JSON array of Pages. Each entry has an `access_token` field. That is your permanent page token.

6. Put the values in `.env`:
   ```
   FACEBOOK_PAGE_ID=123456789012345
   FACEBOOK_ACCESS_TOKEN=EAAxxxxxxx...
   ```

### Step 4 — App Review (for production)

Until your App passes review, tokens only work for users added as admins/developers/testers on the App. This is fine for personal use.

For production (posting to any Page):
1. Meta for Developers > your App > App Review > Permissions.
2. Request `pages_manage_posts` and `pages_read_engagement`.
3. Submit a screen recording showing:
   - The dashboard's compose flow.
   - A post landing in the approval queue.
   - A human pressing Approve.
   - The post appearing on the Page.
4. Wait 1-5 business days. Usually approved on first try if the recording is clear.

### Common errors

| Error | Fix |
|---|---|
| `(#190) Invalid OAuth access token` | Token expired or revoked. Re-run the exchange chain. |
| `(#10) Permission denied` | Missing scope. Debug the token and check granted permissions. |
| `(#100) Object does not exist` | Wrong Page ID, or the Page is unpublished. |

---

## Instagram

**What you need:** an Instagram Business/Creator account linked to a Facebook Page, plus the same Meta App from above.

### Step 1 — Switch to a Business account

Instagram Settings > Account type and tools > Switch to professional account > Business. Link it to your Facebook Page when prompted.

### Step 2 — Get your IG User ID

In Graph API Explorer, with your page token:
```
GET /me/accounts?fields=instagram_business_account
```
The `instagram_business_account.id` is your `IG_USER_ID`.

### Step 3 — Token

Use the same token from the Facebook setup. Add `instagram_basic` and `instagram_content_publish` scopes.

Alternatively, create a **System User** in Business Manager (recommended for production):
1. Business Manager > Settings > Users > System Users > Create.
2. Give it admin role.
3. Add Assets: assign the Page and IG account.
4. Generate New Token > pick your App > choose IG scopes > never expires.

```
IG_USER_ID=178000000000000
IG_TOKEN=EAA...
```

### The two-step publish trap

Instagram does NOT allow single-call publishing. Every post is:
```
POST /{ig-user-id}/media          → returns creation_id
POST /{ig-user-id}/media_publish  → publishes that creation_id
```

Our adapter handles this automatically. But know that:
- The `image_url` must be **publicly reachable**. No localhost, no auth-gated URLs.
- There is a delay (sometimes 30+ seconds) between creation and publish-ready status.
- The adapter polls `GET /{creation_id}?fields=status_code` until `FINISHED`.

### Common errors

| Error | Fix |
|---|---|
| `(#9004) Image URL is not accessible` | Host image publicly. Use a CDN or a public S3 bucket. |
| `(#36003) Caption too long` | IG max is ~2,200 characters. |
| `(#25) Subcode 2207051` | IG container not ready. Adapter retries automatically. |

---

## WhatsApp

**What you need:** the same Meta App, a WhatsApp Business Account, and a phone number.

### Step 1 — Add WhatsApp to your App

Meta for Developers > your App > Add Product > WhatsApp.

### Step 2 — API Setup page

WhatsApp > API Setup. You will see:
- A **temporary 24-hour access token** (good for first test, never for production).
- A **test phone number** (sender).
- A **Phone Number ID** (this is `WHATSAPP_PHONE_NUMBER_ID`). NOT the actual phone number.
- A **WhatsApp Business Account ID** (top of the page).

### Step 3 — Test it

Send the canned `hello_world` template to your own phone to confirm wiring works.

### Step 4 — Permanent token

Same System User approach as Instagram:
1. Business Manager > System Users > generate token with `whatsapp_business_messaging` scope.
2. The Facebook page token also works for WhatsApp if the scopes are right.

```
WHATSAPP_PHONE_NUMBER_ID=987654321098765
WHATSAPP_BUSINESS_ACCOUNT_ID=123456789
```

### 24-hour window rule

Once a user messages you, you have 24 hours to send free-form text. After that, only approved **message templates** work (utility, marketing, authentication). Our adapter supports both.

### Common errors

| Error | Fix |
|---|---|
| `(#131009) Parameter value is not valid` | Template does not exist or wrong language code. Check WhatsApp Manager > Message Templates. |
| `(#100) Invalid parameter` | `to` field is not in E.164 format. Use `+972...` not `0544...`. |
| `(#133010) Account not registered` | Sender phone not registered. Re-register in WhatsApp Manager. |

---

## Threads

**What you need:** an Instagram account (same one), plus the same Meta App with Threads permissions.

### Step 1 — Add Threads permissions to your App

Meta for Developers > your App > Permissions > add `threads_basic` and `threads_content_publish`.

### Step 2 — Get Threads credentials

Threads uses its own OAuth flow. You need:
```
THREADS_APP_ID=123456789        # same as META_APP_ID
THREADS_APP_SECRET=abc123...    # same as META_APP_SECRET
```

### Step 3 — Connect via the dashboard

1. Start the dashboard: `python -m dashboard.app`
2. Go to Settings > Threads > Connect.
3. This opens the Threads OAuth consent screen.
4. Authorise. The callback writes `THREADS_ACCESS_TOKEN` and `THREADS_USER_ID` automatically.

Threads tokens expire after 60 days but are auto-refreshed by the adapter.

---

## TikTok

**What you need:** a TikTok developer account and an approved App.

### Step 1 — Register as a developer

Go to [developers.tiktok.com](https://developers.tiktok.com/) and sign up.

### Step 2 — Create an App

1. Manage Apps > Create.
2. Add these products:
   - **Login Kit** (required for OAuth)
   - **Content Posting API** (required for uploads)
   - **Display API** (optional, for reading videos)
3. Fill in:
   - **App name**: something descriptive, not generic. "Social Auto Engine" works.
   - **App description**: be detailed (see reapplication tips below).
   - **Terms of Service URL**: must be a live, public URL. Use `https://freespirits.github.io/social-auto-engine/TERMS.html` or host your own.
   - **Privacy Policy URL**: same. Use `https://freespirits.github.io/social-auto-engine/PRIVACY.html` or host your own.
   - **Redirect URI**: `http://localhost:7651/oauth/tiktok/callback`
4. Note the **Client Key** and **Client Secret**:
   ```
   TIKTOK_CLIENT_KEY=aw1234abcd...
   TIKTOK_CLIENT_SECRET=xyz789...
   ```

> **Naming trap:** TikTok's portal shows both "Client key" (alphanumeric, this is what the API uses) and a numeric "Client ID" (internal only, ignore it).

### Step 3 — Submit for review

TikTok requires App Review even for the inbox-upload tier (`video.upload` scope).

Request these scopes:
- `user.info.basic`
- `user.info.profile`
- `video.upload`
- `video.list`

Do NOT request `video.publish` on the first application. That is the direct-post scope and triggers a much stricter review. Get `video.upload` approved first, then apply for `video.publish` separately once you have a track record.

### Step 4 — Connect via the dashboard

Once approved:
1. Start the dashboard.
2. Settings > TikTok > Connect.
3. Authorise in TikTok's OAuth screen.
4. The callback writes `TIKTOK_ACCESS_TOKEN` and `TIKTOK_REFRESH_TOKEN` automatically.

### How inbox upload works

Videos land in the user's TikTok drafts, not published directly. The user opens TikTok, reviews, and taps Publish. We present this as a feature in the UI: "you stay in control."

### Rate limits

- 6 upload-init requests per minute per user token.
- Maximum 5 pending drafts in any 24-hour window.
- For PULL_FROM_URL: the source domain must be pre-verified in the TikTok developer portal.

### TikTok App Review — reapplication strategy

TikTok declines apps more often than Meta. Common reasons and fixes:

**1. "App description is insufficient"**

TikTok wants to understand exactly what your app does with their API. Do not write "social media manager". Write something like:

> Social Auto Engine is an open-source, self-hosted social media management dashboard. Users compose posts (text, images, video) in a web-based editor, preview them, and schedule them for publication. Every post enters a human-reviewed approval queue before anything is sent to any platform.
>
> For TikTok specifically, the app uses the Content Posting API (video.upload scope) to push approved videos to the user's TikTok inbox/drafts. The user then opens TikTok to review and publish. No content is published automatically without explicit user action in the TikTok app.
>
> The app is self-hosted. Each user connects their own TikTok account and manages their own content. There is no multi-tenant commercial service.

**2. "Missing or invalid Terms of Service / Privacy Policy"**

The URLs must:
- Be publicly accessible (not localhost).
- Be actual legal pages, not placeholders.
- Mention TikTok by name, saying you access TikTok data and how you handle it.

We ship `TERMS.html` and `PRIVACY.html` in the repo root. They are served at:
- `https://freespirits.github.io/social-auto-engine/TERMS.html`
- `https://freespirits.github.io/social-auto-engine/PRIVACY.html`

Make sure these URLs resolve before reapplying.

**3. "Demo video does not show the flow"**

TikTok reviewers want a screen recording showing:
1. User logs into your app.
2. User composes a video post.
3. User selects TikTok as the destination.
4. The post enters the approval queue.
5. A human approves.
6. The video appears in the TikTok drafts.

Record this with the dashboard running locally against a sandbox TikTok account. 60-90 seconds is enough. No narration needed, just clear screen recording.

**4. "Business verification required"**

Some apps get flagged for business verification. If this happens:
- Register the app under a business account, not a personal developer account.
- Provide a business website and contact email.
- If you do not have a registered business, use the open-source project URL and explain that it is a community project.

**5. General tips for reapplication**

- Wait at least 48 hours before reapplying. Immediate reapplies may be auto-declined.
- Fix every issue mentioned in the rejection email, not just one.
- The description field is the most important part. Write 3-4 paragraphs, not one sentence.
- Mention "open-source", "self-hosted", "user controls their own data" as these signal low risk.
- If you have a live demo, include the URL: `https://huggingface.co/spaces/Warpfreespirit/social-auto-engine`
- Screenshot of the approval queue is powerful evidence of human oversight.

---

## LinkedIn

**What you need:** a LinkedIn developer App with "Share on LinkedIn" product.

### Step 1 — Create a LinkedIn App

1. Go to [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps).
2. Create App. You need a LinkedIn Page to associate it with (create one if needed).
3. Under Products, request:
   - **Sign In with LinkedIn using OpenID Connect**
   - **Share on LinkedIn**
4. These are usually auto-approved within minutes.

### Step 2 — Configure OAuth

Auth tab > add redirect URL:
```
http://localhost:7651/oauth/linkedin/callback
```

### Step 3 — Add credentials to .env

```
LINKEDIN_CLIENT_ID=86xxxxxxxx
LINKEDIN_CLIENT_SECRET=WPxxxxxxxx
```

### Step 4 — Connect via the dashboard

Settings > LinkedIn > Connect. The OAuth flow handles the rest. The callback writes `LINKEDIN_ACCESS_TOKEN` automatically.

### Scopes

The member-tier gives you:
- `openid`, `profile`, `email` (login)
- `w_member_social` (post as the authenticated user)

This lets you post text, images, and articles to the user's own LinkedIn feed. Posting to a Company Page requires the Marketing Developer Platform (MDP), which is a separate, much harder review.

### Rate limits

100 posts per day per member.

### Common errors

| Error | Fix |
|---|---|
| `401 Unauthorized` | Token expired. LinkedIn tokens last 60 days. Re-connect via OAuth. |
| `403 Access denied` | Missing `w_member_social` scope. Check your App's approved products. |

---

## YouTube

**What you need:** a Google Cloud project with YouTube Data API v3 enabled.

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Create a new project (or use an existing one).
3. APIs & Services > Library > search "YouTube Data API v3" > Enable.

### Step 2 — Create OAuth credentials

1. APIs & Services > Credentials > Create Credentials > OAuth 2.0 Client ID.
2. Application type: **Web application**.
3. Add Authorised redirect URI:
   ```
   http://localhost:7651/oauth/youtube/callback
   ```
4. Note the **Client ID** and **Client Secret**.

### Step 3 — Configure consent screen

APIs & Services > OAuth consent screen.
- User type: External (unless you have a Google Workspace org).
- Fill in app name, support email, developer contact.
- Add scopes: `youtube.upload`, `youtube.readonly`.
- Add your own Google account as a test user.

Until you submit the consent screen for Google's verification, only test users can authorise. This is fine for personal use.

### Step 4 — Add to .env

```
YOUTUBE_CLIENT_ID=123456-xxxxx.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=GOCSPX-xxxxx
```

### Step 5 — Connect via the dashboard

Settings > YouTube > Connect. The OAuth flow opens Google's consent screen. Authorise, and the callback writes tokens automatically.

### Quota

YouTube uses a quota-unit system:
- `videos.insert` (upload): 1,600 units
- `channels.list`: 1 unit
- Daily default: 10,000 units = roughly 6 uploads/day on the default quota

If you need more, submit a quota increase request via the Google Cloud console. Include your use case and expected volume.

### Common errors

| Error | Fix |
|---|---|
| `quotaExceeded` | Hit the daily quota. Wait until midnight Pacific time, or request an increase. |
| `forbidden` | OAuth consent screen not verified, and user is not a test user. Add them. |
| `invalidVideoMetadata` | Title too long (max 100 chars) or missing required fields. |

---

## X / Twitter

**Status:** not yet shipped in Social Auto Engine. Listed here for completeness.

X's API costs real money. The free tier is unreliable and changes without notice.

| Tier | Monthly cost | Write limit |
|---|---|---|
| Free | $0 | ~1,500 posts/month (changes often) |
| Basic | ~$200 | ~50,000 posts/month |
| Pro | $5,000 | ~1,000,000 posts/month |

Social Auto Engine does not include X credentials out of the box. When the X adapter ships, users will supply their own X developer credentials and pay their own X bill.

> **Common confusion:** X Premium ($8-$16/month) is a consumer subscription (blue check, longer posts). It does NOT unlock the developer API. The two are completely separate.

---

## Quick reference — where each token lives

| Platform | Auth method | Token written by | Token lifetime | Env vars |
|---|---|---|---|---|
| Facebook | Manual exchange | `scripts.refresh_token` | Never expires | `FACEBOOK_PAGE_ID`, `FACEBOOK_ACCESS_TOKEN` |
| Instagram | System User or manual | Manual | Never expires | `IG_USER_ID`, `IG_TOKEN` |
| WhatsApp | System User | Manual | Never expires | `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID` |
| Threads | OAuth | Dashboard callback | 60 days (auto-refreshed) | `THREADS_APP_ID`, `THREADS_APP_SECRET` |
| TikTok | OAuth | Dashboard callback | 24 hours (auto-refreshed) | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` |
| LinkedIn | OAuth | Dashboard callback | 60 days | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` |
| YouTube | OAuth | Dashboard callback | 1 hour (auto-refreshed via refresh token) | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` |

---

## When stuck

1. **Read the error message.** Every adapter logs the platform's raw error response. It is almost always self-explanatory.
2. **Debug the token.** For Meta: paste it into [Graph API Explorer](https://developers.facebook.com/tools/explorer/) > Debug. Check expiry, app, scopes.
3. **Test the API call by hand.** Use curl or the platform's API explorer. If it fails there, the problem is not our adapter.
4. **Check the dashboard logs.** Run with `DEMO_MODE=0` and watch the terminal output.
5. **Open an issue.** [github.com/Freespirits/social-auto-engine/issues](https://github.com/Freespirits/social-auto-engine/issues) with the error message and platform.

---

## Related docs

- [Meta Business Suite survival guide](meta-survival-guide.md) — deep dive into Meta's five dashboards, token types, and common errors.
- [Platform tiers](platform-tiers.md) — rate limits, pricing, and capability matrices for all platforms.
- [Try the MCP server](try-mcp.md) — five-minute setup for Claude Desktop / Claude Code integration.
