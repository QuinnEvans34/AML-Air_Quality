# AirAlert — Copilot Instructions

> **How to use this file:** This file lives at `.github/copilot-instructions.md`.
> GitHub Copilot reads it automatically for every suggestion and Chat interaction
> in this repository. Complete every section marked **[FILL IN]** using your
> finalized `INTERFACE.md` before writing any implementation code.
> Both partners must agree to this file before committing it.

---

## Project Overview

AirAlert is an automated air quality prediction pipeline. It ingests real-time
PM2.5 readings from the OpenAQ v3 API and weather data from the OpenMeteo API,
engineers features, trains a binary classifier that predicts whether air quality
will exceed a safe threshold, and serves predictions via a FastAPI endpoint
connected to a Streamlit dashboard. The full pipeline is orchestrated by an
Airflow DAG that runs daily at 6am.

**Team:** [FILL IN: Student A] + [FILL IN: Student B]
**Repo:** aml-airalert

---

## Tech Stack

[FILL IN]

---

## Shared Constants

Always use these exact values. Never hardcode them inline.

```python
[FILL IN]
```

> Note: Any additional constants (e.g. a freshness threshold for serving,
> a minimum coverage threshold for training data quality) are team decisions
> documented in INTERFACE.md. Add them here once decided.

---

## Data Schema

### `ingest.py` output — `data/raw/pm25_{YYYY-MM-DD}.csv`

| Column | Type | Nullable | Notes |
[FILL IN]

### `transform.py` output — `data/features/features_{YYYY-MM-DD}.csv`

| Column | Type | Nullable | Notes |
[FILL IN]

> Copy your agreed feature columns from `INTERFACE.md` Contract 2 exactly.

### Model prediction input

The model expects these feature columns (exclude timestamp, location_id, is_unsafe):

```python
FEATURE_COLS = [FILL IN]  # copy from your Contract 3 in INTERFACE.md
```

---

## Airflow Conventions

These rules apply to every task function in the DAG. Follow them without exception.

1. **Every task function must return a file path string** — never return a DataFrame or any other object. XComs carry paths, not data.
2. **Every task must save its output to a file before returning** — the return value is the path to that file.
3. **Output file names must include the execution date** — use `context['ds']` (a `YYYY-MM-DD` string) in the filename: `pm25_{context['ds']}.csv`
4. **Raise meaningful exceptions on failure** — use `ValueError` for empty data, `requests.HTTPError` for API failures. Never use bare `except: pass`.
5. **Always check `catchup=False`** in the DAG definition.

```python
# Correct XCom pattern
def my_task(**context) -> str:
    output_path = f"data/raw/pm25_{context['ds']}.csv"
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
- **`pathlib.Path` for all file paths** — never hardcode string paths like `"data/raw/file.csv"`
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

DATA_RAW_DIR      = Path("data/raw")
DATA_PROCESSED_DIR = Path("data/processed")
DATA_FEATURES_DIR  = Path("data/features")
MODELS_DIR         = Path("models")

# File naming — always include the date
raw_path      = DATA_RAW_DIR / f"pm25_{date}.csv"
features_path = DATA_FEATURES_DIR / f"features_{date}.csv"
```

---

## What Copilot Should Know About This Project

- This is a **pair project** — [FILL IN: Student A] owns `ingest.py` and `serve.py`; [FILL IN: Student B] owns `transform.py` and `train.py`
- The lag features in `transform.py` **must be grouped by `location_id`** before shifting — a global shift is a data leakage bug
- The model is a **binary classifier** — `is_unsafe` is the target (1 = PM2.5 > 35.4 μg/m³)
- The primary evaluation metric is **F1 score** on the positive class (unsafe = 1)
- All MLflow logging happens inside Airflow task functions — the MLflow URI inside Docker is `http://host.docker.internal:5000`
