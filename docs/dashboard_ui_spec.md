# AirAlert Dashboard UI Specification (W7A1 Part 4)

**Status:** source of truth for the **user-facing UI surface** of the
AirAlert dashboard. Sister doc to
`docs/dashboard_implementation_plan.md` — that doc owns architecture,
API contracts, the Decision 8 feature-prep algorithm, and the
directory layout; this doc owns layout grids, component specs, state
machines, color tokens, error copy, and accessibility.

**Scope of this doc.** Visual + interaction surface only. If a question
is "where does the data come from?" → implementation plan. If a
question is "what does the screen look like at this moment?" → this
doc.

**Out of scope.** Architecture, API route handlers, feature-prep
algorithm, train.py promotion, drift detection, DAG wiring.

---

## Rubric mapping (W7A1 Part 4)

The W7A1 rubric for the dashboard specifies four required UX
behaviors. Every behavior maps to a specific component or state
documented below.

| Rubric language | Component / state | Section |
|---|---|---|
| "A health check that confirms the API is reachable before attempting a prediction" | `HealthBadge` polls `/api/health`; Predict button disabled while badge is red | §"HealthBadge" + §"Predict button" |
| "Input controls reflecting your Decision 8 choice" | `LocationPicker` + `DateTimePicker` + `HourRangeSlider` (user picks location and future date; feature values are computed server-side from recent patterns) | §"Controls panel" |
| "A clear, plain-language display of the prediction result and confidence" | `PredictionCard` — narrative headline + recommendation + confidence bucket | §"PredictionCard" |
| "A trend chart showing recent PM2.5 values with the unsafe threshold marked" | `TrendChart` — Recharts line + horizontal reference line at 35.4 μg/m³ | §"TrendChart" |
| "A user who knows nothing about PM2.5 thresholds or machine learning should understand what the prediction means and what they should do about it" | `PredictionCard` produces sentence-case English; `HourlyPredictionStrip` encodes verdict + confidence in color + glyph, never raw probability | §"PredictionCard" + §"HourlyPredictionStrip" |

The non-technical-user clause is the highest-priority constraint. Any
ambiguity in this spec resolves toward "would a school administrator
who has never heard of PM2.5 understand this?"

---

## Page anatomy

Single-page application, no routing, no auth. Top-down vertical
layout on mobile; two-column on wide screens.

```
┌───────────────────────────────────────────────────────────────────┐
│  AirAlert · Utah PM2.5 Predictor             [HealthBadge ●]      │
│  Should kids have outdoor recess tomorrow?                        │
│                                                                   │
│  ────────────────────────────────────────────────────────────────  │
│                                                                   │
│  CONTROLS  (left column on desktop, top stack on mobile)          │
│  ┌──────────────────────────────────────────┐                     │
│  │  Location:  [ Red Butte | Smithfield | Ledges ]               │
│  │  Date:      [ May 15, 2026 ▾ ]                                │
│  │  Hours:     [ 8 AM ──●━━●── 6 PM ]                            │
│  │  [ Get prediction ]                                            │
│  └──────────────────────────────────────────┘                     │
│                                                                   │
│  PREDICTION DISPLAY  (right column on desktop, below controls)    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Outlook                                                      │ │
│  │  Air quality at Red Butte is predicted to be UNSAFE          │ │
│  │  between 2 PM and 4 PM. We recommend indoor recess           │ │
│  │  during those hours.                                          │ │
│  │  Confidence: HIGH                                             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  HOURLY OUTLOOK  (always full-width)                              │
│  [ ✓ ][ ✓ ][ ✓ ][ ✓ ][ ✓ ][ ⚠ ][ ✗ ][ ✗ ][ ✗ ][ ⚠ ][ ✓ ]         │
│   8AM  9AM 10AM 11AM 12PM 1PM 2PM  3PM  4PM  5PM  6PM             │
│  Legend: ▮ Safe  ▮ Borderline  ▮ Unsafe       Darker = higher conf │
│                                                                   │
│  RECENT PM2.5 TREND  (always full-width)                          │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  (Recharts line chart, last 7 days, 35.4 dashed reference)   │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Data source: actual measurements through May 13; May 14–15      │
│  estimated from recent hourly patterns.                           │
└───────────────────────────────────────────────────────────────────┘
```

