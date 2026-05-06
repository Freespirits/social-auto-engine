# Company-grouped UI and multi-platform fan-out compose

**Status:** Design draft, 2026-05-06.
**Author:** Generated with Claude Code, reviewed by Ori Siracki.
**Predecessors:** [`2026-05-02-multi-channel-platform-master-plan.md`](./2026-05-02-multi-channel-platform-master-plan.md), [`2026-05-02-approval-queue-and-dashboard-mvp-design.md`](./2026-05-02-approval-queue-and-dashboard-mvp-design.md).

## Goal

Make social-auto-engine a true multi-platform tool, both in capability and in UX:

1. Compose a single creative once and publish it to several platforms in one action.
2. Organise the dashboard so the user thinks in **company groups** (Meta, LinkedIn, TikTok, YouTube, X) rather than a flat list of platforms.
3. Keep the approval-queue spine intact. Every fan-out post is still reviewed before it goes live.

This design is the bridge between the four-Meta-only adapters of today and the cross-platform scheduler the project is positioned as on awesome-mcp-servers and similar listings.

## Non-goals for this iteration

- No browser automation, ever. Every platform must be reached through its official API. Three reasons stacked:
  - Violates ToS of every supported platform; ban risk lands on the user's account.
  - Contradicts the "no silent automation" spine that is the project's safety story.
  - Specifically toxic for the maintainer who is currently freelancing for Meta.
- No analytics dashboard in this iteration. The fan-out result is success / failure per platform, nothing fancier.
- No team / multi-user permissions. Single-tenant remains the default.
- No drag-and-drop calendar editing. Existing scheduler stays the same.

## Prior art reviewed

