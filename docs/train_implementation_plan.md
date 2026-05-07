# Train Implementation Plan — `include/src/train.py`

> **Purpose.** Strict outline for creating and implementing
> `include/src/train.py`. Used by the team and by any AI assistant
> generating the file.
> If this document disagrees with `INTERFACE.md`, **`INTERFACE.md` wins.**

> **Owner of this document:** Quinton Evans (QE)
> **Reviewer:** Gracelyn Jarrett (GJ)
> **Branch:** `feat:train-test`
> **Last updated:** 2026-05-04

---

## 1. Goal

Produce a single file at `include/src/train.py` that:

1. Reads a Contract-2 features CSV (one row per `(location_id, hour)` with
   the 9 features in `FEATURE_COLS` plus `is_unsafe` target plus
   `timestamp` + `location_id`).
2. Trains one logistic-regression classifier per location
   (Decision 6 — three per-location models).
3. Registers each model in MLflow under `MODEL_NAME_TEMPLATE.format(...)`.
4. Saves a single `include/models/latest_model.pkl` containing all three
   trained models in a dict, plus per-location date-stamped artifacts.
5. Returns an aggregated metrics dict (mean across locations) suitable for
   Airflow XCom — keys include the five required by the assignment plus
   `false_negatives` and `true_positives` (Decision 3 makes these
   actionable).

The DAG's `retrain_model` task already imports and calls `retrain_task`
from this module; that call signature is already pinned and must not
change.

---

## 2. Source-of-truth references

| Reference | What it governs |
|---|---|
| `INTERFACE.md` Decision 3 | When `retrain_task` gets called (weekly + on FN). Trigger logic lives in the DAG; this module is unconditional when invoked. |
| `INTERFACE.md` Decision 6 | Per-location models — three independent classifiers, registered separately. |
| `INTERFACE.md` Decision 7 | Classifier choice — logistic regression for v1. |
| `INTERFACE.md` Contract 2 | Input schema — `timestamp`, `location_id`, `is_unsafe`, plus 9 feature columns. |
| `INTERFACE.md` Contract 3 | `FEATURE_COLS` list — exactly 9 names; train.py imports this from `constants.py`, never hardcodes. |
| `include/src/constants.py` | `UNSAFE_THRESHOLD`, `MLFLOW_EXPERIMENT`, `MLFLOW_URI`, `MODEL_NAME_TEMPLATE`, `TARGET_LOCATIONS`. |
| `dags/airalert_dag.py` | The caller — `retrain_model` task imports and calls `retrain_task(features_path, ds)`. |
| W6A1 assignment Part 4 | Verification — `include/models/latest_model.pkl` must load with `joblib.load()`; XCom `return_value` must contain `f1`, `baseline_f1`, `accuracy`, `precision`, `recall`. |

---

## 3. Hard rules

1. **Entry point signature is fixed:** `retrain_task(features_path: str, ds: str) -> dict`.
   The DAG already calls it that way — don't change it.
2. **Returned dict must include** at minimum: `f1`, `baseline_f1`,
   `accuracy`, `precision`, `recall` (per the assignment).
   **Additional allowed keys:** `false_negatives`, `true_positives`
   (decision-relevant per Decision 3).
3. **`latest_model.pkl` is a dict** keyed by `location_key` (one of
   `"red_butte"`, `"smithfield"`, `"ledges"`) with sklearn estimators as
   values. Loadable with `joblib.load()`.
4. **Per-location MLflow runs** — one MLflow run per location, registered
   under `MODEL_NAME_TEMPLATE.format(location=<key>)`.
5. **Class imbalance handling** — every classifier must use
   `class_weight="balanced"`. With ~0.6% positive rate this is essential.
6. **Train/test split is chronological** within each location — last 20%
   of rows (sorted by timestamp) is the holdout. Never random-shuffle a
   time series.
7. **Use `FEATURE_COLS` from constants** — never hardcode the column list.
   Constants are the single source of truth for Contract 3.
8. **F1 is computed on the unsafe class** —
   `f1_score(y_true, y_pred, pos_label=1, zero_division=0)`. The
   `zero_division=0` matters because some test windows have no positives.
9. **Lazy imports for heavy libraries** — `sklearn`, `mlflow`, `joblib`
   imported inside the functions that use them, not at module top, so
   DAG parsing stays fast.
