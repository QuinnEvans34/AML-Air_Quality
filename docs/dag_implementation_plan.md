# DAG Implementation Plan — `dags/airalert_dag.py`

> **Purpose.** Strict outline for implementing the AirAlert Airflow DAG.
> Used by the team and by any AI assistant generating the file.
> If this document disagrees with `INTERFACE.md`, `INTERFACE.md` wins.

> **Owner of this document:** Quinton Evans (QE)
> **Reviewer:** Gracelyn Jarrett (GJ)
> **Last updated:** 2026-05-04

---

## 1. Goal

Produce a single file at `dags/airalert_dag.py` that defines the
`airalert_pipeline` DAG. The DAG ingests yesterday's PM2.5 data,
validates its schema, engineers features, and retrains the per-location
classifiers — once per day at 06:00 UTC.

This file is the **only file** to be created or modified by this task.
Pipeline scripts (`include/src/ingest.py`, `include/src/transform.py`,
`include/src/train.py`) are out of scope and are imported lazily.

---

## 2. Source-of-truth references

Read these before writing or generating code:

| Reference | What it governs |
|---|---|
| `INTERFACE.md` Contract 1 | Schema of `include/data/raw/pm25_{ds}.csv` |
| `INTERFACE.md` Contract 2 | Schema of `include/data/features/features_{ds}.csv` |
| `INTERFACE.md` Module Ownership | Who reviews this file |
| `.github/copilot-instructions.md` Airflow Conventions | XCom rule, file-path rule, `catchup=False` |
| `.github/copilot-instructions.md` Code Style | Type hints, docstrings, `pathlib.Path`, descriptive names |
| `.github/agents.md` Output File Naming Convention | `include/data/raw/pm25_{ds}.csv` etc. |
| Week 6 Assignment Part 2 — "Implement the DAG tasks" | Hard rules below |

---

## 3. Hard rules (mandatory)

Every task function in this file MUST satisfy all of the following:

1. **Use the `@task` decorator** from `airflow.decorators`. No `PythonOperator`.
   No manual `xcom_push` / `xcom_pull`.
2. **Return a string file path** for the first three tasks (`fetch_air_quality`,
   `validate_schema`, `engineer_features`). Never return a `DataFrame` or `None`.
3. **`retrain_model` is the documented exception:** it returns a `dict` whose
   keys include `f1`, `baseline_f1`, `accuracy`, `precision`, `recall` because
   Part 4 of the assignment verifies these keys in XCom.
4. **Get the execution date via** `get_current_context()["ds"]`. Never call
   `datetime.now()` for filenames or anywhere else inside a task.
5. **Idempotency check** at the top of any task that writes a file — if the
   output file for this `ds` already exists, return its path immediately.
6. **Raise meaningful exceptions on failure.** No bare `except: pass`.
   `ValueError` for empty / malformed data, `requests.HTTPError` for API
   failures (raised by upstream pipeline scripts), `FileNotFoundError`
   when a referenced upstream file is missing.
7. **Use `pathlib.Path`** for every file path. Never hardcode strings like
   `"include/data/raw/file.csv"`.
8. **All paths begin with `include/data/`** (Astro convention). Never use
   `data/` at the repo root.
9. **No hardcoded API keys, no absolute local paths.** Secrets live in `.env`
   and are loaded by the pipeline scripts.

---

## 4. File location and filename

- **Path:** `dags/airalert_dag.py` — exactly this. No alternative location is
  scanned by the Astro Airflow scheduler.
- **Filename suffix `_dag.py`** matches the default Astro DAG-discovery regex.

---

## 5. Module docstring (required at the very top)

The module docstring must describe inputs, outputs, the schedule, and the
task chain. Use this template:

```python
"""
airalert_dag.py — Daily AirAlert pipeline.

Owner:    Quinton Evans (QE)
Reviewer: Gracelyn Jarrett (GJ)

Schedule: 06:00 UTC daily (cron `0 6 * * *`).

Pipeline (linear chain — TaskFlow API):

    fetch_air_quality        ->  include/data/raw/pm25_{ds}.csv
    validate_schema          ->  pass-through (Contract 1 assertions)
    engineer_features        ->  include/data/features/features_{ds}.csv
    retrain_model            ->  metrics dict in XCom + model artifacts on disk

Each task pulls the execution date from get_current_context()["ds"] and
checks for an existing output file before doing work (idempotency).

Pipeline scripts live in include/src/ and are imported lazily inside each
task to keep DAG-parse-time cheap.
"""
```

---

## 6. Imports

### Module-level (parsed every ~30 seconds by the scheduler — keep small):

```python
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
```

### Lazy imports (inside each `@task` function — heavy):

- `import pandas as pd`         — only inside `validate_schema`
- `import json`                 — only inside `retrain_model`
- `from include.src.ingest import ingest_task`         — inside `fetch_air_quality`
- `from include.src.transform import transform_task`   — inside `engineer_features`
- `from include.src.train import retrain_task`         — inside `retrain_model`

