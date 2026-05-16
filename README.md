# AirAlert

Air quality prediction pipeline that ingests PM2.5 readings from the
[OpenAQ v3 API](https://api.openaq.org/v3) for three Utah locations
(Red Butte in Salt Lake City, Smithfield in northern Utah, and Ledges by
Snow Canyon in St. George), engineers temporal and lag features, trains a
per-location binary classifier that predicts whether air quality will
exceed the EPA unhealthy PM2.5 threshold of 35.4 μg/m³, and serves
predictions via a FastAPI endpoint connected to a Streamlit dashboard.
The pipeline is orchestrated by an Apache Airflow DAG running daily via
the Astro CLI inside Docker.

## Team

| Partner | Modules |
|---|---|
| Quinton Evans | `include/src/ingest.py`, `include/src/train.py` |
| Gracelyn Jarret | `include/src/transform.py`, `include/src/serve.py` |
| Both | `dags/airalert_dag.py`, `app/dashboard.py` |

## Project Structure

```
.
├── dags/                     # Airflow DAGs (orchestration)
├── include/
│   ├── src/                  # Python source modules (ingest, transform, train, serve)
│   ├── data/
│   │   ├── raw/              # ingest.py output (gitignored)
│   │   ├── features/         # transform.py output (gitignored)
│   │   └── mock/             # development mock CSVs (gitignored)
│   ├── models/               # local model artifacts (gitignored)
│   └── mlruns/               # MLflow tracking store (gitignored)
├── app/                      # Streamlit dashboard
├── tests/                    # pytest tests
├── scripts/                  # one-off scripts (e.g., API smoke tests)
├── .github/
│   ├── copilot-instructions.md
│   └── agents.md
├── INTERFACE.md              # design decisions and data contracts
├── COPILOT_LOG.md            # AI assistance interaction log
├── Dockerfile                # Astro Runtime image
├── requirements.txt
├── .env.example
└── README.md
```

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

On the first run, the launcher seeds synthetic raw history, bootstraps the
three Production models in MLflow, starts FastAPI, and starts the dashboard.

## Documentation

- [`INTERFACE.md`](INTERFACE.md) — design decisions, data contracts, and
  architectural agreements between partners
- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) —
  Copilot AI configuration (schema, conventions, project facts)
- [`.github/agents.md`](.github/agents.md) — Copilot Agent constraints
- [`COPILOT_LOG.md`](COPILOT_LOG.md) — AI assistance interaction log
- [`astro_setup_guide.md`](astro_setup_guide.md) — local Airflow environment
  setup walkthrough

## Tech Stack

Python 3.11, pandas, numpy, scikit-learn, MLflow, FastAPI, Streamlit,
Apache Airflow (via Astro CLI), pytest, ruff.
