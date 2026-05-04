# AirAlert — Copilot Instructions

> **How to use this file:** This file lives at `.github/copilot-instructions.md`.
> GitHub Copilot reads it automatically for every suggestion and Chat interaction
> in this repository. Both partners must agree to this file before committing it.

---

## Project Overview

AirAlert is an automated air quality prediction pipeline. It ingests hourly PM2.5
readings from the OpenAQ v3 API for three Utah locations, engineers lag and
temporal features, trains a per-location binary classifier that predicts whether
air quality will exceed the EPA unsafe threshold (35.4 μg/m³), and serves
predictions via a FastAPI endpoint connected to a Streamlit dashboard. The full
pipeline is orchestrated by an Apache Airflow DAG running daily at 6am via the
Astro CLI inside Docker.

**Team:** Quinton Evans + Gracelyn Jarret
**Repo:** aml-airalert

---

## Tech Stack

- Python 3.11
- Data: pandas, numpy, pyarrow
- HTTP: requests, python-dotenv
- ML: scikit-learn, mlflow
- Serving: FastAPI, uvicorn, pydantic
- Dashboard: Streamlit
- Orchestration: Apache Airflow via Astro CLI in Docker
- Dev: pytest, pytest-cov, ruff

---

## Shared Constants

Always use these exact values. Never hardcode them inline.

```python
UNSAFE_THRESHOLD = 35.4                    # μg/m³ — PM2.5 unsafe boundary
OPENAQ_PM25_PARAMETER_ID = 2
DATETIME_COL = "timestamp"
MLFLOW_EXPERIMENT = "AirAlert"
MLFLOW_URI = "http://localhost:5001"       # 5001 to dodge macOS AirPlay on 5000

# Three per-location models (Decision 6)
TARGET_LOCATIONS = {
    "red_butte":  ...,                     # Salt Lake City — fill in OpenAQ id
    "smithfield": ...,                     # northern Utah — fill in OpenAQ id
    "ledges":     ...,                     # near Snow Canyon, St. George — fill in OpenAQ id
}
MODEL_NAME_TEMPLATE = "AirAlert_{location}"  # e.g. "AirAlert_red_butte"
```

> Note: any additional constants emerging from later design decisions
> (e.g. retraining threshold) should be documented in `INTERFACE.md` first
> and then mirrored here.

---

## Data Schema

### `ingest.py` output — `include/data/raw/pm25_{YYYY-MM-DD}.csv`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `timestamp` | datetime64[ns, UTC] | No | UTC; one row per location per hour |
| `location_id` | int64 | No | OpenAQ location ID; one of `TARGET_LOCATIONS` |
| `pm25` | float64 | No | μg/m³; rows where pm25 is null are dropped at ingest |

### `transform.py` output — `include/data/features/features_{YYYY-MM-DD}.csv`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `timestamp` | datetime64[ns, UTC] | No | matches Contract 1 |
| `location_id` | int64 | No | matches Contract 1 |
| `is_unsafe` | int64 | No | target — 1 if pm25 > 35.4 |
| `pm25_lag_1h` | float64 | No | shifted 1h within `location_id` |
| `pm25_lag_3h` | float64 | No | shifted 3h within `location_id` |
| `pm25_lag_24h` | float64 | No | shifted 24h within `location_id` |
| `pm25_rolling_mean_3h` | float64 | No | mean over (t-3, t-2, t-1) within `location_id` |
| `pm25_rolling_std_3h` | float64 | No | std over (t-3, t-2, t-1) within `location_id` |
| `hour_of_day` | int64 | No | 0-23 from `timestamp` |
| `day_of_week` | int64 | No | 0-6 from `timestamp.dayofweek` |
| `month_of_year` | int64 | No | 1-12 from `timestamp.month` |
| `is_weekend` | int64 | No | 1 if `day_of_week >= 5` else 0 |

> Copy of `INTERFACE.md` Contract 2. Must stay in sync — the contract is the
> source of truth.

### Model prediction input

The model expects these feature columns (excludes timestamp, location_id, is_unsafe):

