# Platform tiers — what each social platform's API actually grants

> Status: living reference. Last verified 2026-05-06. Tier policies change.
> Always cross-check developer.x.com / developers.tiktok.com / etc before
> committing capacity to a paid tier.

This is a single source of truth for the dashboard's UI gating, the
adapter capability checks, and the docs that tell users what to expect.
When a platform changes its rules, update this file first, then the
adapter code that reads from it.

## Why we care

Platform tiers shape three UX decisions inside social-auto-engine:

1. **Which features the dashboard offers a connected account.** No "show analytics" button when the user is on a tier without read access.
2. **How much volume the scheduler will queue.** If a tier permits 50 posts a month, the queue must refuse the 51st with a clear message.
3. **What the connection card shows.** A small badge next to the account name (Free / Basic / Pro / Member / MDP) so the user knows their cap at a glance.

The adapters *do not* try to upgrade tiers automatically. The rule is the same as the rest of the project: nothing silent. Tier upgrades happen in the platform's developer portal, with the user's eyes open and their money explicit.

## X / Twitter

| Tier | Cost | Writes/mo | Reads | OAuth-as-user | Suitable for |
|---|---|---|---|---|---|
| Free | $0 | ~1,500 (changes often) | essentially none | yes | Tinkering only. Don't ship behind it. |
| Basic | ~$200/mo (was $100, raised late 2024) | ~50,000 | limited | yes | Single creator or tiny agency posting their own accounts. |
| Pro | $5,000/mo | ~1,000,000 | full | yes | A real third-party SaaS scheduler with multiple paying users. |
| Enterprise | custom (six figures+) | bespoke | bespoke | yes | Out of scope for this project. |

**Rule we apply:** social-auto-engine does not ship X support out of the box. Users supply their own X developer credentials in `.env`. Each user pays their own X bill.

**Common confusion:** **X Premium / Premium+** ($8/$16 a month) is a *consumer* subscription that gets the user a blue check, longer posts, and Grok in the browser. It does *not* unlock the X developer API. The two systems are billed separately and managed in completely different portals.

**Grok API** (api.x.ai) is yet another product, an LLM API similar to OpenAI's. It does not let you post on behalf of a user. It is a candidate AI-compose backend, not an X-publishing backend.

## TikTok

| Tier | Cost | Capability | What it requires | Suitable for |
|---|---|---|---|---|
| Sandbox | $0 | Test the API against sandbox-listed test users | Dev app registration | Building and testing locally. |
| Inbox upload | $0 | `video.upload` scope, video lands in user's drafts. User taps Publish in TikTok app to finalise. | Sandbox graduation, Terms + Privacy URLs, app description | Single creator or scheduling tool that is happy with a manual final step. **This is what social-auto-engine ships today.** |
| Direct post | $0 | `video.publish` scope, video publishes immediately | Full TikTok app review (security questionnaire, demo videos, business verification) | A SaaS that has earned the right by going through review. |

**Rule we apply:** social-auto-engine implements only the inbox-upload tier. The "user finalises in the TikTok app" step is presented as a feature in the UI ("you stay in control of what TikTok sees you doing"), not a limitation. When a user has direct-post approved, we add it as an opt-in toggle on the connection card.

**Rate limits to know:**

- Inbox-upload init: 6 requests per minute per user access token
- Maximum 5 pending drafts within any 24-hour rolling window
- For PULL_FROM_URL: domain must be pre-verified in the TikTok dev portal

## LinkedIn

| Tier | Cost | Capability | What it requires | Suitable for |
|---|---|---|---|---|
| Member (default) | $0 | `w_member_social` scope, post as the authenticated user | Standard developer app, no manual review | Single creator or small tool that posts the user's own content. **This is what social-auto-engine ships today.** |
| Marketing Developer Platform | $0 fee, but gated review | Post as a Company Page on behalf of an organisation, plus analytics | LinkedIn manual review, takes weeks-to-months, frequently rejected for tools without existing paying users | Agency tools managing multiple LinkedIn pages. |

**Rule we apply:** member-tier first. Mark MDP as a Phase 2 unlock. Do not block the launch on it.

**Rate limits:** 100 posts per day per member.

## YouTube

| Tier | Cost | Capability | What it requires | Suitable for |
|---|---|---|---|---|
| Default project | $0 | 10,000 quota units / day, ~100 video uploads / day per project | Google Cloud project, OAuth setup | Personal use, small creator. |
| Audited / increased quota | $0 fee, but gated request | Higher daily quota for Shorts and analytics | Quota-increase request to Google with usage justification | Anyone hitting the cap. |

**Rule we apply:** default project quota covers any reasonable single-user case. The quota-increase request is a Phase 2 task once we have signal that someone is hitting the cap.

**Quota costs:**

- `videos.insert` (upload): 100 units. So 100 uploads / day on the default 10,000-unit allowance.
- `channels.list`: 1 unit.
- `videos.delete`: 50 units.

## Meta (Facebook, Instagram, WhatsApp, Threads)

| Tier | Cost | Capability | What it requires | Suitable for |
|---|---|---|---|---|
| Development mode | $0 | Test with users explicitly added to the app | App registration | Building locally. |
| Live mode (basic permissions) | $0 | `pages_read_engagement`, `pages_manage_posts`, `instagram_content_publish`, `whatsapp_business_messaging`, `threads_basic`, `threads_content_publish` | App Review for each permission, manual approval | Production use against any user. |
| Live mode (advanced permissions) | $0 | `pages_messaging`, more granular insights, Marketing API | Heavier App Review | Larger production tools. |

**Rule we apply:** social-auto-engine targets the basic-permissions set. The MCP server's full 37-tool suite uses exactly the standard Graph permissions, no advanced ones. App Review is the bottleneck, not the cost.

## How adapters should consume this matrix

Future shape (when the X adapter or the LinkedIn MDP path is built):

```python
# capabilities/x.py
TIERS = {
    "free":  {"post_text": True, "post_media": False, "monthly_writes": 1500,    "read": False},
    "basic": {"post_text": True, "post_media": True,  "monthly_writes": 50000,   "read": True},
    "pro":   {"post_text": True, "post_media": True,  "monthly_writes": 1000000, "read": True},
}
```

Each adapter reads its own tier from `.env` (`X_TIER=basic`, `LINKEDIN_TIER=member`, `TIKTOK_TIER=inbox`, etc), defaults to the most-restricted tier. Each public method does an early `if not TIERS[self.tier]["post_media"]: return {"success": False, "error": "..."}`.

The dashboard's compose UI reads the same matrix to disable / enable per-platform features and to surface upgrade prompts.

## When this file becomes wrong

- A platform changes its tier names, prices, or limits. Update the table above first, the adapter code second, the README third. Always in that order.
- Add the date of the change in the corresponding table row, e.g. *"Basic raised from \$100 to \$200/mo (effective ~late 2024)"*.
- If a platform reorganises its developer programme (X has done this twice in two years), keep the old table for historical reference under a "## Old tiers" heading rather than rewriting from scratch.