### Grid rules

| Breakpoint | Layout |
|---|---|
| Desktop (≥ 1024px) | Controls + Prediction Display side-by-side in a 1:2 grid. Strip and trend chart full-width below. |
| Tablet (640–1023px) | Single column. Controls on top, prediction display below, strip below, trend below. |
| Mobile (< 640px) | Same as tablet, plus the strip wraps from one 11-cell row into two rows of ~6 cells each. |

Max content width: `max-w-5xl` (1024px). Generous outer padding
(`px-6 py-8` minimum) so the dashboard never feels cramped.

---

## Components

Each subsection specifies: visual shape, props, internal state,
behavior, edge cases, accessibility. Components live under
`app/dashboard/components/`. One component per file; named exports.

### HealthBadge

**Purpose.** Render the current status of the FastAPI serving layer so
the user knows whether predictions are available.

**Visual.** Small pill in the page header, right-aligned next to the
title row.

**States.**

| State | Appearance | When |
|---|---|---|
| `loading` | Gray pill, spinner glyph + "Checking…" | Initial mount, before first `/api/health` call resolves |
| `online` | Green pill, `ti-circle-check` glyph + "Service online" | `/api/health` returned `{status: "ok", ...}` |
| `offline` | Red pill, `ti-alert-circle` glyph + "Service offline" | `/api/health` returned 5xx, threw `ApiError`, or `status !== "ok"` |

**Behavior.**
- Polls `/api/health` on mount.
- Re-polls every 30 seconds via `setInterval` cleared on unmount.
- Re-polls immediately after the user submits a prediction request
  (so the badge reflects the truth right when it matters).

**Props.** None. Component is self-contained and reads from
`getHealth()` in `lib/api.ts`.

**Accessibility.** `aria-live="polite"` so screen readers announce
state transitions. Icon is `aria-hidden`; the text is the
accessible name.

---

### Controls panel

A grouped card containing the three input controls plus the submit
button. All inputs share one `<form>` so pressing Enter from any
focused input triggers Predict.

#### LocationPicker

**Visual.** Three-button segmented control. Each button shows the
location's short label ("Red Butte", "Smithfield", "Ledges") with
the region as a secondary line ("Salt Lake County" / "Cache Valley"
/ "Snow Canyon").

**Selected state.** Solid background (`bg-slate-900` light /
`bg-slate-100` dark), white text. Unselected buttons: transparent
background, slate border.

**Props.**
- `value: LocationKey` — the currently selected location key.
- `onChange: (next: LocationKey) => void`.

**Keyboard.** Tab focuses the button group; arrow keys move between
buttons; Enter or Space activates. Native `<button>` elements inside
a `<div role="radiogroup">`.

