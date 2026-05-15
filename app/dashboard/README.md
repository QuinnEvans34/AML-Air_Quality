# AirAlert Dashboard

Next.js + React + Tailwind dashboard for the AirAlert PM2.5 predictor.
The browser side renders a non-technical UI; the Node-side API routes
proxy to FastAPI (`/api/health`, `/api/predict`) and read raw pm25 CSVs
from the pipeline output (`/api/features`).

See `docs/dashboard_implementation_plan.md` (at the repo root) for the
full design.

## Prerequisites

- Node 20+
- npm 10+
- The FastAPI serving layer (`uvicorn serve:app --port 8000`) running
  separately from the repo root
- At least one full Airflow DAG run so `include/data/raw/pm25_*.csv`
  files exist for the dashboard's feature prep

## Run locally

From the repo root:

    uvicorn serve:app --reload --port 8000

In another terminal:

    cd app/dashboard
    npm install
    npm run dev

Open <http://localhost:3000>.

## Environment

Copy `.env.local.example` to `.env.local` if you need to override
defaults. The defaults assume:

- FastAPI is at `http://localhost:8000`
- Raw pm25 CSVs are at `../../include/data/raw`

`.env.local` is git-ignored.

## Where things live

```
app/dashboard/
├── app/
│   ├── layout.tsx                  Root layout, fonts, body styles
│   ├── page.tsx                    Main UI composition
│   ├── globals.css                 Tailwind directives + base styles
│   └── api/
│       ├── health/route.ts         GET — proxies FastAPI /health
│       ├── predict/route.ts        POST — proxies FastAPI /predict
│       └── features/route.ts       GET — Node-side feature prep from raw CSVs
├── components/                     React components (HealthBadge, charts, etc.)
└── lib/
    ├── constants.ts                Mirror of include/src/constants.py
    ├── types.ts                    Contract 3/4 + dashboard types
    ├── featurePrep.ts              Decision 8 recent-pattern algorithm
    ├── readRawCsv.ts               Node-side raw pm25 CSV reader
    ├── api.ts                      Typed fetch helpers
    └── plainLanguage.ts            "Indoor recess" / "Outdoor activities" headline
```

## Source of truth

`include/src/constants.py` is the Python source of truth for shared
constants. The mirror in `lib/constants.ts` must be updated whenever
the Python file changes (Decision-level changes must also update
INTERFACE.md "Shared Constants").

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Start the dev server on port 3000 with hot reload. |
| `npm run build` | Production build. |
| `npm run start` | Run the production build (`npm run build` first). |
| `npm run lint` | ESLint via `next lint`. |
| `npm run typecheck` | `tsc --noEmit` — verify TypeScript without emitting. |