10. **`pathlib.Path` for all file paths.** No hardcoded strings.
11. **Do not modify any other file** during this task — `constants.py`,
    `INTERFACE.md`, the DAG, ingest.py, transform.py — all off-limits.

---

## 4. File location and filename

- **Path:** `include/src/train.py` — new file. Does not exist yet.
- **Branch for this work:** `feat:train-test`.

---

## 5. Module docstring (required at top)

```python
"""
train.py — Per-location classifier training and MLflow registration.

Owner:    Quinton Evans (QE)
Reviewer: Gracelyn Jarrett (GJ)

This module trains one logistic-regression classifier per location in
TARGET_LOCATIONS, registers each in MLflow, saves a unified bundle to
``include/models/latest_model.pkl``, and returns a dict of metrics for
Airflow XCom. It is invoked by the ``retrain_model`` task in
``dags/airalert_dag.py``.

Pipeline shape (per call):

    Contract-2 features CSV
        -> split by location_id
            -> for each location:
                  chronological 80/20 split
                  -> train logistic regression with class_weight='balanced'
                  -> compute metrics on the holdout
                  -> log run + register model in MLflow as AirAlert_<location>
            -> bundle all three models into a dict
            -> save dict to include/models/latest_model.pkl
        -> aggregate metrics (mean across locations)
        -> return aggregated dict to Airflow XCom

Decision context (see INTERFACE.md)
-----------------------------------
- Decision 3 — Retraining trigger:  this module trains unconditionally
  when invoked. The DAG decides *when* to invoke (weekly Monday or on a
  detected false negative from the prior day's predictions). FN-trigger
  detection logic is not implemented in this PR — it requires a
  predictions log from serve.py, which is future work.
- Decision 6 — Per-location models: three independent classifiers, one
  per (location_key, location_id) pair in TARGET_LOCATIONS.
- Decision 7 — Classifier choice: logistic regression for v1; chosen
  because predict_proba is reasonably calibrated for this feature set
  and the model is fast to train and easy to explain.

Inputs
------
- features_path  Path string to a Contract-2 CSV (the output of
                 transform.py / engineer_features task).
- ds             YYYY-MM-DD execution date string from Airflow context.

Outputs
-------
- include/models/latest_model.pkl                 — dict of three sklearn estimators
- include/models/{location_key}_{ds}.pkl          — per-location date-stamped
- MLflow runs under experiment MLFLOW_EXPERIMENT   — one per location
- Returned dict (XCom value) with keys:
    f1, baseline_f1, accuracy, precision, recall,
    false_negatives, true_positives

Constraints
-----------
- Class imbalance: every classifier uses class_weight='balanced'.
  Without it the model collapses to "always predict safe" given the
  ~0.6% positive class rate.
- Chronological split, not random — time-series data must not have
  future bleed into the training set.
- F1 is computed with pos_label=1 and zero_division=0 (some holdout
  windows have no unsafe hours).
- FEATURE_COLS comes from include/src/constants.py — never hardcoded
  here, so Contract 3 stays the single source of truth.

Error behavior
--------------
- features_path missing or empty           -> FileNotFoundError / ValueError
- A location has fewer than ~50 rows
  in the features CSV (too sparse to split) -> ValueError per location
- MLflow tracking server unreachable        -> mlflow client error
                                              (not caught — fail loud)
- joblib pickling failure on the bundle     -> propagates

Future work
-----------
- FN-triggered retrain logic — needs predictions log from serve.py
- Calibration of predict_proba — sklearn's
  CalibratedClassifierCV may be added in a follow-up PR
- Promote-on-improvement gating — currently every call overwrites
  latest_model.pkl unconditionally; a future version may compare new
  metrics to MLflow's current "Production" model and only swap on
  improvement.
"""
```

---

## 6. Imports

### Module-level (parsed by Airflow scheduler — keep small):

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from include.src.constants import (
    MLFLOW_EXPERIMENT,
    MLFLOW_URI,
    MODEL_NAME_TEMPLATE,
    TARGET_LOCATIONS,
)

if TYPE_CHECKING:
    # Type-only imports — no runtime cost during DAG parse
    from sklearn.linear_model import LogisticRegression