**Why lazy:** Airflow re-parses every DAG file on a tight loop. Heavy
imports at module level slow the scheduler and waste memory. Inside a
`@task`, the import only runs when that task executes.

---

## 7. Module-level constants

```python
RAW_DATA_DIR      = Path("include/data/raw")
FEATURES_DATA_DIR = Path("include/data/features")
MODELS_DIR        = Path("include/models")
```

These are referenced by every task. Single-source-of-truth pattern: if the
project layout shifts, only these three lines change.

---

## 8. DAG decorator configuration

Apply `@dag(...)` to a function named `airalert_pipeline`. Exact
parameter values:

| Parameter | Value | Why |
|---|---|---|
| `dag_id` | `"airalert_pipeline"` | Matches Part 4: "trigger airalert_pipeline manually" |
| `description` | `"Daily AirAlert PM2.5 ingestion → features → retrain pipeline"` | UI clarity |
| `start_date` | `datetime(2026, 5, 1)` | Recent enough to allow manual triggers; not a backlog |
| `schedule` | `"0 6 * * *"` | 6am UTC daily (project overview) |
| `catchup` | `False` | **Mandatory** — without it, Airflow runs every missed day on first start |
| `max_active_runs` | `1` | One run at a time; prevents two runs racing on the same `pm25_{ds}.csv` |
| `default_args` | dict (see below) | One retry on transient failures, no past-run dependency |
| `tags` | `["airalert", "pm25", "production"]` | UI filtering |

`default_args` dict:

```python
default_args={
    "owner": "airalert-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}
```

---

## 9. Tasks

Each task is a `@task`-decorated nested function defined inside
`def airalert_pipeline()`. The four tasks must appear in the order
listed below.

### 9.1 `fetch_air_quality`

```python
@task
def fetch_air_quality() -> str:
    """
    Ingest one day of PM2.5 readings for all TARGET_LOCATIONS via OpenAQ.

    Returns:
        Absolute path string to include/data/raw/pm25_{ds}.csv.

    Raises:
        ValueError:           if no readings were returned across all locations.
        requests.HTTPError:   on OpenAQ API failure (raised inside ingest_task).
    """
    ctx = get_current_context()
    ds = ctx["ds"]
    output_path = RAW_DATA_DIR / f"pm25_{ds}.csv"

    if output_path.exists():
        return str(output_path)

    from include.src.ingest import ingest_task
    return ingest_task(**ctx)
```

**Notes:**
- Pulls `ds` from context first, before any work or imports.
- Idempotency check before the lazy import — saves the import cost on rerun.
- `**ctx` is forwarded to `ingest_task` so the underlying script has full
  Airflow context if it wants it.
- Returns `str(output_path)` — XCom carries a path string.

### 9.2 `validate_schema`

```python
@task
def validate_schema(raw_path: str) -> str:
    """
    Assert Contract 1 schema on the raw CSV; pass-through on success.

    Args:
        raw_path: file path string from fetch_air_quality.

    Returns:
        The same raw_path (no transformation — pass-through pattern).

    Raises:
        FileNotFoundError: if raw_path does not exist on disk.
        ValueError:        if Contract 1 columns are missing, dtypes wrong,
                           or any null appears in a non-nullable column.
    """
    import pandas as pd

    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Upstream file missing: {raw_path}")

    df = pd.read_csv(path, parse_dates=["timestamp"])

    required = {"timestamp", "location_id", "pm25"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Contract 1 columns missing from {path}: {missing}")

    null_counts = df[list(required)].isna().sum()
    bad = null_counts[null_counts > 0].to_dict()
    if bad:
        raise ValueError(f"Nulls in Contract 1 output {path}: {bad}")

    if not pd.api.types.is_numeric_dtype(df["pm25"]):
        raise ValueError(f"pm25 is not numeric (dtype={df['pm25'].dtype})")
    if not pd.api.types.is_integer_dtype(df["location_id"]):
        raise ValueError(f"location_id is not integral (dtype={df['location_id'].dtype})")

    return raw_path
```

**Notes:**
- Pass-through: returns the input path unchanged.
- No file-existence idempotency check needed — pure function with no side
  effects, naturally idempotent on repeated calls.
- Three distinct violation classes (missing columns, null cells, wrong dtypes)
  raise three distinct error messages — fail-loudly satisfies Rule 6.
- Reads against Contract 1 in `INTERFACE.md` (3 columns: `timestamp`,
  `location_id`, `pm25`).

### 9.3 `engineer_features`

```python
@task
def engineer_features(validated_path: str) -> str:
    """
    Build the Contract 2 feature matrix from validated raw data.

    Args:
        validated_path: file path string from validate_schema.

    Returns:
        Absolute path string to include/data/features/features_{ds}.csv.

    Raises:
        ValueError: if no rows survive feature computation
                    (raised inside transform_task).
    """
    ctx = get_current_context()
    ds = ctx["ds"]
    output_path = FEATURES_DATA_DIR / f"features_{ds}.csv"

    if output_path.exists():
        return str(output_path)

    from include.src.transform import transform_task
    return transform_task(input_path=validated_path, **ctx)
```

