# Social Engine — Design System (MASTER)

> Source of truth. Page-specific overrides live in `design-system/pages/<page>.md`.

## Identity

**Name:** Social Engine
**Aesthetic:** Editorial Terminal — a fusion of magazine asymmetry, command-center density, and brutalist edge.
**Anti-pattern target:** generic SaaS dashboards (soft slate gray, rounded cards, Inter everywhere). We do the opposite.

## Tokens

### Color (dark canvas only)

| Role          | Hex        | Use                                             |
| ------------- | ---------- | ----------------------------------------------- |
| canvas        | `#08090B`  | page background                                 |
| surface       | `#0F1014`  | module containers                               |
| surface-alt   | `#15171C`  | nested / hover surface                          |
| line          | `#1F2127`  | hairline borders                                |
| line-strong   | `#2C2F38`  | section dividers                                |
| ink           | `#F4F1EA`  | primary text (warm off-white, not `#FFFFFF`)    |
| ink-mute      | `#9097A1`  | secondary text                                  |
| ink-faint     | `#5A5F6B`  | tertiary, captions                              |
| signal        | `#E5FF00`  | signature accent (acid yellow) — sparingly      |
| signal-ink    | `#0A0B0D`  | text-on-signal                                  |
| heat          | `#FF5A1F`  | warm accent, alerts                             |
| ok            | `#5BE39A`  | success / published                             |
| danger        | `#FF3D6E`  | failure / destructive                           |
| pending       | `#FFB454`  | pending / approval-queue                        |

### Typography

- **Display / Heading:** `Instrument Serif` (italic for editorial weight) — Google Fonts.
- **UI / Body:** `Inter` 400/500/600 — for legibility only; never as a display font.
- **Data / Mono:** `JetBrains Mono` 400/500 — for numbers, timestamps, IDs, status codes.

Scale (px): 11 · 12 · 13 · 14 · 16 · 20 · 28 · 44 · 72 · 120
Body: 14/1.55. Mono UI: 12/1.4 with `font-feature-settings: "tnum" 1, "ss01" 1`.

### Space

4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 — strict 4pt rhythm.

### Border / radius / elevation

- Borders: 1px solid `--line`. **No drop shadows.** Depth comes from tonal value shifts.
- Radius: 0 (sharp) for chrome and tickers; 4px on inputs / pills; 12px on inset cards only.

### Motion

- Durations: 120ms (state), 240ms (transition), 480ms (panel).
- Easing: `cubic-bezier(.2,.8,.2,1)` standard; `cubic-bezier(.6,0,.4,1)` for emphasis.
- Live ticker: 30s loop, linear, pause on hover.
- Number counters: 800ms ease-out on mount.
- Respect `prefers-reduced-motion: reduce` — disable marquee, instant counters, no pulse.

## Signature Patterns

1. **Editorial masthead** — oversized italic serif headline with a wire-style date/time stamp; mixes serif display with all-caps mono labels.
2. **Wire ticker** — top-of-page horizontal marquee showing live activity (post status, errors, accounts) — pauses on hover.
3. **Index numerals** — every module is numbered `01 / 02 / 03` in mono, top-left, treated as part of the layout grammar.
4. **Asymmetric 12-col grid** — modules span varied column widths (4/5/3, 7/5, 8/4) instead of equal cards.
5. **Hairline language** — thin `1px` borders, never shadows; interior dividers express hierarchy.
6. **Status LEDs** — 6px dot + pulsing aura for live states; color-coded but always paired with a label.
7. **Inline sparklines** — tiny SVG line charts beside metric numbers; one accent stroke, no axes.
8. **Live caret** — a blinking mono `▌` after the active section title.

## Anti-patterns (do NOT do)

- Drop shadows of any kind.
- Gradient backgrounds on cards.
- Pure `#FFFFFF` text on pure `#000000`. We use warm off-whites on near-blacks.
- Emoji as icons. Use Lucide stroke icons only, 1.5px stroke.
- Rounded "pill cards" filling the page like Stripe / Notion / Claude SaaS templates.
- Equal-width 3-column grid as the default.
- Center-aligned hero sections.
- Generic chart libraries with default styling — every chart is hand-styled SVG.

## Required quality checks

- Contrast: ink on canvas ≥ 7:1; ink-mute on canvas ≥ 4.5:1.
- All interactive elements have a 2px focus ring in `--signal`.
- Touch targets ≥ 44×44 even though desktop-first.
- Reduced motion variant defined.
- Screen reader labels for icon-only buttons.
- Tabular numbers for all counts and times.
