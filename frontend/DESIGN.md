# LLM Council — Design System & UI Direction

> **Why this document exists:** In August 2026 we revamped the UI from a
> demo-grade interface to a production-grade one targeting **high-net-worth
> individuals** (the service is positioned as expensive, so the UI must reflect
> that). This file records the design direction, the decisions behind it, and
> how to iterate safely in the future. Read this before touching `theme.css`
> or any component CSS.

## Design direction

**"Private banking, not SaaS."** Reference points are private wealth
management and members' club aesthetics (KKR, Goldman Private Wealth,
Centurion) — *not* Linear/Stripe-style dev tools.

Three principles:

1. **Restraint over decoration** — hairline borders, generous whitespace,
   near-zero shadows, no gradients, no glow effects.
2. **Editorial typography** — a display serif (Fraunces) for headings and the
   wordmark, a quiet grotesque (Inter) for body text.
3. **Ceremony** — the 3-stage deliberation is the product's differentiator.
   The UI presents it as a formal proceeding (Stage I / II / III with a
   ceremonial progress indicator), not three spinner boxes. Waiting time is
   brand experience.

## Decisions made (and why)

| Decision | Choice | Rationale |
|---|---|---|
| Copy tone | Formal/quiet ("Consult the Council", "Council Consensus", roman numerals) | Playful copy ("Street Cred") undermines the premium segment |
| Default theme | **Dark** on first visit (system/light/dark toggle intact) | Deep charcoal + gold is the strongest expression of the concept |
| Accent color | **Champagne gold** | The luxury cue; a gold hairline reads richer than a gold button. Rejected: generic SaaS blue (old UI), deep emerald (fallback if gold ever feels too literal) |
| Fonts | Inter + Fraunces (variable) | Self-hosted in `public/fonts/`, `<link rel="preload">`-ed latin subsets, `font-display: optional` — no FOUC / text-shift on load, no CDN dependency (see `src/fonts.css`) |
| Favicon | Bespoke "council table" monogram (`public/council.svg`) | Six members seated around a gold ring |

## Token architecture (`src/theme.css`)

Kept the existing `light-dark()` + `color-mix(in oklch, ...)` architecture
(per `.clinerules/frontend.md`); only the values and names changed.

- **Surfaces**: `--bg-body / -app / -sidebar / -subtle / -panel / -hover`
  - Light = warm ivory paper (`#faf9f5` family). Dark = deep ink (`#14130f` family).
- **Accent**: `--accent` (text-safe, ≥ 4.5:1 on `--bg-app`), `--accent-text`
  (slightly stronger for links/labels), `--gold-line` (decorative — hairlines,
  underlines; NOT guaranteed text contrast), `--accent-soft`, `--accent-hover`,
  `--focus-ring`.
- **Typography**: `--font-display` / `--font-body` / `--font-mono`.
- **Elevation & motion**: `--shadow-panel` (one subtle level only),
  `--transition-fast` (150ms) / `--transition-med` (220ms).

**Rule of thumb when iterating:** if you reach for `--accent`, ask whether the
element is informational (yes: `--accent`/`--accent-text`) or decorative
(rare: `--gold-line`). Never introduce new hues; luxury comes from restraint.

## Component conventions introduced

- **Reading column**: chat content is centered at ~720px max-width. Long lines
  are the enemy of luxury — do not make the chat full-bleed.
- **Stage headers**: `I · Deliberation`, `II · Peer Review`, `III · Synthesis`
  — roman numeral in gold, small-caps kicker, hairline separator.
- **Ceremonial progress**: while a council run is in flight, a 3-step
  indicator (Deliberation → Peer Review → Synthesis) replaces per-stage
  spinners. Active step glows gold with a shimmer; completed steps get a ✓.
- **Tabs** (Radix, presentation only): underline tabs with a thin gold active
  underline — not boxed browser-tabs.
- **Stage 3** is the deliverable: most elevated treatment (larger body text,
  gold top rule, "Chairman" byline). It is deliberately NOT a colored
  "success box" — the old mint-green treatment read as "test passed".
- **User messages**: quiet bordered block, no bright bubble.
- **Monospace** is retained for model ids and durations — technical honesty
  reads as confidence at this price point.

## What was deliberately NOT changed

- No backend, `api.js`, routing, streaming, or state-management changes —
  this revamp is presentation-layer only.
- Stage transparency (raw model outputs + parsed rankings below raw text) is
  untouched — it is an architectural rule (`architecture.md`) and it also
  *supports* the premium positioning.
- Plain nested CSS per component remains the house style (no Tailwind, no
  CSS-in-JS). No runtime font packages — Inter/Fraunces are vendored as static
  files in `public/fonts/` and declared in `src/fonts.css`.

## Iterating in the future

1. Start from `theme.css` tokens — never hardcode a hex in a component.
2. Check both themes after any change (ThemeToggle cycles
   System → Light → Dark; first visit defaults to dark).
3. Verify breakpoints 320 / 768 / 1024 / 1440 (sidebar overlays below 900px).
4. Keep the gold sparse. If a screen feels "blingy", remove gold, don't add.
5. Contrast: text must stay ≥ 4.5:1 (WCAG AA) — the light-mode golds are
   already darkened for this; don't brighten `--accent`/`--accent-text`.