- **[Postiz](https://github.com/gitroomhq/postiz-app)** (AGPL-3.0, NextJS / NestJS / Prisma / Temporal). Pattern study only — its AGPL licence prevents code reuse without re-licensing this project.
- **[Mixpost](https://github.com/inovector/MixPost)** (MIT, Laravel / Vue). Confirms the single-post-with-variants model ("Post Versions and Conditions"). MIT compatible if anything turns out to be worth copying line-for-line.
- **[facebook-mcp-server by Hagai Hen](https://github.com/HagaiHen/facebook-mcp-server)** — the project's own foundation, single platform per call.
- **[charlie947/social-media-skills](https://github.com/charlie947/social-media-skills)** — informs voice and content patterns, no fan-out concept.

The convergent shape across mature schedulers is: **one creative, N platform-specific outputs, per-platform overrides where useful, partial-failure tolerated.**

## Data model

### Current (single-platform per row)

```
post(id, platform, account_name, message, image_url, recipient, template_name,
     status, platform_post_id, error_message,
     created_at, decided_at, published_at, scheduled_for, permalink_url)
```

Each row is one post on one platform.

### New (group_id ties N platform rows together)

Add a single column:

```sql
ALTER TABLE post ADD COLUMN group_id TEXT;
CREATE INDEX IF NOT EXISTS idx_post_group ON post(group_id);
```

Semantics:

- A post created from the **broadcast composer** gets a freshly generated UUID4 `group_id`. Every platform target produces its own row, all sharing that `group_id`.
- A post created from the **single-platform composer** (e.g. WhatsApp 1:1 messaging, which is not a broadcast) leaves `group_id` NULL.
- A post created from the **MCP server or external API** also leaves `group_id` NULL by default. External callers can supply one if they want to bundle.

Each row keeps independent `status`, `error_message`, and `published_at`. A "group" is fully published when every row in the group has `status='published'`. A group with at least one `status='failed'` row is partially published — the UI must distinguish this.

### Why this shape

- **Minimum viable migration.** One column, no table split, additive change, safe to run on existing databases.
- **Independent per-platform status is correct semantics.** Twitter could fail at the rate limit while LinkedIn succeeds; the user must see the partial outcome accurately.
- **Existing single-platform code paths keep working unchanged.** `_publish_post` already dispatches by `post.platform`; nothing in the publish path needs to change.
- **Approve-all-in-group becomes a thin SQL filter** rather than a new code path.

## API surface

### Existing endpoints (unchanged)

- `GET /` — inbox
- `GET /calendar`
- `GET /published`
- `GET /settings`
- `POST /approve/{post_id}`
- `POST /reject/{post_id}`
- `POST /schedule/{post_id}`
- `POST /unschedule/{post_id}`

### Modified

- `POST /compose` — accepts a `platforms` form list (one or more) plus existing fields. Creates N rows under one `group_id` and returns the refreshed view.
  - Backwards compatibility: a single `platform` field still works (degrades to a one-row group), so any external caller using the current shape is unaffected.

### New

- `POST /approve-group/{group_id}` — approve and publish every pending row sharing that group_id.
- `POST /reject-group/{group_id}` — reject every pending row in the group.

## Composer UX

The composer has two modes, selected by tab at the top:

1. **Broadcast** — fan-out across selected social platforms. Default mode.
2. **Direct message** — WhatsApp 1:1 messaging. Same form as today, just one platform.

Reasoning for the split: WhatsApp Business is fundamentally 1:1, requires a recipient phone number, and uses templated messages. Forcing it into a multi-checkbox broadcast UI confuses both shapes. A tab keeps the broadcast experience clean and acknowledges WA's different model honestly.

### Broadcast layout

```
┌────────────────────────────────────────────────────────────────┐
│ New broadcast post                                              │
├────────────────────────────────────────────────────────────────┤
│ Publish to:                                                     │
│  ┌─ Meta ─────────────────────────────────────────────────────┐ │
│  │ [✓] Facebook    [✓] Instagram    [✓] Threads               │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌─ LinkedIn ─────────────────────────────────────────────────┐ │
│  │ [✓] LinkedIn (member)                                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌─ TikTok ───────────────────────────────────────────────────┐ │
│  │ [ ] TikTok (inbox upload)         (connect first)          │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ...                                                             │
├────────────────────────────────────────────────────────────────┤
│ Message                                                         │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │                                                            │ │
│ └────────────────────────────────────────────────────────────┘ │
│ Image URL (optional, required for Instagram)                    │
├────────────────────────────────────────────────────────────────┤
│ Per-platform overrides ▸ (collapsed by default)                 │
│   - Twitter / X version (280 char limit warning)                │
│   - LinkedIn version (3000 char limit)                          │
│   - Threads version (500 char limit)                            │
├────────────────────────────────────────────────────────────────┤
│ Will create 4 pending posts        [Cancel]  [Add to queue]     │
└────────────────────────────────────────────────────────────────┘
```

Per-platform character limits (informational, not enforced server-side in this iteration):

| Platform   | Limit  |
|------------|--------|
| Facebook   | 63,206 |
| Instagram  | 2,200  |
| Threads    | 500    |
| LinkedIn   | 3,000  |
| Twitter/X  | 280    |
| TikTok cap | 2,200  |
| YouTube    | 5,000  |

The composer shows a warning when the master message exceeds a selected platform's limit and offers a one-click "use override" to truncate or rewrite for that platform. The user makes the final call.

### Disabled state for unconnected platforms

Each checkbox is disabled when the platform is not connected, with hover text "Not connected — go to Settings". The Settings page already exists and surfaces all platforms regardless of connection state, so the user has a clear path to fix.

## Sidebar UX

Replace the flat `Accounts` list with company-grouped collapsible sections:

```
┌──────────────────────┐
│ Workspace            │
│  • Inbox    [3]      │
│  • Calendar [1]      │
│  • Published         │
├──────────────────────┤
│ Meta            ▾    │
│  ▪ Hack-Tech (FB)    │
│  ▪ @hack_tech (IG)   │
│  ▪ @threads_handle   │
│  ▪ +972… (WA)        │
├──────────────────────┤
│ LinkedIn        ▾    │
│  ▪ Ori Siracki       │
├──────────────────────┤
│ TikTok          ▾    │
│  ○ Not connected     │
├──────────────────────┤
│ YouTube         ▾    │
│  ○ Not connected     │
├──────────────────────┤
│ X               ▾    │
│  ○ Not connected     │
├──────────────────────┤
│ Settings             │
│ Sign out             │
└──────────────────────┘
```

- Each company section is collapsible (purely cosmetic, state stored in `localStorage`).
- The connection dot stays the same primitive.
- Order is fixed: Meta first (it has the most adapters today), then LinkedIn, TikTok, YouTube, X. Order can become user-configurable later.

## Approval queue UX

For grouped posts, the approval queue collapses N rows into a single card:

```
┌────────────────────────────────────────────────────────────────┐
│ ● Pending broadcast — 4 platforms                               │
│                                                                  │
│ "Big news: we just shipped multi-platform fan-out…"             │
│                                                                  │
│  [f]  Facebook        ✓ ready                                   │
│  [IG] Instagram       ✓ ready                                   │
│  [@]  Threads         ✓ ready                                   │
│  [in] LinkedIn        ✓ ready                                   │
│                                                                  │
│  Created 3m ago                                                 │
│                                                                  │
│  [Publish all]   [Reject all]   [Edit per platform ▸]           │
└────────────────────────────────────────────────────────────────┘
```

After "Publish all" is pressed, the card stays visible and updates each row's status as the dispatches complete:

```
│  [f]  Facebook        ✓ Live (view ↗)
│  [IG] Instagram       ✓ Live (view ↗)
│  [@]  Threads         ✗ Failed: 'OAuthException: token expired'
│  [in] LinkedIn        ⏳ Publishing...
```

Single-platform posts (group_id NULL) render as today.

## Adapter dispatch and partial failure

`_publish_post(post)` is unchanged at the row level. The new `/approve-group/{group_id}` endpoint:

```python
def approve_group(group_id):
    rows = db.list_group(group_id, status="pending")
    results = []
    for post in rows:
        _publish_post(post)
        refreshed = db.get_post(post["id"])
        results.append((post["platform"], refreshed["status"]))
    return _refresh_all(request, toast=_toast_for_group_result(results))
```

Sequential dispatch is fine for v1. Each adapter call is bounded by a 30 second timeout (already enforced in `LinkedInAPI._request`, similar elsewhere). Worst case is `N × 30s`, which is acceptable for the small number of platforms a single user fans out to.

A future iteration can move dispatch to a background task queue (APScheduler is already present, would just need a transient job) if the response time becomes a UX problem.

### Toast for group result

| All published | "Published to Facebook, Instagram, Threads, LinkedIn" |
| Some failed   | "Published 3 of 4: failed on Threads (token expired)" |
| All failed    | "All 4 publishes failed. See activity log."           |

## Backwards compatibility

- **Existing single-platform posts** keep working with `group_id` NULL. They render as today.
- **External MCP callers** of `manager.post_to_facebook(...)` etc. are completely untouched. The fan-out feature is dashboard-only in this iteration.
- **Existing `/compose` callers** sending a single `platform` field still work. Server treats it as a one-row group.
- **DB migration** is purely additive. Existing `dashboard.db` files migrate cleanly via the same lightweight pattern already used in `db.init_db`.

## Test plan

Manual end-to-end tests on a fresh `~/.social-auto-engine/dashboard.db`:

1. **Single-platform compose still works.** Compose a Facebook-only post via the legacy single-platform code path, verify it appears in pending, approve, verify it publishes.
2. **Broadcast compose creates N rows.** Compose a broadcast to FB + IG + Threads + LinkedIn, verify four rows appear in pending with the same group_id, no platform_post_id yet.
3. **Approve-all-in-group publishes all four.** Click "Publish all", verify all four rows transition to published or failed, group card updates per-row.
4. **Partial failure surfaces correctly.** Manually expire a token in `.env`, repeat (3), verify the failing row shows the error and the group toast says "Published 3 of 4".
5. **Reject-all-in-group rejects all four.** Verify all four rows transition to rejected.
6. **Sidebar grouping renders.** Verify connected accounts appear under their company section, unconnected platforms show as "Not connected" placeholders.
7. **WhatsApp tab still works.** WA flow lives in the "Direct message" tab and is unaffected by the broadcast changes.
8. **Calendar view.** Confirm grouped posts render as one item or N items (whichever is more useful — pick by feel and document).

Automated tests are out of scope for this iteration but the data shape (`group_id`) makes them easy to add later.

## Migration / rollback

- Forward migration is a single `ALTER TABLE` plus an index, run inside the existing `init_db` lightweight migrations.
- Rollback: drop the column. SQLite does not support `DROP COLUMN` natively in older versions, so for safety the rollback path is "leave the column in place, ignore it" — the column has no NOT NULL constraint and no behavioural impact when unused.

## Open questions for review

1. **WhatsApp in broadcast?** Current proposal puts WA on its own tab because it is 1:1 not broadcast. Alternative: include WA in broadcast with a per-row recipient picker, but this gets messy fast. **Recommendation: keep separate, revisit when there is real demand.**
2. **TikTok tier — inbox upload vs direct post?** Both, controlled by a per-account setting. Default to inbox upload because it is approvable without TikTok review; user opts in to direct post once their app is approved.
3. **YouTube in this iteration?** The design covers it conceptually, the adapter is not implemented. **Recommendation: design includes the slot, implementation deferred to a follow-up PR. Don't ship a half-baked YouTube adapter.**
4. **Per-platform image variants?** Today the same `image_url` is used for all platforms. Per-platform image overrides are a natural follow-up but not in this iteration. Use the master image, the user can edit per-platform later.

## Out of scope, listed explicitly so they don't sneak in

- Multi-image / carousel post composition (already exists as a skill, not in this UX work).
- Rich-text editor with formatting per platform.
- Post analytics dashboard.
- Team collaboration / approval workflows beyond a single user.
- Cross-platform comment moderation.
- Native mobile app.
