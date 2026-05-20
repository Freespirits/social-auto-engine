# HiggsField API — reverse-engineering notes

This is what we know about HiggsField's API from inspecting a HAR capture
of the higgsfield.ai web app. Use these notes to refine the adapter at
`ai_services/higgsfield.py`.

These are **not official docs**. Treat them as working hypotheses to verify.

## Hosts

| Host | Purpose |
|---|---|
| `fnf.higgsfield.ai` | The actual JSON API (jobs, workspaces, user) |
| `clerk.higgsfield.ai` | Auth provider (Clerk-managed sessions) |
| `cms.higgsfield.ai` | CMS for tips, notices, public content |
| `cdn.higgsfield.ai` | Media CDN (generated videos, thumbnails) |
| `static.higgsfield.ai` | Static assets (model preview clips) |
| `images.higgs.ai` | Image CDN (note the different TLD) |
| `amplitude.higgsfield.ai` | Amplitude analytics proxy (ignore) |
| `o4509169762697216.ingest.de.sentry.io` | Sentry error tracking (ignore) |

## Endpoints observed (web app)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/jobs/v2/{model_id}` | **Start a generation** (e.g. `/jobs/v2/seedance_2_0`) |
| `GET` | `/jobs/{uuid}/status` | Poll job status |
| `POST` | `/jobs/{uuid}/view` | Mark a job as viewed |
| `GET` | `/workspaces/wallet` | Credit balance |
| `GET` | `/workspaces` | List workspaces |
| `GET` | `/workspaces/details` | Workspace info |
| `POST` | `/workspaces/context` | Switch active workspace, body `{"workspace_id": "..."}` |
| `GET` | `/user`, `/user/features`, `/user/meta`, `/user/settings` | User info |
| `GET` | `/reference-elements` | List saved characters / face refs |
| `GET` | `/video/{uuid}/meta` | Video metadata |
| `POST` | `/publications/check-likes` | Like-counter check, body is array of UUIDs |
| `GET` | `/tours` | Product tours |
| `GET` | `/subscriptions/plans` | Pricing plans |

## Request shape — generation (verified)

```http
POST https://fnf.higgsfield.ai/jobs/v2/seedance_2_0
Content-Type: application/json
Origin: https://higgsfield.ai
Referer: https://higgsfield.ai/

{
  "params": {
    "prompt": "<<<9af97f85-c730-4c39-95b5-2502e6bd12b0>>> rest of the description ...",
    "duration": 15,
    "aspect_ratio": "16:9",
    "resolution": "720p",
    "generate_audio": true,
    "width": 1280,
    "height": 720,
    "medias": [],
    "model": "seedance_2_0"
  },
  "use_unlim": false,
  "use_free_gens": false
}
```

### Response

```json
{
  "id": "<project-uuid>",
  "job_sets": [
    {
      "id": "<job-uuid>",
      "type": "seedance_2_0",
      "project_id": "<project-uuid>",
      "created_at": 1779300445.438815,
      "parent_id": null,
      "cluster_hash": "b9199a24494b51b6c51b58b08e9bfb4e",
      "cost": 6750,
      "params": { ...same as request... },
      "reference_elements": [
        {
          "id": "<character-uuid>",
          "name": "ori",
          "category": "character",
          "medias": [{ "id": "...", "url": "https://d2ol7oe51mr4n9.cloudfront.net/..." }]
        }
      ]
    }
  ]
}
```

## Character (face) reference

Prompts include a saved character via `<<<character-uuid>>>` inline.
The character has to be created first (face upload + extract). The uuid then
gets included literally in the prompt string.

For SocialBlast's Brand Kit, this means:

1. When a face photo is uploaded, we POST it to HiggsField, get a character uuid
2. Save the uuid alongside the face asset (in `asset.description` like
   `higgsfield_character_id:<uuid>`)
3. When generating videos for that face, prepend `<<<uuid>>> ` to the prompt

## Auth — DECODED (mostly)

Inspecting the Next.js JS bundles in the HAR reveals the exact wire-level
auth scheme used by the web app:

```js
// from assets.higgsfield.ai/main/_next/static/chunks/.../page-*.js
axios.create({
  baseURL: "https://fnf.higgsfield.ai",
  fetch: (e, t) => {
    let i = new Headers(t?.headers);
    let r = getClerkSessionToken();  // returns a short-lived JWT
    if (r) i.set("Authorization", "Bearer " + r);
    return fetch(e, { ...t, headers: i });
  },
});
```

So every request to `fnf.higgsfield.ai` carries
`Authorization: Bearer <jwt>`. The JWT is fetched from Clerk:

1. Initial login: `higgsfield.ai` → Clerk Sign-in modal → Google OAuth →
   Clerk sets a `__session` cookie on `.clerk.higgsfield.ai`.
2. **Token refresh** (every ~50 seconds, observed 15+ times in this HAR):
   `POST https://clerk.higgsfield.ai/v1/client/sessions/<sess_id>/tokens`
   → returns `{ "jwt": "<short-lived JWT>", ... }`.
3. That JWT is what goes in `Authorization: Bearer ...` on every
   `fnf.higgsfield.ai` call.

### Your Key ID + Key Secret pair

The pair is **not** what the web app uses. It is for the official HiggsField
CLI / MCP, which likely:

- Posts `{ "client_id": <key_id>, "client_secret": <key_secret>,
  "grant_type": "client_credentials" }` to some token endpoint
- Receives back a Bearer JWT in the same format the web app uses
- Calls `fnf.higgsfield.ai` with that JWT

The exchange endpoint is **not visible** in this HAR because the user did
not use the CLI during the capture. To pin it down:

1. Install the official HiggsField CLI (likely `npm i -g @higgsfield/cli`)
   or find the MCP source and grep for `/auth/`, `/token`, or
   `client_credentials`.
2. Run any CLI command with verbose/debug enabled — the URL and request
   body will show in stderr or `.cli/debug.log`.
3. Or check `higgsfield.ai/cli` and `higgsfield.ai/mcp` for documentation.
4. Or contact HiggsField support — the API is clearly real, they just
   haven't published official REST docs yet.

### Other interesting bits from the JS

- `https://aitys.higgsfield.ai` — another subdomain, purpose unclear
- `https://dd.higgsfield.ai/js` — DataDome bot protection JS
- `/audio` endpoint accepts `POST {"extension": "wav", "name": "..."}` and
  returns an upload URL (so ElevenLabs may be proxied here).
- `/folders/{id}/audio/token` — token to upload audio to a folder.

## Implementation hints for `ai_services/higgsfield.py`

1. Change `DEFAULT_HIGGSFIELD_BASE_URL` from
   `https://higgsfield.ai/api/v1` to `https://fnf.higgsfield.ai`
2. Generate endpoint: `POST {base}/jobs/v2/{model_id}` with body
   `{"params": {...}, "use_unlim": false, "use_free_gens": false}`
3. Status endpoint: `GET {base}/jobs/{job_uuid}/status`
4. Wallet endpoint: `GET {base}/workspaces/wallet`
5. Once auth is confirmed, send the right header on every request.

## Known anti-bot

HiggsField uses **DataDome** for bot protection. The web client sets
`x-datadome-clientid: <token>` on every request. Programmatic clients with
proper API keys should be exempt, but if direct calls get blocked with a
challenge response (HTTP 403 + DataDome HTML body), that's why.
