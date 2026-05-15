# Dashboard Implementation Plan (W7A1 Parts 1, 4, 5)

**Status:** source of truth for the Next.js + React + Tailwind
dashboard at `app/dashboard/`. This document describes the agreed
design; the code changes follow it.

## Why Next.js instead of Streamlit

The W7A1 rubric suggests Streamlit (`streamlit run app/dashboard.py`)
but does not mandate it. We are substituting Next.js + React + Tailwind
for three reasons:

1. **Real product feel.** A non-technical user (the rubric's framing —
   "a parent or school administrator deciding whether kids should have
   indoor recess") is more likely to trust a dashboard that looks like
   the consumer apps they already use than one with Streamlit's
   default `flex-direction: column; max-width: 740px; gray sidebar`
   aesthetic.
2. **Portfolio value.** The team gets practice with a stack that is
   commonly seen in real ML serving deployments (FastAPI + Next.js).
3. **Architecture honesty.** Splitting the dashboard into a thin
   browser client + a Node API layer makes the FastAPI/dashboard
   boundary explicit, which mirrors how production ML systems
   typically deploy.

The PR description will document this substitution and the
`app/dashboard.py` -> `app/dashboard/` path change for the rubric
grader.

## Architecture

```
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────┐
│ Browser (React) │  →   │ Next.js dev server :3000 │  →   │ FastAPI :8000   │
│                 │      │                          │      │ serve:app       │
│  Tailwind UI    │      │  /api/health  (proxy)    │  →   │ /health         │
│  Recharts       │      │  /api/predict (proxy)    │  →   │ /predict        │
│                 │      │  /api/features (Node)    │  ┐   │                 │
└─────────────────┘      └────────────┬─────────────┘  │   └─────────────────┘
                                      │                │
                                      ▼                │
                          include/data/raw/*.csv ──────┘
                          (Node fs + papaparse)
```

Three boxes, two processes, one filesystem-shared raw-data dir:

- **FastAPI (`serve:app`)** — exposes `/health` and `/predict` exactly
  as Contract 4 specifies. We don't grow its surface area.
- **Next.js dev server** — both the React UI and a Node-side API
  layer. The Node API has three routes (below). The browser never
  talks to FastAPI directly — going through Next.js avoids CORS work
  in `serve.py` and lets us add health enrichment later if we want.
- **Pipeline output** — the Node API layer reads
  `include/data/raw/pm25_*.csv` to compute features for user requests.
  Same filesystem layout the rest of the pipeline already uses.

### Next.js API routes

#### `GET /api/health`

Proxies `GET http://localhost:8000/health`. Surfaces the FastAPI
response shape directly — `{status, model_name, stage}` per Contract 4
— so the React side can render a binary online/offline health badge.

On FastAPI being unreachable, returns HTTP 503 with
`{"status": "fastapi_unreachable"}` so the dashboard can render a
"serving layer down" state.

> **Note on serve.py scope:** an earlier draft of this plan assumed
> `/health` would also include a `model_versions: dict[str, int]` field
> so the badge could show "red_butte v3, smithfield v2, ledges v4."
> That field was reviewed, judged scope-creep for the W7A1 deadline,
> and dropped from this PR. The HealthBadge renders against the W6
> three-field response shape only. The version-display improvement is
> a documented follow-up in the final PR description.

#### `POST /api/predict`

Proxies `POST http://localhost:8000/predict`. Request body is the
Contract 3 shape (location + nine engineered feature columns); response
is the Contract 4 shape (is_unsafe + unsafe_probability + threshold_used).

Errors from FastAPI (404, 503, 422) pass through.

#### `GET /api/features`

Node-side route — does NOT talk to FastAPI. Reads
`include/data/raw/pm25_*.csv` files, computes the engineered features
for the requested `(location, datetime)` using the "recent hourly
pattern" approach documented in Decision 8.

Query parameters:

- `location` — one of `red_butte`, `smithfield`, `ledges` (required).
- `from` — ISO 8601 UTC datetime for the first hour to predict (required).
- `hours` — integer count of consecutive hourly rows to return (default 11, range 1–24). For the default UX (8am–6pm), this is 11.

Response shape:

```json
{
  "location": "red_butte",
  "rows": [
    {
      "timestamp": "2026-05-15T14:00:00Z",
      "features": {
        "pm25_lag_1h": 11.6,
        "pm25_lag_3h": 4.2,
        "pm25_lag_24h": 7.7,
        "pm25_rolling_mean_3h": 5.7,
        "pm25_rolling_std_3h": 2.1,
        "hour_of_day": 14,
        "day_of_week": 4,
        "month_of_year": 5,
        "is_weekend": 0
      },
      "data_source": "recent_pattern",
      "fallback_used": false
    },
    ...
  ],
  "reference_window_days": 14,
  "any_fallback_used": false
}
```

`data_source` is one of:

- `"actual"` — the requested datetime falls inside the raw history,
  exact pm25 values were used to build features.
- `"recent_pattern"` — the requested datetime is in the future (or has
  no raw entry); features were derived from the hour-of-day average
  over the last `REFERENCE_WINDOW_DAYS` (= 14) of raw data for this
  location.
- `"insufficient_data"` — the recent_pattern computation produced too
  few samples (< 7 observations for the requested hour-of-day) to
  trust. The row's features are returned with `fallback_used: true`
  so the UI can flag low-confidence input.

### Feature-prep algorithm (`lib/featurePrep.ts`)

For a requested `(location, target_datetime)`:

1. Load every `include/data/raw/pm25_{YYYY-MM-DD}.csv` for the last
   `REFERENCE_WINDOW_DAYS` days strictly before `target_datetime.date`.
   Concatenate, filter to `location_id`, drop NaN pm25.
2. Build a per-hour-of-day lookup: `{0: mean_pm25_at_midnight, 1: ...,
   23: ...}` plus `{0: std, 1: ...}`.
3. For each of `pm25_lag_1h`, `pm25_lag_3h`, `pm25_lag_24h`:
   - Try to read the actual pm25 at `target_datetime - lag` from the
     raw data. If present, use it (`data_source = "actual"` if all
     three are actual).
   - Otherwise fall back to the hour-of-day mean for the lag hour
     (`data_source = "recent_pattern"`).
4. For `pm25_rolling_mean_3h` and `pm25_rolling_std_3h`:
   - Compute over the (t-3, t-2, t-1) hours; same actual-or-pattern
     fallback per hour. The rolling mean of three pattern values is
     the mean of the three hour-of-day means.
5. Temporal features (`hour_of_day`, `day_of_week`, `month_of_year`,
   `is_weekend`) come from `target_datetime` directly — no fallback
   needed.
6. If the per-hour lookup has fewer than 7 observations for the
   target hour, set `fallback_used: true`.

### Constants kept in sync

`app/dashboard/lib/constants.ts` mirrors `include/src/constants.py`:

```typescript
export const UNSAFE_THRESHOLD = 35.4 as const;
export const TARGET_LOCATIONS = {
  red_butte:  { id: 3318370, label: "Red Butte (Salt Lake County)" },
  smithfield: { id: 305,     label: "Smithfield (Cache Valley)" },
  ledges:     { id: 6158842, label: "Ledges (St. George area)" },
} as const;
export const REFERENCE_WINDOW_DAYS = 14;
export const FEATURE_COLS = [
  "pm25_lag_1h", "pm25_lag_3h", "pm25_lag_24h",
  "pm25_rolling_mean_3h", "pm25_rolling_std_3h",
  "hour_of_day", "day_of_week", "month_of_year", "is_weekend",
] as const;
export const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";
```

These five values are the SECOND copy of the constants — the first
copy lives in Python at `include/src/constants.py`. INTERFACE.md
Shared Constants gains a row recording that both copies exist and the
Python file is the source of truth.

## Files that change

### 1. `app/dashboard/` — new Next.js project

Directory layout:

```
app/dashboard/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── next.config.ts
├── README.md
├── .env.local.example
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── health/route.ts
│       ├── predict/route.ts
│       └── features/route.ts
├── components/
│   ├── HealthBadge.tsx
│   ├── LocationPicker.tsx
│   ├── DateTimePicker.tsx
│   ├── HourRangeSlider.tsx
│   ├── PredictionCard.tsx
│   ├── HourlyPredictionStrip.tsx        ← see "Prediction visualization" below
│   ├── TrendChart.tsx
│   ├── DataSourceLegend.tsx
│   └── ui/
│       ├── Button.tsx
│       ├── Card.tsx
│       └── Select.tsx
├── lib/
│   ├── constants.ts
│   ├── types.ts
│   ├── featurePrep.ts
│   ├── readRawCsv.ts
│   ├── api.ts
│   └── plainLanguage.ts
└── public/
    └── favicon.ico
```

Dependencies (`package.json`):

```json
{
  "name": "airalert-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.x",
    "react": "18.x",
    "react-dom": "18.x",
    "recharts": "^2.12",
    "papaparse": "^5.4",
    "date-fns": "^3.6",
    "clsx": "^2.1"
  },
  "devDependencies": {
    "typescript": "^5.4",
    "@types/node": "^20.12",
    "@types/react": "^18.3",
    "@types/papaparse": "^5.3",
    "tailwindcss": "^3.4",
    "postcss": "^8.4",
    "autoprefixer": "^10.4"
  }
}
```

#### `app/page.tsx` — main UI

Top-level layout (mobile-friendly stack at narrow widths, two-column
grid at wide widths):

```
┌──────────────────────────────────────────────────────────────────┐
│  AirAlert · Utah PM2.5 Predictor             [HealthBadge ●]      │
│  Should kids have outdoor recess tomorrow?                        │
├──────────────────────────────────┬───────────────────────────────┤
│  Location:  [Red Butte ▾]        │  Outlook                       │
│  Date:      [May 15, 2026 ▾]     │  ─────────────────────         │
│  Hours:     [8 AM   ━●━━ 6 PM]   │  Air quality is predicted to   │
│                                  │  be UNSAFE between 2 PM and    │
│  [ Get prediction ]              │  4 PM at Red Butte.            │
│                                  │                                │
│                                  │  We recommend INDOOR recess    │
│                                  │  during those hours.           │
│                                  │                                │
│                                  │  Confidence: HIGH              │
├──────────────────────────────────┴───────────────────────────────┤
│  Hourly breakdown                                                 │
│  Hour   Predicted     Probability   Confidence                    │
│   8 AM  Safe          0.12          Low                           │
│   9 AM  Safe          0.18          Low                           │
│  10 AM  Safe          0.22          Low                           │
│  ...                                                              │
│   2 PM  UNSAFE        0.78          High                          │
│   3 PM  UNSAFE        0.82          High                          │
│   4 PM  UNSAFE        0.74          High                          │
│   5 PM  Safe          0.45          Medium                        │
│   6 PM  Safe          0.31          Low                           │
├──────────────────────────────────────────────────────────────────┤
│  Recent PM2.5 at Red Butte                                        │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ ▁▃▂▄▃▅▄▆▅▇━━━━━━━ 35.4 (unsafe) ━━━━━━━━━━━━━━━━━━━━━━━━ │   │
│  │                                                            │   │
│  │ (Recharts line chart: last 7 days hourly pm25, threshold)  │   │
│  └────────────────────────────────────────────────────────────┘   │
│  Data source: actual measurements through May 13;                 │
│  May 14–15 estimated from recent hourly patterns.                 │
└──────────────────────────────────────────────────────────────────┘
```

#### Plain-language headline logic (`lib/plainLanguage.ts`)

The headline string is computed from the array of per-hour predictions:

```typescript
type Prediction = {
  timestamp: string;       // ISO 8601 UTC
  is_unsafe: 0 | 1;
  unsafe_probability: number;
};

function plainLanguageHeadline(
  location_label: string,
  predictions: Prediction[],
): { headline: string; recommendation: string; confidence: "high" | "medium" | "low" } {
  const unsafe_hours = predictions.filter(p => p.is_unsafe === 1);

  if (unsafe_hours.length === 0) {
    return {
      headline: `Air quality at ${location_label} is predicted to be SAFE across the requested hours.`,
      recommendation: "Outdoor activities should be fine.",
      confidence: confidenceBucketFromMaxProb(predictions),
    };
  }

  // Group consecutive unsafe hours into one or more ranges.
  const ranges = groupConsecutive(unsafe_hours);
  const range_str = ranges.map(r => `${fmtHour(r.start)} and ${fmtHour(r.end)}`).join(", and ");
  const max_prob = Math.max(...unsafe_hours.map(p => p.unsafe_probability));

  return {
    headline: `Air quality at ${location_label} is predicted to be UNSAFE between ${range_str}.`,
    recommendation: "We recommend INDOOR recess during those hours.",
    confidence: confidenceBucketFromProb(max_prob),
  };
}
```

Confidence buckets match Decision 7: `prob >= 0.70` → high, `>= 0.40`
→ medium, else low.

#### Prediction visualization — strip over table over line

The model produces one prediction per hour for the requested range
(default 8 AM–6 PM, 11 hours). Three visualization shapes were
considered:

| Shape | Verdict |
|---|---|
| Line chart of `unsafe_probability` vs. hour | **Rejected.** Lines imply continuity between hours, and per Decision 7 the raw probability is a relative ranking score (not a calibrated absolute), so visual height differences would mislead a non-technical user. |
| Text table (hour · verdict · probability · confidence) | **Reasonable but dense.** Forces the user to read every row to spot the unsafe window. |
| **Hourly status strip** (one colored cell per hour) | **Adopted.** Color = safe / borderline / unsafe verdict. Saturation = confidence bucket (high = saturated, medium/low = lighter). Glyph (✓ / ⚠ / ✗) reinforces color for accessibility. |

The strip encodes only what Decision 7 says we can honestly show — the
binary verdict plus the high/medium/low confidence bucket. Raw
`unsafe_probability` is available in a hover popover for users who
want it.

`components/HourlyPredictionStrip.tsx` renders the 11-cell grid.
Color rule:

- **Safe + high/medium confidence** → green cell, ✓ glyph (`c-green 50` bg, `c-green 600` border, `c-green 900` glyph).
- **Safe + low confidence** OR **unsafe + low confidence** → amber cell, ⚠ glyph (`c-amber 50` bg, `c-amber 600` border, `c-amber 800` glyph). This is the "we're not sure" bucket; intentionally collapses low-confidence safe and low-confidence unsafe into one borderline state because the rubric question ("indoor or outdoor?") doesn't benefit from finer gradation in the uncertain zone.
- **Unsafe + medium confidence** → red cell, ✗ glyph (`c-red 50` bg, `c-red 600` border, `c-red 800` glyph).
- **Unsafe + high confidence** → saturated red cell, ✗ glyph (`c-red 100` bg, `c-red 700` border, `c-red 900` glyph). Pulls the eye to the most actionable hours.
- **Any cell with `fallback_used: true`** → renders a small ⓘ icon in the top-right corner of the cell (does not change the verdict color).

Cell click → opens a small popover with the underlying numbers
(raw probability, data_source, fallback flag) for power users.

#### `components/TrendChart.tsx`

Recharts line chart of the last 7 days of raw pm25 for the selected
location. Uses the same Node API layer (`/api/features` with a special
`as_chart=1` query param, or a separate `/api/trend` route — TBD
during implementation). Renders a horizontal reference line at
`UNSAFE_THRESHOLD = 35.4` so users can see how close current readings
sit to the unsafe boundary. Data points above the line use a red
stroke segment; data points below use a green stroke segment.

#### `components/HealthBadge.tsx`

Polls `/api/health` on mount and every 30 seconds. Renders:

- Green dot + "Online — AirAlert red_butte / smithfield / ledges loaded" when `status: "ok"` from /health.
- Red dot + "Serving layer unreachable" when `/api/health` returns 503 or the upstream FastAPI is down.

Predict button is disabled while red.

### 2. `include/src/serve.py`

**No changes.** Gracelyn's existing W6 implementation is correct as
written for the rubric. The dashboard renders against the existing
`/health` response shape (`status`, `model_name`, `stage`) and POSTs to
the existing `/predict` exactly per Contract 4. The serve.py file is
owned by GJ per the INTERFACE.md ownership table and is not touched
in this PR.

### 3. `INTERFACE.md`

- **Decision 7** — append paragraph about `class_weight='balanced'`
  affecting probability calibration. (See Phase 2 task — the prose to
  paste lives in `docs/phase_2_interface_md_patch.md`.)
- **Decision 8** — full write-up of this architecture and the
  recent-pattern feature-prep approach. (See Phase 2 task — same
  staging doc.)
- **Shared Constants** — add a note that the dashboard mirrors
  certain constants in `app/dashboard/lib/constants.ts` and that
  `include/src/constants.py` remains the source of truth.
- **Contract 4** — no changes. `/health` response shape stays at the
  W6 three-field contract; `/predict` request/response unchanged.
- **Change Log** — entry for this phase, separate from the Phase 1
  entry.

## Files that do NOT change

- `include/src/ingest.py`, `include/src/transform.py`,
  `include/src/train.py` (beyond Phase 1's promotion change),
  `include/src/drift.py`, `include/src/constants.py` — orthogonal.
- `dags/airalert_dag.py` — orthogonal.
- `requirements.txt` — no new Python deps. Node deps live in
  `app/dashboard/package.json`.

## Test scenarios

| Scenario | Setup | Expected |
|---|---|---|
| **Cold start, all services up** | FastAPI on :8000, Next.js on :3000 | Page loads, HealthBadge green within ~1s, all three model versions shown. |
| **FastAPI down** | Only Next.js running | HealthBadge red, predict button disabled, friendly error: "The prediction service is offline. Try again in a minute." |
| **Predict in the past (data exists)** | User picks 2026-05-08 14:00 for Red Butte | `/api/features` returns rows with `data_source: "actual"`; predictions render normally. |
| **Predict in the future** | User picks tomorrow 14:00 for Red Butte | `/api/features` returns rows with `data_source: "recent_pattern"`; banner under the chart says "May 15 estimated from recent hourly patterns." |
| **Predict with sparse history** | User picks an hour-of-day with < 7 observations across the reference window | Affected rows have `fallback_used: true`; UI shows a small ⚠ icon next to those rows in the hourly table. |
| **All predictions safe** | Recent pattern at Red Butte well below 35.4 | Headline: "Air quality is predicted to be SAFE across the requested hours." Hourly table all green. |
| **Mixed safe/unsafe** | Some hours above threshold | Headline groups consecutive unsafe hours into ranges. |
| **MLflow promoted a new version mid-session** | After 5 minutes, v2 replaces v1 at Production | Next predict call triggers cache reload server-side; HealthBadge updates to show v2 within 30s (next health poll). |
| **Browser console clean** | Open devtools, exercise the UI | No CORS errors (everything through Next.js API routes). No unhandled promise rejections. |

## Rubric impact (W7A1)

| W7A1 Part 4 criterion | Impact |
|---|---|
| Streamlit application | ✗ Substituted with Next.js + React + Tailwind. PR description documents the choice. |
| Health check confirms API is reachable before predicting | ✓ HealthBadge polls /api/health; predict button gated on green. |
| Input controls reflect Decision 8 | ✓ LocationPicker + DateTimePicker + HourRangeSlider; feature values are computed by Node from recent patterns. |
| Plain-language display of prediction + confidence | ✓ plainLanguageHeadline + PredictionCard; "high/medium/low" confidence buckets per Decision 7. |
| Trend chart with unsafe threshold marked | ✓ TrendChart with Recharts horizontal reference line at 35.4. |
| Run with `streamlit run app/dashboard.py` | ✗ Run with `cd app/dashboard && npm run dev`. README documents the substitution. |

| W7A1 Part 5 criterion | Impact |
|---|---|
| Airflow pipeline 5 tasks green | ✓ already done in drift plan. |
| MLflow run logged | ✓ already done. |
| Production model accessible | ✓ enabled by Phase 1 (serve_production_promotion_plan.md). |
| POST to /predict via Swagger UI | ✓ FastAPI surface unchanged. |
| Streamlit dashboard makes prediction | ✓ via Next.js substitute. |

## Time budget

| Phase 3 task | Estimate |
|---|---|
| `npx create-next-app@latest`, configure Tailwind, set up directories | 30 min |
| `lib/readRawCsv.ts` + `lib/featurePrep.ts` + unit tests | 90 min |
| `app/api/*` route handlers | 45 min |
| Components (HealthBadge, LocationPicker, DateTimePicker, HourRangeSlider) | 60 min |
| Components (PredictionCard, HourlyPredictionsTable, plainLanguage logic) | 60 min |
| TrendChart with Recharts + threshold line | 45 min |
| `app/page.tsx` composition + styling pass | 60 min |
| Manual end-to-end smoke + README | 30 min |
| **Total** | **~7 hours** |

## Rollback

The Next.js project is self-contained under `app/dashboard/`. A
single `rm -rf app/dashboard/` plus revert of the INTERFACE.md
Change Log entry restores the project to pre-Phase-3 state. No other
modules depend on the dashboard.
