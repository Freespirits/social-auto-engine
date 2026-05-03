# Page: Dashboard — overrides

Inherits all rules from `design-system/MASTER.md`. Below are page-specific deviations and additions.

## Layout

- 12-column grid, 32px gutters, 1440px max page width.
- Persistent **left rail** 64px wide: vertical brand glyph at top, vertical-rotated section label, footer status LED.
- **Top wire** 36px tall: marquee ticker with live activity items + clock on right edge.
- **Masthead** 200px tall: oversized italic serif "APPROVAL · QUEUE" headline (~120px), date and operator info on right.
- Below masthead, modules in this order:
  1. **KPI strip** (4 metrics, equal cells, sharp dividers between them — no card chrome).
  2. **Approval queue** spans 8 cols on left, **Activity feed** spans 4 cols on right.
  3. **Platform breakdown ring** spans 4 cols, **24h volume sparkbars** spans 8 cols.
  4. **System log** full width, monospace, dim.

## Modules

### 01 — KPI strip
4 cells: Total posts · Published · Pending · Failed. Numbers in 72px Instrument Serif italic; label in 11px mono uppercase tracked +0.18em; sparkline below number in `--signal`.

### 02 — Approval queue
List of pending posts. Each row:
- left: index `01.`, platform tag (FB / WA / IG), account name in mono.
- center: editorial italic serif preview of message, truncated 2 lines.
- right: Approve / Reject buttons. Approve = `--signal` filled. Reject = ghost danger.
Hovering a row inverts ink and surface — full negative.

### 03 — Activity feed
Vertical list, 8px between rows, mono 12px. Each row: timestamp, status-LED, account, action. `published` rows accent in `--ok`; `failed` rows accent in `--danger`.

### 04 — Platform ring
Custom SVG donut with thick strokes. No labels inside; legend below in mono with percentages. Hover slice highlights.

### 05 — Volume sparkbars
24 vertical bars (one per hour). Bar height = post count. Two-tone: published bars in `--ink`, failed bars in `--danger`. X-axis hours every 6h; no Y-axis.

### 06 — System log
Tail of last 12 events. Monospace, `--ink-faint` color. Single accent-yellow caret on most recent line.

## Page-only behaviors

- Top-right "REFRESH" button blinks signal yellow when stale > 60s.
- Pressing `j` / `k` moves selection through approval queue rows.
- Pressing `a` approves selected, `r` rejects (with confirm).
- Pressing `?` opens shortcut sheet (sheet, not modal — slides from bottom).