```python
FEATURE_COLS = [
    "pm25_lag_1h",
    "pm25_lag_3h",
    "pm25_lag_24h",
    "pm25_rolling_mean_3h",
    "pm25_rolling_std_3h",
    "hour_of_day",
    "day_of_week",
    "month_of_year",
    "is_weekend",
]
```

---

## Airflow Conventions

These rules apply to every task function in the DAG. Follow them without exception.

1. **Every task function must return a file path string** — never return a DataFrame or any other object. XComs carry paths, not data.
2. **Every task must save its output to a file before returning** — the return value is the path to that file.
3. **Output file names must include the execution date** — use `context['ds']` (a `YYYY-MM-DD` string) in the filename: `include/data/raw/pm25_{context['ds']}.csv`
4. **Raise meaningful exceptions on failure** — use `ValueError` for empty data, `requests.HTTPError` for API failures. Never use bare `except: pass`.
5. **Always check `catchup=False`** in the DAG definition.

```python
# Correct XCom pattern
def my_task(**context) -> str:
    output_path = f"include/data/raw/pm25_{context['ds']}.csv"
    df.to_csv(output_path, index=False)
    return output_path  # ← always return a path string

# Pull path from previous task
def next_task(**context) -> str:
    input_path = context['ti'].xcom_pull(task_ids='previous_task_id')
    df = pd.read_csv(input_path)
    ...
```

---

## Code Style

Every function in this project must follow these conventions:

- **Type hints on all function signatures** — `def fetch(date: str) -> pd.DataFrame:`
- **Docstrings with Args, Returns, and Raises** — every function, no exceptions
- **`pathlib.Path` for all file paths** — never hardcode string paths like `"include/data/raw/file.csv"`
- **`response.raise_for_status()`** after every API call — never skip error handling
- **Descriptive variable names** — `pm25_readings_df` not `df`, `raw_output_path` not `path`

```python
# Example of the expected standard
def fetch_pm25_readings(date: str, limit: int = 1000) -> pd.DataFrame:
    """
    Fetch PM2.5 readings from OpenAQ for a given date.

    Args:
        date: Target date in YYYY-MM-DD format
        limit: Maximum number of records to fetch (default 1000)

    Returns:
        DataFrame with columns matching the ingest output schema

    Raises:
        ValueError: If the API returns zero measurements
        requests.HTTPError: If the API call fails
    """
    ...
```

---

## File Path Conventions

```python
from pathlib import Path

DATA_RAW_DIR       = Path("include/data/raw")
DATA_PROCESSED_DIR = Path("include/data/processed")
DATA_FEATURES_DIR  = Path("include/data/features")
MODELS_DIR         = Path("include/models")

# File naming — always include the date
raw_path      = DATA_RAW_DIR / f"pm25_{date}.csv"
features_path = DATA_FEATURES_DIR / f"features_{date}.csv"

# Source code lives under include/src/
# Imports inside DAG tasks: from include.src.ingest import fetch_pm25_readings
```

---

## What Copilot Should Know About This Project

- This is a **pair project** — Quinton Evans owns `include/src/ingest.py` and `include/src/train.py`; Gracelyn Jarret owns `include/src/transform.py` and `include/src/serve.py`. The Airflow DAG (`dags/airalert_dag.py`) and dashboard (`app/dashboard.py`) are joint.
- The lag and rolling features in `transform.py` **must be grouped by `location_id`** before shifting — a global shift is a data leakage bug.
- Rolling features use the prior 3 hours `(t-3, t-2, t-1)` and **must not include the current hour's pm25** — including it would leak the target into its own predictors.
- The model is a **binary classifier** — `is_unsafe` is the target (1 = PM2.5 > 35.4 μg/m³).
- The primary evaluation metric is **F1 score** on the positive class (unsafe = 1).
- **Three per-location models** are trained and registered separately as `AirAlert_red_butte`, `AirAlert_smithfield`, and `AirAlert_ledges`.
- This pipeline does **not** use weather features — OpenAQ PM2.5 readings are the sole data source.
- All MLflow logging happens inside Airflow task functions — the MLflow URI inside the Astro Docker container is `http://host.docker.internal:5001`.
