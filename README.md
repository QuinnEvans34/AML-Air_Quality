# AirAlert

**Daily recess and athletics guidance for Utah K-5 administrators.**

AirAlert is an end-to-end machine learning system that predicts whether the air at three Utah elementary-school locations will be safe for outdoor recess, hour by hour, for the day ahead. It ingests PM2.5 readings from the [OpenAQ v3 API](https://api.openaq.org/v3), engineers nine lag and temporal features, monitors distribution drift, retrains per-location logistic-regression models on a daily Airflow schedule, serves predictions through a FastAPI endpoint, and presents results in a Next.js dashboard that speaks directly to K-5 principals.

**Team:** Quinton Evans (QE) · Gracelyn Jarrett (GJ)
**Course:** Applied Machine Learning · Project One · W7A1

---

## What the system does

A school principal opens the dashboard at 8 AM Monday morning and sees:

- A one-glance verdict pill at the top: **GO**, **HOLD**, **MONITOR**, or **INDOORS**.
- A plain-English headline naming their school: *"Air quality at Bonneville Elementary is predicted to be UNSAFE between 2 PM and 4 PM."*
- A school-period-aware recommendation: *"Hold recess indoors during those hours."* — or, for after-school hours, *"After-school staff and coaches should monitor outdoor activities."*
- A color-coded hourly strip from 8 AM to 6 PM Mountain Time, with each cell tagged measured (from real sensor data) or estimated (from recent hourly patterns).
- A trend chart of the last 7 days of measured PM2.5, with the EPA unsafe threshold (35.4 μg/m³) marked.

Behind the scenes, a daily Airflow DAG runs at 06:00 UTC, ingests yesterday's OpenAQ data, validates Contract 1, engineers Contract 2 features over a 60-day rolling window, computes drift verdicts per location, and retrains any per-location model whose F1 has fallen below 0.70 or whose drift sigma exceeds 2.0. Newly-trained models are promoted to MLflow's Production stage automatically.

---

## Architecture

```
                     ┌──────────────────── Airflow DAG (06:00 UTC daily) ────────────────────┐
                     │                                                                        │
   OpenAQ v3  ──►   ingest   ─►   validate   ─►   engineer   ─►   drift_check   ─►   retrain │
                     │              │                │                  │                │    │
                     │     pm25_{ds}.csv   features_{ds}.csv   drift_{ds}.json   MLflow Registry │
                     │                                                            AirAlert_<loc> │
                     └──────────────────────────────────────────────────────────── @ Production ┘
                                                                                       │
                                       ┌───────────────────────────────────────────────┘
                                       ▼
                              ┌────────────────────────┐
                              │  FastAPI (uvicorn)     │
                              │  GET  /health          │
                              │  POST /predict         │
                              └────────────┬───────────┘
                                           │
                                           ▼
                              ┌────────────────────────────────────────┐
                              │  Next.js dashboard (port 3000)         │
                              │   ◄── React UI (Mountain Time)          │
                              │   ◄── Node /api/* routes (proxy + CSV)  │
                              └────────────────────────────────────────┘
```

The browser never talks to FastAPI directly — every external call goes through Next.js API routes, which lets `serve.py` skip CORS middleware entirely.

---

## Module ownership

| Module | Owner | Reviewer |
|---|---|---|
| `include/src/ingest.py` | QE | GJ |
| `include/src/transform.py` | GJ | QE |
| `include/src/train.py` | QE | GJ |
| `include/src/drift.py` | QE | GJ |
| `include/src/serve.py` | GJ | QE |
| `dags/airalert_dag.py` | Both | Both |
| `app/dashboard/` | Both | Both |

The serving layer and the transform layer are Gracelyn's; the ingest, train, and drift layers are Quinn's; the DAG and the dashboard are jointly owned.

---

## Tech stack

- **Python 3.11** · pandas, numpy, scikit-learn, mlflow, fastapi, uvicorn, pydantic
- **Apache Airflow** via the Astro CLI in Docker
- **MLflow** tracking server with sqlite backend + filesystem artifact store (serve-artifacts mode)
- **Next.js 14** · React 18 · TypeScript · Tailwind CSS · Recharts · date-fns-tz · lucide-react
- **OpenAQ v3** public API for PM2.5 ingestion

---

## Quick start (one command)

After cloning the repo and installing Python deps + Node deps (one-time setup below), run the entire demo stack with one command:

```bash
./scripts/run_app.sh
```

The script starts MLflow, runs bootstrap training if no Production-stage models exist yet, starts FastAPI, runs `npm install` on first invocation, and starts the Next.js dashboard. It also force-clears the demo ports (3000, 5001, 8000) before starting so a previous run's orphaned processes don't cause conflicts. Ctrl+C stops everything cleanly.

Open the dashboard at <http://localhost:3000>.

### One-time setup

```bash
# Python deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# OpenAQ API key
cp .env.example .env
# Edit .env and paste your OpenAQ key (register at https://explore.openaq.org/register)

# Node deps for the dashboard
cd app/dashboard
npm install
cd ../..

# Make the launcher executable
chmod +x scripts/run_app.sh scripts/stop_app.sh
```

### Manual run (four terminals)

If you'd rather not use the launcher script:

```bash
# Terminal 1 — MLflow
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --artifacts-destination ./mlartifacts \
  --serve-artifacts \
  --host 0.0.0.0 --port 5001

# Terminal 2 — train + promote to Production (first time only, or after wiping mlflow.db)
export MLFLOW_TRACKING_URI=http://localhost:5001
python3 scripts/bootstrap_train.py 2026-05-15

# Terminal 3 — FastAPI
export MLFLOW_TRACKING_URI=http://localhost:5001
uvicorn include.src.serve:app --reload --port 8000

# Terminal 4 — Dashboard
cd app/dashboard && npm run dev
```

### Running the full Airflow DAG

For the rubric-compliant pipeline demo (instead of the bootstrap-train fast path):

```bash
astro dev start
```

Then open <http://localhost:8080>, unpause `airalert_pipeline`, and click "Trigger DAG."

---

## Model performance

The final model is three independent per-location logistic-regression pipelines (`StandardScaler` + `LogisticRegression(class_weight='balanced', max_iter=1000)`), trained on a 60-day rolling window of hourly PM2.5 features.

| Metric | Naive baseline (always-safe) | AirAlert |
|---|---|---|
| F1 (unsafe class), aggregate | 0.000 | **0.824** |
| Recall (unsafe class), aggregate | 0.000 | **0.885** |
| Precision (unsafe class), aggregate | undefined | 0.772 |
| Accuracy, aggregate | ~0.94 | 0.961 |

Per-location F1:

| Location | F1 | Recall | Precision | TP | FN |
|---|---|---|---|---|---|
| Red Butte | 0.897 | **1.000** | 0.812 | 13 | 0 |
| Smithfield | 0.816 | 0.870 | 0.769 | 20 | 3 |
| Ledges | 0.759 | 0.786 | 0.733 | 11 | 3 |

Red Butte's recall = 1.000 means every unsafe hour in the holdout was correctly identified by the model.

---

## Stakeholder framing

The dashboard is targeted at one user: a K-5 elementary-school administrator (principal, assistant principal, district health-and-safety lead) in Utah making the morning recess decision.

Each PM2.5 sensor pairs with the public elementary schools in its air shed:

| Sensor | District | Nearby K-5 schools |
|---|---|---|
| Red Butte | Salt Lake City SD | Bonneville · Indian Hills · Wasatch · Uintah |
| Smithfield | Cache County SD | Summit · Birch Creek · Heritage |
| Ledges | Washington County SD | Red Mountain · Diamond Valley · Coral Cliffs |

The dashboard's headline names the primary school directly ("Air quality at Bonneville Elementary…"), the controls are weekday-pill day pickers rather than calendar inputs, and recommendations are tailored to whether unsafe hours fall in the 8 AM – 4 PM recess window, the 4 PM – 7 PM after-school window, or outside school operations.

---

## Drift detection

Drift checks run as the 4th task in the 5-task DAG, between `engineer_features` and `retrain_model`. For each location:

- **Reference distribution:** last 7 days of raw PM2.5 (from `include/data/raw/pm25_*.csv`).
- **Recent window:** today's raw PM2.5 file (~24 hourly readings per location).
- **Metric:** `mean_shift_sigma = (recent.mean() - reference.mean()) / reference.std(ddof=0)`.
- **Threshold:** `|mean_shift_sigma| > 2.0` flips the `drifted` flag.
- **Action:** drifted locations are retrained that day, alongside the existing Monday backstop and F1 < 0.70 triggers.

All values are logged to MLflow under a run named `drift_{ds}` and persisted to `include/data/drift/drift_{ds}.json`. Design doc: [`docs/drift_implementation_plan.md`](docs/drift_implementation_plan.md).

---

## Project structure

```
.
├── dags/
│   └── airalert_dag.py              5-task DAG
├── include/
│   ├── src/
│   │   ├── ingest.py                OpenAQ → raw CSVs
│   │   ├── transform.py             raw → features (60-day rolling window)
│   │   ├── drift.py                 mean-shift sigma + JSON + MLflow
│   │   ├── train.py                 StandardScaler + LR + Production promotion
│   │   ├── serve.py                 FastAPI /health + /predict
│   │   └── constants.py             shared constants
│   ├── data/
│   │   ├── raw/                     pm25_{ds}.csv per day
│   │   ├── features/                features_{ds}.csv per day
│   │   └── drift/                   drift_{ds}.json per day
│   └── models/                      pickled bundles + per-location pickles
├── app/
│   └── dashboard/                   Next.js + TypeScript + Tailwind
│       ├── app/
│       │   ├── api/                 health, predict, features, trend routes
│       │   ├── page.tsx             main composition
│       │   └── globals.css
│       ├── components/              all React components
│       └── lib/                     featurePrep, plainLanguage, api, constants, timezone
├── scripts/
│   ├── run_app.sh                   one-command launcher
│   ├── stop_app.sh                  aggressive port killer
│   ├── bootstrap_train.py           idempotent local training
│   ├── sample_openaq.py             OpenAQ exploration helper
│   └── seed_synthetic_raw.py        for tests
├── docs/                            design docs + plans + audit
├── INTERFACE.md                     contracts + decisions + change log
├── COPILOT_LOG.md                   every Copilot interaction + end-of-project reflection
└── requirements.txt
```

---

## Setup

1. **Clone and create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Configure secrets**
   ```bash
   cp .env.example .env
   ```
   Then add your OpenAQ API key (register free at
   <https://explore.openaq.org/account>).

3. **Start the local Airflow environment**
   ```bash
   astro dev start
   ```
   The Airflow UI will be available at <http://localhost:8080>
   (login: `admin` / `admin`). See
   [`astro_setup_guide.md`](astro_setup_guide.md) for full setup details.

4. **Start MLflow tracking** (separate terminal)
   ```bash
   mlflow ui --port 5001
   ```
   MLflow runs on port 5001 because macOS reserves 5000 for AirPlay.

5. **Start the prediction API** (separate terminal, after `train.py` has
   registered models in MLflow)
   ```bash
   uvicorn include.src.serve:app --port 8000
   ```

### Windows quick start

If you are on PowerShell, run the repo launcher instead of the Bash script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\run_app.ps1
```

---

## Design decisions

Eight major design decisions are documented with reasoning in [`INTERFACE.md`](INTERFACE.md):

1. **Data freshness** — no freshness filter; PM2.5 volatility is low enough that any sensor data is usable.
2. **Missing data** — drop NaN rows at ingest; do not impute lags.
3. **Retraining trigger** — weekly Monday backstop + F1 < 0.70 floor + drift > 2.0σ.
4. **Feature engineering** — nine engineered features (three lags, two rolling stats, four temporal).
5. **Aggregation granularity** — one row per (location_id, hour).
6. **Per-location modeling** — three independent classifiers, one per location.
7. **Classifier choice** — class-weight-balanced Logistic Regression with StandardScaler; probabilities bucketed into high/medium/low for the user-facing display.
8. **Dashboard data sourcing** — Node-side feature prep from raw CSVs, recent-pattern hourly fallback for future dates.

---

## What we would improve with more time

- **Probability calibration** via `CalibratedClassifierCV` so the dashboard can show a true percentage instead of a high/medium/low bucket.
- **Non-linear model** (HistGradientBoosting or RandomForest); independent audit suggested ~0.07 F1 lift, but we preserved the Decision 7 commitment to logistic regression.
- **Decision-threshold tuning** per location via Youden's J statistic on a held-out validation fold.
- **Weather features** (temperature, humidity, wind speed) from Open-Meteo; Decision 4 explicitly punted on these to keep the pipeline single-source.
- **Serve.py degraded-boot mode** so uvicorn starts cleanly even before any DAG run has produced a Production-stage model. Design lives in [`docs/serve_first_run_handoff.md`](docs/serve_first_run_handoff.md).
- **Model-version-aware /health** so the dashboard's HealthBadge can show per-location version numbers, not just online/offline.

---

## Acknowledgements

- **OpenAQ** for the public PM2.5 API and the historical data window.
- **Astronomer** for the Astro CLI and the Airflow Docker images.
- **The MLflow team** for the registry + tracking server.
- Our professor for the rubric, the stakeholder framing, and the cross-review protocol that kept this project disciplined.

---

## License

This project was built for a graduate-level course assignment. Code is provided as-is for educational reference.