**Default.** `red_butte` (mirrors the rubric's "elementary school in
Salt Lake County" stakeholder framing in Decision 6).

#### DateTimePicker

**Visual.** Single native `<input type="date">` styled with
Tailwind utilities to match the page's neutral aesthetic.

**Props.**
- `value: string` (YYYY-MM-DD).
- `onChange: (next: string) => void`.
- `minDate: string`, `maxDate: string` — bounding rails.

**Bounds.**
- `minDate` = today − 30 days. Past dates older than that have no raw
  data in the typical pipeline window.
- `maxDate` = today + 7 days. Future dates are allowed per Decision 8
  but capped at one week so users don't ask for predictions a month
  out where the recent-pattern fallback is heavily extrapolating.

**Default.** Tomorrow (`today + 1 day`).

#### HourRangeSlider

**Visual.** Dual-thumb range slider with the selected range
highlighted between the thumbs. Live numeric labels above the
thumbs ("8 AM" / "6 PM" updating as the user drags).

**Props.**
- `start: number` (0–23, inclusive).
- `end: number` (0–23, inclusive).
- `onChange: (next: { start: number; end: number }) => void`.

**Rules.**
- `end >= start` always. UI prevents thumb crossover.
- Range span = `end - start + 1` hours. Minimum span = 1, maximum =
  12 (so the user doesn't request 24 sequential predictions).

**Default.** `start = 8`, `end = 18` (8 AM through 6 PM, the
recess-window framing).

**Keyboard.** Each thumb is a focusable `<input type="range">`. Left/
right arrows step by 1; PageUp/PageDown step by 3; Home/End jump to
the bound.

#### Predict button

**Visual.** Primary button at the bottom of the controls panel.
Full-width on mobile, auto-width on desktop. Slate-900 background,
white text, 1px ring on focus.

**States.**

| State | Appearance | Behavior |
|---|---|---|
| `default` | "Get prediction" label | Click → submit |
| `loading` | Spinner + "Predicting…" label | Disabled, no click |
| `disabled` | Reduced opacity | When `HealthBadge` is offline, or no location selected |

**Keyboard.** Enter from any control inside the form triggers submit
unless the button is disabled.

---

### PredictionCard

**Purpose.** Convert the array of per-hour predictions into a
plain-English headline that a non-technical user can act on.

**Visual.** Rounded card with a gentle slate background, sitting in
the upper-right of the desktop layout (or just under the controls on
mobile). Three text rows:

1. Small caps label: "Outlook"
2. Headline sentence (large, ~17–18px, weight 500). The two key
   phrases — the verdict ("UNSAFE between 2 PM and 4 PM" or "SAFE
   across the requested hours") — are colored to match the verdict
   (red for unsafe, green for safe).
3. Recommendation sentence (normal weight).
4. Footer line: "Confidence: HIGH / MEDIUM / LOW" with the bucket
   value bolded.

**States.**

| State | What renders |
|---|---|
| `empty` | Placeholder microcopy: "Pick a location and date, then tap Get prediction." |
| `loading` | Skeleton bars matching the 4-row shape. |
| `result` | The headline + recommendation + confidence per `plainLanguageHeadline()`. |
| `error` | Friendly error message keyed by error type (see §"Error states"). |

**Props.**
- `state: "empty" | "loading" | "result" | "error"`.
- `verdict: PlainLanguageVerdict | null`.
- `errorMessage: string | null`.

**Accessibility.** `role="status"` and `aria-live="polite"` on the
result container so screen readers announce the headline when a new
prediction lands.

---

### HourlyPredictionStrip

**Purpose.** Show a per-hour at-a-glance view of the requested hour
range, color-coded by verdict and confidence.

**Visual.** Horizontal grid of cells, one cell per hour. Cell layout:

```
┌────┐
│ ✓  │  ← glyph, sized 18–20px
│    │
│8AM │  ← hour label, 11px, secondary
└────┘
```

Width: `repeat(N, minmax(0, 1fr))` where `N = end - start + 1`.
On screens narrower than 640px, the strip wraps to two rows of half
the cells each. Cell aspect ratio approximately square — width ≈
height. Spacing between cells: `gap-2` (8px).

**Cell-state mapping.** Every cell renders one of five states. The
state comes from `lib/plainLanguage.ts → cellState(prediction)`:

| State | When | Background | Border | Glyph | Glyph color |
|---|---|---|---|---|---|
| `safe-high` | `is_unsafe=0`, confidence `high` | `bg-safe-50` | `border-safe-500` | `ti-check` | `text-safe-700` |
| `safe-medium` | `is_unsafe=0`, confidence `medium` | `bg-safe-50` | `border-safe-500` | `ti-check` | `text-safe-700` |
| `borderline` | `confidence=low` (either direction) | `bg-caution-50` | `border-caution-500` | `ti-alert-triangle` | `text-caution-700` |
| `unsafe-medium` | `is_unsafe=1`, confidence `medium` | `bg-unsafe-50` | `border-unsafe-500` | `ti-x` | `text-unsafe-700` |
| `unsafe-high` | `is_unsafe=1`, confidence `high` | `bg-unsafe-100` (more saturated) | `border-unsafe-600` | `ti-x` | `text-unsafe-700` (deeper) |

`safe-high` and `safe-medium` deliberately render identically — the
strip's three visible color tiers (safe / borderline / unsafe) match
the legend below it. Higher safe confidence is a non-event for the
user. The intensity bump is reserved for `unsafe-high` because that
is the most actionable state.

**Fallback indicator.** Any cell whose underlying row has
`fallback_used: true` renders a small `ti-info-circle` glyph (12px)
in the cell's top-right corner. This communicates "the model was
working with partial data for this hour" without changing the
verdict color. Hover or focus on the cell reveals a tooltip:
"Estimated from recent hourly patterns."

**Hover / click behavior.** Hovering a cell (desktop) or tapping it
(mobile) opens a small popover anchored below the cell containing:
- Hour: "2 PM (UTC)"
- Verdict: "Unsafe" / "Safe" / "Borderline"
- Confidence: high / medium / low
- Raw unsafe_probability: numeric, 2 decimal places
- Data source: `actual` / `recent_pattern`
- Fallback used: yes / no

This is the only place the raw probability appears in the UI — see
the Decision 7 rationale in INTERFACE.md.

**Below the strip.** A small legend row:

```
▮ Safe   ▮ Borderline   ▮ Unsafe          Darker = higher confidence
```

**Props.**
- `predictions: HourlyPrediction[]`.
- `loading: boolean`.

**Loading state.** Each cell renders as a slate-200 skeleton block
of the same dimensions, no glyph, no label.

**Empty state.** Hidden — the parent doesn't render the strip until
predictions exist (matches the rubric framing of "make a prediction
first").

**Accessibility.** Each cell is a focusable button with an
`aria-label` like "8 AM, predicted safe, high confidence." The
keyboard tab order moves left-to-right through the cells. The popover
is keyboard-dismissable with Escape.

---

### TrendChart

**Purpose.** Show recent observed PM2.5 readings for the selected
location so the user has context for what's been happening at this
site lately.

**Visual.** Recharts `LineChart` filling the full width of its
parent card. Height ~200px on mobile, ~240px on desktop.

**Data.** Last 7 days of raw pm25, one point per hour. Fetched from
`/api/trend?location={loc}&days=7` once on mount and again when the
location changes.

**Encoding.**
- X axis: time. Ticks every 24 hours.
- Y axis: pm25 in μg/m³. Range = `[0, max(observed, 60)]` so the
  threshold line at 35.4 is always visible.
- Main line: solid 1.5px stroke, `c-blue 600`.
- Reference line at `UNSAFE_THRESHOLD` (35.4): horizontal, dashed,
  `c-red 600`. Label "35.4 μg/m³" at the right edge.
- Line segments above 35.4: stroke turns `c-red 600` for visual
  reinforcement that those points were unsafe.
- Tooltip on hover: "May 12, 2 PM · 42.1 μg/m³ · UNSAFE" / "SAFE".

**Empty state.** "No recent PM2.5 data for [location]. The pipeline
may not have produced any successful runs in the last 7 days."

**Loading state.** Skeleton placeholder (gray rectangle of the same
dimensions). No spinner — chart shimmer is more polished.

**Error state.** Inline error card: "Couldn't load the trend chart.
{errorMessage}"

**Props.**
- `location: LocationKey`.

**Internal state.** `useState` for points, loading, error. `useEffect`
re-fetches on location change.

**Accessibility.** Recharts adds `role="img"` and a default
`aria-label`. We override with a descriptive label:
"PM2.5 trend chart for Red Butte. Seven days of hourly readings.
Unsafe threshold at 35.4 micrograms per cubic meter."

---

### DataSourceLegend

**Purpose.** Communicate what kind of evidence the dashboard is
working with right now (actuals vs recent-pattern estimation).

**Visual.** Small footer text below the trend chart, secondary text
color. Sentence-case English. Updates dynamically based on the
prediction results.

**Logic.**
- If `predictions.every(p => p.data_source === "actual")` →
  "All hours used actual measurements from the pipeline."
- If `predictions.some(p => p.data_source === "recent_pattern")` →
  "Hours marked with ⓘ were estimated from the last 14 days of
   hourly patterns."
- If `predictions.some(p => p.data_source === "insufficient_data")` →
  Append: "One or more hours had less than 7 reference observations
   — those predictions are low-confidence."

**Props.**
- `predictions: HourlyPrediction[]`.

---

## State machine

The page lives in one of these top-level states. The transitions are
managed by `app/page.tsx` (the composition file).

```
   [INITIAL]              ← page load
       │
       │ /api/health resolves
       ▼
   [READY]                ← controls editable, predict enabled
       │
       │ user submits
       ▼
   [PREDICTING]           ← spinner; card + strip show skeleton
       │
       ├── success ──▶ [HAS_RESULT]   ← card + strip + trend render
       │                   │
       │                   │ user changes controls + submits
       │                   ▼
       │              [PREDICTING] (again)
       │
       └── failure ──▶ [ERROR]        ← card shows error message
                           │
                           │ user retries or changes controls
                           ▼
                       [PREDICTING] (again)
```

Side-channel: HealthBadge polling can transition the page from any
state into a sub-state where the Predict button is disabled (badge
red). This does not transition the page's main state; it only gates
the submit affordance.

---

## Loading, error, and empty states

### Loading

| Region | Loading appearance |
|---|---|
| HealthBadge | Gray pill, spinner glyph, "Checking…" |
| Predict button | Spinner + "Predicting…" label, disabled |
| PredictionCard | Skeleton bars matching the 4-row shape |
| HourlyPredictionStrip | Skeleton cells, no glyphs |
| TrendChart | Solid skeleton rectangle |

### Errors

| Failure | User-facing message |
|---|---|
| `/api/health` 5xx or unreachable | HealthBadge red. Predict button disabled. No error toast — the badge IS the error UI. |
| `/api/features` 5xx | PredictionCard error state: "Couldn't build features for this date. The pipeline may not have produced recent data for this location." |
| `/api/predict` 5xx | PredictionCard error state: "The prediction service couldn't process this request. Try a different location or date." |
| `/api/trend` 5xx | TrendChart error card only. The prediction can still render. |
| Network offline | Universal banner at the top: "You appear to be offline. Reconnect and try again." |
| Validation (e.g. date out of range) | Inline message under the bad control; submit disabled until fixed. |

All error copy is sentence-case, ≤ 2 sentences, no jargon. No raw
exception messages exposed to the user. The underlying `ApiError`
detail is logged to the browser console for debugging.

### Empty

The page first renders in an empty state before the user has
submitted a prediction:

- HealthBadge: live state (typically online).
- Controls: defaults shown.
- PredictionCard: empty-state placeholder ("Pick a location and date, then tap Get prediction.").
- HourlyPredictionStrip: hidden.
- TrendChart: loads automatically on mount with the default location.

---

## Color tokens

Mirror of `tailwind.config.ts`. Source of truth is the Tailwind
config; this table is for documentation.

| Token | Hex | Use |
|---|---|---|
| `safe-50` | `#f0fdf4` | Safe cell background |
| `safe-500` | `#22c55e` | Safe cell border, legend dot |
| `safe-700` | `#15803d` | Safe cell glyph, safe verdict text |
| `caution-50` | `#fffbeb` | Borderline cell background |
| `caution-500` | `#f59e0b` | Borderline cell border, legend dot |
| `caution-700` | `#b45309` | Borderline cell glyph |
| `unsafe-50` | `#fef2f2` | Unsafe-medium cell background |
| `unsafe-100` | `#fee2e2` | Unsafe-high cell background |
| `unsafe-500` | `#ef4444` | Unsafe cell border |
| `unsafe-600` | `#dc2626` | Unsafe-high cell border |
| `unsafe-700` | `#b91c1c` | Unsafe cell glyph, unsafe verdict text |
| `slate-*` | (default Tailwind) | All neutral chrome |

---

## Typography

| Element | Size | Weight | Color |
|---|---|---|---|
| Page title | 30px (`text-3xl`) | 500 | `text-slate-900` |
| Page subtitle | 18px (`text-lg`) | 400 | `text-slate-600` |
| Section label ("Outlook", "Hourly outlook") | 13px | 500 (uppercase, tracking-wider) | `text-slate-500` |
| Body / card heading | 17px (`text-base`) | 500 | `text-slate-900` |
| Body / paragraph | 15–16px | 400 | `text-slate-700` |
| Cell glyph | 18–20px | — | per state table |
| Cell hour label | 11px | 400 | per state table |
| Legend caption | 12px | 400 | `text-slate-500` |
| Trend chart axis | 11px | 400 | `text-slate-500` |

Font family: Tailwind default sans stack (system fonts). No custom
web fonts — keeps the dashboard fast and avoids font-load FOUT.

---

## Accessibility

- Every interactive element has a visible focus ring (`ring-2
  ring-slate-700 ring-offset-2`).
- No information is conveyed by color alone. The cells use color AND
  a glyph; the headline uses color AND the words "SAFE" / "UNSAFE";
  the badge uses color AND text.
- All `<img>`-equivalent SVG elements have descriptive `aria-label`s.
- All controls have associated `<label>` elements (or `aria-label`).
- Cell color contrast meets WCAG AA against the cell background for
  glyph and label (`#15803d on #f0fdf4` ≈ 6.7:1; `#b91c1c on
  #fee2e2` ≈ 6.9:1).
- Live regions: HealthBadge (`aria-live="polite"`), PredictionCard
  result region (`aria-live="polite"`).
- The page is fully keyboard-navigable in tab order: HealthBadge →
  LocationPicker → DateTimePicker → HourRangeSlider start thumb →
  HourRangeSlider end thumb → Predict button → (after submit) any
  HourlyPredictionStrip cell → TrendChart container.

---

## Responsive rules

| Breakpoint | Specific behavior |
|---|---|
| `sm` (≥ 640px) | Controls panel becomes side-padded card. Strip cells get hover popover (not tap). |
| `md` (≥ 768px) | Trend chart height increases to 240px. |
| `lg` (≥ 1024px) | Controls + PredictionCard go side-by-side in a 1:2 grid. |
| `xl` (≥ 1280px) | Container caps at `max-w-5xl` regardless. |

Strip wrap rule: on screens narrower than `sm` (mobile), the strip
wraps from one 11-cell row to two rows of `Math.ceil(N/2)` cells.
Cell aspect stays square; vertical space accommodates the wrap.

---

## Acceptance criteria (checklist before submission)

Functional:

- [ ] Cold-start: open the dashboard at `http://localhost:3000` with FastAPI on `:8000` → HealthBadge shows "Service online" within ~1s.
- [ ] Cold-start: open the dashboard with FastAPI stopped → HealthBadge shows "Service offline", Predict button is disabled.
- [ ] Default values: Red Butte selected; tomorrow's date; 8 AM – 6 PM range.
- [ ] Picking each of the three locations works and the trend chart updates.
- [ ] Date picker bounds: cannot pick more than 30 days in the past or 7 days in the future.
- [ ] Hour slider: thumbs cannot cross; min span 1 hour; max span 12 hours.
- [ ] Predict in the past with full raw history: every cell shows `data_source: actual`, no ⓘ flags, no fallback indicator.
- [ ] Predict in the future (tomorrow): every cell shows `data_source: recent_pattern`, ⓘ indicator visible on cells, `DataSourceLegend` mentions the estimation.
- [ ] When the model predicts all-safe across the range: PredictionCard headline says "SAFE across the requested hours" in green; recommendation says "Outdoor activities should be fine."
- [ ] When the model predicts mixed: headline groups consecutive unsafe hours into ranges ("between 2 PM and 4 PM"), names the location, recommends "indoor recess during those hours."
- [ ] Trend chart renders the last 7 days of pm25 with a dashed reference line at 35.4 and a label.
- [ ] Hovering a strip cell opens a popover with the raw probability + data source + fallback flag.

Visual:

- [ ] Strip uses exactly three verdict colors (green / amber / red).
- [ ] Unsafe-high cells are visibly more saturated than unsafe-medium cells.
- [ ] No raw probability number visible outside the cell popover.
- [ ] Page renders cleanly at 360px, 640px, 1024px widths.
- [ ] Dark mode (if applied via OS preference) doesn't break legibility.

Accessibility:

- [ ] Tab order matches the documented sequence.
- [ ] Focus rings visible on every focusable element.
- [ ] Screen reader announces HealthBadge transitions and prediction results.
- [ ] All glyph-only buttons have aria-labels.

Non-functional:

- [ ] `npm run typecheck` passes cleanly.
- [ ] `npm run lint` passes cleanly (or only warns; no errors).
- [ ] Browser console clean — no errors, no React warnings, no CORS errors.
- [ ] Time-to-first-prediction (cold cache, dev server) under ~3 seconds.

---

## Out-of-scope clarifications

This dashboard does NOT include, intentionally:

- User authentication or accounts.
- Saving previous predictions or notification subscriptions.
- A "compare locations" view.
- An admin / operator view (model version numbers, retraining
  history). Those are documented in the final PR description as
  candidate follow-ups.
- A dark-mode toggle (we inherit OS preference via CSS media query;
  no explicit toggle).
- Multi-day predictions across more than 24 hours.

These are deliberate scope cuts; revisit in a v2.