**Notes:**
- Same shape as `fetch_air_quality` — consistency makes the cross-review
  checklist trivial.
- Takes `validated_path` from upstream as a positional argument; TaskFlow
  handles XCom transparently.
- Output path uses `FEATURES_DATA_DIR` constant.
- Does not enforce Contract 2 schema here — `transform.py` validates
  internally before saving.

### 9.4 `retrain_model`

```python
@task
def retrain_model(features_path: str) -> dict:
    """
    Retrain the per-location classifiers and register them in MLflow.

    Args:
        features_path: file path string from engineer_features.

    Returns:
        Metrics dict with keys: f1, baseline_f1, accuracy, precision, recall.
        Visible in XCom for the Part 4 verification.

    Raises:
        ValueError: if features_path is missing or empty
                    (raised inside retrain_task).
    """
    import json

    ctx = get_current_context()
    ds = ctx["ds"]
    metrics_path = MODELS_DIR / f"metrics_{ds}.json"

    if metrics_path.exists():
        return json.loads(metrics_path.read_text())

    from include.src.train import retrain_task
    metrics = retrain_task(features_path=features_path, ds=ds)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics))
    return metrics
```

**Notes:**
- This is the **only task that returns a dict instead of a path string** —
  required by Part 4's XCom verification (`return_value` must contain
  `f1`, `baseline_f1`, `accuracy`, `precision`, `recall`).
- Idempotency uses a `metrics_{ds}.json` cache: re-running the DAG on the
  same date returns the cached metrics dict without retraining.
- The model artifact files themselves are written by `train.py` and have
  their own idempotency protection there.

---

## 10. Wiring block

Inside the body of `def airalert_pipeline()`, after the four `@task`
definitions, add the linear wiring chain exactly as written here:

```python
    raw       = fetch_air_quality()
    validated = validate_schema(raw)
    features  = engineer_features(validated)
    retrain_model(features)
```

TaskFlow infers the dependency graph from the function calls. Do not
use `>>` or `set_upstream`.

---

## 11. DAG instantiation

At module level — outside the function body — call:

```python
airalert_pipeline()
```

This invocation is what makes the DAG visible to the Airflow scheduler.
Without it, the file parses cleanly but no DAG appears in the UI.

---

## 12. What NOT to include in this file

- **No implementation of `ingest_task`, `transform_task`, or `retrain_task`.**
  Those live in `include/src/{ingest,transform,train}.py` and are imported
  lazily inside the matching `@task`.
- **No mock or synthetic data generation.** Per the assignment, the
  synthetic fallback is handled by the pipeline scripts, not by the DAG.
- **No tests.** DAG tests live under `tests/dags/`, not in this file.
- **No `if __name__ == "__main__":` block.** The DAG is loaded by Airflow,
  not run as a script.
- **No Airflow connections, variables, or `Variable.get()` calls.** Secrets
  stay in `.env` and are loaded by the pipeline scripts.
- **No additional helper functions outside the `@task` definitions** unless
  they are reviewed and added to this plan first.

---

## 13. Cross-review checklist coverage

These are the items listed in Week 6 Part 3. The DAG file must satisfy
every row:

| Checklist item | Where in this file |
|---|---|
| Returns a string file path — not DataFrame or None | All 4 tasks (retrain returns dict by spec) |
| Output file saved before the return statement | Pipeline scripts handle saving; tasks return after the call returns |
| Filename includes execution date from `get_current_context()` | `pm25_{ds}.csv`, `features_{ds}.csv`, `metrics_{ds}.json` |
| Idempotency check present | `output_path.exists()` in 3 of 4 tasks; `validate_schema` is naturally idempotent |
| Column names exactly match the relevant contract | `validate_schema` is the explicit gate against Contract 1 |
| Lag features grouped by `location_id` | Enforced inside `transform.py` (out of scope for this file) |
| Meaningful exception raised on failure | Every `raise` names the specific violation |
| Paths use `include/data/` — not `data/` at repo root | Three module-level `Path` constants |
| No hardcoded API keys or absolute local paths | None present |

---

## 14. Acceptance criteria

The file is complete when:

- [ ] All four `@task` functions exist with the signatures shown in §9.
- [ ] Module docstring matches §5.
- [ ] Imports split between module-level (§6.1) and lazy (§6.2) as specified.
- [ ] Three module-level path constants present (§7).
- [ ] `@dag` decorator parameters match §8 exactly.
- [ ] Wiring block matches §10 exactly.
- [ ] `airalert_pipeline()` invocation at module level (§11).
- [ ] Every Hard Rule (§3) is satisfied.
- [ ] Every Cross-review checklist item (§13) is satisfied.
- [ ] No file in the repo other than `dags/airalert_dag.py` is created or modified.
- [ ] File length is in the 130–180 line range (sanity check; not a hard limit).