```

### Lazy imports (inside the functions that use them):

| Library | First-use function |
|---|---|
| `sklearn.linear_model.LogisticRegression` | `train_logistic_regression` |
| `sklearn.metrics` (f1_score, accuracy_score, etc.) | `compute_metrics`, `baseline_f1_score` |
| `mlflow`, `mlflow.sklearn` | `log_run_to_mlflow` |
| `joblib` | `save_model_bundle` |

---

## 7. Module-level constants

`include/src/constants.py` already defines `MLFLOW_EXPERIMENT`,
`MLFLOW_URI`, `MODEL_NAME_TEMPLATE`, and `TARGET_LOCATIONS`. We import
those rather than redeclaring.

Train.py adds these of its own:

```python
MODELS_DIR: Path = Path("include/models")
TEST_FRACTION: float = 0.20  # last 20% of each location's rows -> holdout
LATEST_MODEL_FILENAME: str = "latest_model.pkl"

# FEATURE_COLS — sourced from Contract 3 in INTERFACE.md.
# Imported here from constants once Contract 3 / FEATURE_COLS lives there;
# until then, declared locally and kept exactly in sync with INTERFACE.md.
FEATURE_COLS: list[str] = [
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
TARGET_COL: str = "is_unsafe"
```

> **Note on FEATURE_COLS:** if INTERFACE.md / `constants.py` later
> centralizes FEATURE_COLS, this file should `from include.src.constants
> import FEATURE_COLS` and remove the local copy. Do not duplicate the
> list once a single source exists.

---

## 8. Per-function implementation requirements

Nine functions. Each subsection lists the signature, full docstring
content (verbatim — Claude should match this), and what the body must do.

### 8.1 `load_features(path: Path) -> pd.DataFrame`

**Body must:**
1. Convert `path` to a `Path` if it's a str.
2. If the file does not exist, raise `FileNotFoundError` with a clear
   message.
3. Read the CSV with `pd.read_csv(path, parse_dates=["timestamp"])`.
4. Verify required columns are present: `timestamp`, `location_id`,
   `TARGET_COL`, plus all of `FEATURE_COLS`. Raise `ValueError` listing
   any missing.
5. Verify there are no nulls in any of those required columns. Raise
   `ValueError` listing per-column null counts on violation.
6. Return the DataFrame.

### 8.2 `split_by_location(df: pd.DataFrame) -> dict[int, pd.DataFrame]`

**Body must:**
1. Group `df` by `location_id`.
2. Return a dict mapping each `location_id` to its sorted DataFrame
   (sorted ascending by `timestamp`).
3. Raise `ValueError` if any location_id in the data is not present in
   `TARGET_LOCATIONS.values()`, or vice versa.

### 8.3 `chronological_split(df, test_fraction=TEST_FRACTION)`

Signature:
```python
def chronological_split(
    df: pd.DataFrame, test_fraction: float = TEST_FRACTION
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
```

**Body must:**
1. Sort `df` by `timestamp` ascending (defensive — should already be).
2. Compute `cutoff = int(len(df) * (1 - test_fraction))`.
3. If `cutoff < 24` (less than ~1 day of training rows), raise
   `ValueError("Not enough rows for chronological split")`.
4. Return `(X_train, X_test, y_train, y_test)`:
   - `X_train = df.iloc[:cutoff][FEATURE_COLS]`
   - `X_test = df.iloc[cutoff:][FEATURE_COLS]`
   - `y_train = df.iloc[:cutoff][TARGET_COL].astype(int)`
   - `y_test = df.iloc[cutoff:][TARGET_COL].astype(int)`

### 8.4 `train_logistic_regression(X_train, y_train) -> LogisticRegression`

**Body must:**
1. Lazy-import: `from sklearn.linear_model import LogisticRegression`.
2. Instantiate `LogisticRegression(class_weight="balanced", max_iter=1000, random_state=0)`.
3. Fit on `(X_train, y_train)`.
4. Return the fitted model.

### 8.5 `compute_metrics(model, X_test, y_test) -> dict[str, float | int]`

**Body must:**
1. Lazy-import: `from sklearn.metrics import (f1_score, accuracy_score, precision_score, recall_score, confusion_matrix)`.
2. Predict: `y_pred = model.predict(X_test)`.
3. Compute the five required metrics with `pos_label=1, zero_division=0`
   where the function supports those args (precision/recall/f1).
4. Compute confusion matrix with `confusion_matrix(y_test, y_pred, labels=[0, 1])`.
   Pull `tn, fp, fn, tp = cm.ravel()`.
5. Compute baseline F1 via `baseline_f1_score(y_test)` (next function).
6. Return a dict:
```python
{
    "f1":              float(f1),
    "baseline_f1":     float(baseline_f1),
    "accuracy":        float(acc),
    "precision":       float(prec),
    "recall":          float(rec),
    "false_negatives": int(fn),
    "true_positives":  int(tp),
}
```

### 8.6 `baseline_f1_score(y_test: pd.Series) -> float`

**Body must:**
1. Lazy-import: `from sklearn.metrics import f1_score`.
2. Construct a baseline prediction array of all zeros (= "always predict safe"):
   `y_baseline = [0] * len(y_test)`.
3. Return `float(f1_score(y_test, y_baseline, pos_label=1, zero_division=0))`.
   This will be 0.0 by definition — that's the point. The model should
   beat zero.

### 8.7 `log_run_to_mlflow(model, metrics, location_key, ds) -> str`

**Body must:**
1. Lazy-import: `import mlflow; import mlflow.sklearn`.
2. Set tracking URI: `mlflow.set_tracking_uri(MLFLOW_URI)`.
3. Set experiment: `mlflow.set_experiment(MLFLOW_EXPERIMENT)`.
4. Build run name: `f"{location_key}_{ds}"`.
5. Open `with mlflow.start_run(run_name=run_name) as run:`.
6. Inside the run:
   - `mlflow.log_params({"location_key": location_key, "ds": ds, "class_weight": "balanced"})`
   - `mlflow.log_metrics(metrics)` — note metrics dict has both floats
     and ints; MLflow accepts both.
   - Register the model:
     `mlflow.sklearn.log_model(model, artifact_path="model",
     registered_model_name=MODEL_NAME_TEMPLATE.format(location=location_key))`
7. Return `run.info.run_id` (a UUID string).

### 8.8 `save_model_bundle(models_by_location, ds) -> Path`

Signature:
```python
def save_model_bundle(
    models_by_location: dict[str, "LogisticRegression"], ds: str
) -> Path:
```

**Body must:**
1. Lazy-import `import joblib`.
2. Validate that the dict has all three expected keys
   (set(models_by_location) == set(TARGET_LOCATIONS)). Raise
   `ValueError` listing mismatches if not.
3. `MODELS_DIR.mkdir(parents=True, exist_ok=True)`.
4. Per-location artifacts: for each `(location_key, model)`, dump to
   `MODELS_DIR / f"{location_key}_{ds}.pkl"`.
5. Bundle: dump the entire dict to `MODELS_DIR / LATEST_MODEL_FILENAME`.
6. Return the bundle path (`MODELS_DIR / LATEST_MODEL_FILENAME`).

### 8.9 `retrain_task(features_path: str, ds: str) -> dict`

This is the orchestrator and the public entry point.

**Body must:**
1. Validate inputs: `features_path` is a non-empty string, `ds` is a
   YYYY-MM-DD string. Raise `ValueError` on either failure.
2. `df = load_features(Path(features_path))`.
3. `per_location_frames = split_by_location(df)`.
4. Per-location loop, accumulating models and metrics:
   ```python
   models_by_location: dict[str, LogisticRegression] = {}
   per_loc_metrics: dict[str, dict] = {}
   for location_key, location_id in TARGET_LOCATIONS.items():
       loc_df = per_location_frames[location_id]
       X_tr, X_te, y_tr, y_te = chronological_split(loc_df)
       model = train_logistic_regression(X_tr, y_tr)
       metrics = compute_metrics(model, X_te, y_te)
       log_run_to_mlflow(model, metrics, location_key, ds)
       models_by_location[location_key] = model
       per_loc_metrics[location_key] = metrics
   ```
5. Bundle: `bundle_path = save_model_bundle(models_by_location, ds)`.
6. Aggregate: take the mean of each metric across the three locations
   (sum and average for floats; sum for the int counts):
   ```python
   keys_float = ("f1", "baseline_f1", "accuracy", "precision", "recall")
   keys_int   = ("false_negatives", "true_positives")
   aggregated: dict[str, float | int] = {}
   for k in keys_float:
       aggregated[k] = sum(m[k] for m in per_loc_metrics.values()) / len(per_loc_metrics)
   for k in keys_int:
       aggregated[k] = sum(m[k] for m in per_loc_metrics.values())
   ```
7. Return the aggregated dict. (Per-location detail lives in MLflow.)

---

## 9. Testing strategy

**Round 1 (this PR's smoke test):** Run against
`include/data/mock/mock_transform_output.csv`. The mock has 8 rows × 12
columns and matches Contract 2 exactly. Expected behavior:
`chronological_split` will likely raise `ValueError("Not enough rows for
chronological split")` because the mock has too few rows per location —
that's a feature, not a bug. The mock is too small for real training;
write a slightly larger fixture if needed (50+ rows per location), or
skip until real data exists.

**Round 2 (after Gracelyn's transform.py lands):** Pipe the 7 days of
ingest output we already have through transform.py to get a real
Contract-2 CSV, then run `retrain_task` against it. Expected:
- 3 MLflow runs visible at `localhost:5001`
- `include/models/latest_model.pkl` loadable via `joblib.load()`,
  containing 3 sklearn estimators
- Returned dict has all 7 keys

**Round 3 (Part 4 verification):** Trigger the full DAG manually in the
Airflow UI; all 4 tasks green; XCom on `retrain_model` has the metric
keys.

---

## 10. What NOT to change

- Any other file in the repo (`constants.py`, the DAG, INTERFACE.md,
  ingest.py, transform.py — all off-limits during this task).
- The signature of `retrain_task` — the DAG already imports and calls
  it as `retrain_task(features_path, ds)`.
- The set of keys in the returned dict's required portion (`f1`,
  `baseline_f1`, `accuracy`, `precision`, `recall`) — adding optional
  keys is fine; renaming or removing the required ones is not.

---

## 11. Cross-review checklist coverage

| Item | Where in this file |
|---|---|
| Returns a string file path / dict (per spec) | `retrain_task` returns dict (Part 4 explicit exception) |
| Output file saved before return | `save_model_bundle` writes both per-location and bundle before returning |
| Filename includes execution date | `{location_key}_{ds}.pkl`; `latest_model.pkl` is the rolling pointer |
| Idempotency check | Handled by the DAG `retrain_model` task wrapper (cached metrics_{ds}.json); train.py itself trains unconditionally, which is correct for an event-triggered system |
| Column names match Contract 2 | `load_features` validates; `FEATURE_COLS` comes from the contract |
| Lag features grouped by location_id | Enforced upstream in transform.py; we consume the pre-grouped output |
| Meaningful exception on failure | `FileNotFoundError`, `ValueError` with specific messages everywhere |
| Paths use `include/data/` and `include/models/` | `MODELS_DIR = Path("include/models")` |
| No hardcoded API keys or absolute paths | None present; MLflow URI from `constants.py` |

---

## 12. Acceptance criteria

The implementation is complete when:

- [ ] All 9 functions are defined with the signatures shown in §8.
- [ ] Module docstring matches §5.
- [ ] Imports split between module-level (§6.1) and lazy (§6.2).
- [ ] Module-level constants present (§7).
- [ ] No file other than `include/src/train.py` has been modified.
- [ ] `python -c "from include.src.train import retrain_task"` runs
      without import error.
- [ ] `retrain_task` invoked on a sufficiently large Contract-2 CSV
      returns a dict with all 7 keys, populates 3 MLflow runs, and writes
      `include/models/latest_model.pkl` loadable by `joblib.load()`.
- [ ] All cross-review checklist items in §11 are visibly satisfied
      in the code.

---

## 13. Two-commit flow on `feat:train-test`

This file's implementation is split across two commits:

**Commit 1 — signatures + docstrings only.**
Generate `include/src/train.py` with the module docstring (§5), all 9
function signatures (§8.1–§8.9), full Args/Returns/Raises docstrings
that match what each body will eventually do, and module-level
constants (§7). **Function bodies are docstring-only — no `pass`, no
`raise`, no logic.** Imports are added (§6) but most go unused at this
stage; that's expected.

**Commit 2 — fill in the bodies.**
Implement each function body per §8 verbatim. Run the round-1 smoke
test from §9 to verify imports resolve and trivial paths work.

After commit 2, push and open the PR against `main`.
