# Drift Detection Implementation Plan (W7A1 Part 2)

**Status:** source of truth for the migration that adds drift detection to
the AirAlert pipeline. This document describes the agreed design; the code
changes follow it.

## Assignment context (from W7A1 Part 2)

> Add a drift check task to the Airflow DAG between `_engineer_task` and
> `_retrain_task`. The task should compare a recent window of PM2.5 values
> against a reference distribution from training and log the result to
> MLflow.
>
> At minimum, track mean shift — how many standard deviations has the
> recent mean moved from the training mean? Log `mean_shift_sigma` and a
> boolean `drifted` flag as MLflow metrics. Document your drift threshold
> in `INTERFACE.md` under Decision 3's reasoning — your retraining
> trigger and drift threshold should be consistent with each other.

## Decision (extends Decision 3 in `INTERFACE.md`)

Drift is a **third retrain trigger**, layered on top of the two from the
W6 design:

1. Weekly Monday backstop (unchanged).
2. Prior per-location F1 < `F1_RETRAIN_THRESHOLD` (= 0.70) (unchanged).
3. **NEW** — per-location `|mean_shift_sigma|` > `DRIFT_SIGMA_THRESHOLD`
   (= 2.0).

Decision precedence is per location, evaluated in order:

| Precedence | Condition | Decision | Reason string |
|---|---|---|---|
| 1 | `ds.weekday() == 0` (Monday) | retrain | `"weekly Monday backstop"` |
| 2 | no `metrics_*.json` on disk | retrain | `"bootstrap (no prior metrics)"` |
| 3 | no entry for this location in latest `per_location` | retrain | `"bootstrap (no prior {loc} metrics)"` |
| 4 | **`drift[loc].drifted == True`** | **retrain** | **`"drift sigma={s:.2f} > threshold {DRIFT_SIGMA_THRESHOLD}"`** |
| 5 | latest `per_location[loc].f1 < 0.70` | retrain | `"prior f1={x:.3f} < threshold 0.70"` |
| 6 | otherwise | skip | `"prior f1={x:.3f} ≥ threshold 0.70 and drift sigma={s:.2f} within ±{t}"` |

Why 2.0 σ specifically — and why it is consistent with the 0.70 F1 floor:

- **2σ catches the upstream signal before the downstream metric collapses.**
  By the time F1 has dropped below 0.70 the model is already underperforming
  on real days; the 2σ drift trigger is the *leading* indicator, F1 < 0.70
  is the *lagging* indicator. Both have to be present in Decision 3 for the
  retrain trigger to react to both causes (covariate shift) and consequences
  (loss of skill).
- **2σ on a 7-day reference (≈168 hourly observations per location) is
  unlikely to fire on routine noise** but reliably fires on a sustained
  shift larger than ±2 standard deviations of the training distribution —
  e.g. the leading edge of wildfire smoke or a multi-day inversion. A 3σ
  cut would only fire on catastrophic shifts and would let real drift go
  unflagged until F1 has already collapsed; a 1σ cut would fire on
  background variation and force unnecessary retrains.
- **Consistency check:** if 2σ drift is sustained for several days, the
  per-location F1 on the unsafe class will fall under 0.70 within roughly
  one retrain cycle. The two triggers overlap deliberately rather than
  contradict.

## Why this is a code change

The W6 DAG has four tasks. W7A1 explicitly requires a fifth task between
`engineer_features` and `retrain_model`. The drift verdict must be
available to `retrain_model` so the new precedence rule can be applied,
which means drift must be its own upstream task — not a helper called
inside `retrain_model`.

To honor the new contract, the DAG needs to:

1. Run a new `check_drift` task after features are built.
2. Persist the per-location drift verdict to disk and to MLflow.
3. Feed the verdict into `_per_location_decisions` so it joins Monday and
   F1 < 0.70 as a retrain trigger.
4. Carry through every existing W6 idempotency, bootstrap, and audit
   guarantee without regression.

## Architecture

```
fetch_air_quality → validate_schema → engineer_features → check_drift → retrain_model
                                                              │              │
                                                              │              │
                                              raw pm25 history │              │
                                                  (ds-7..ds-1) │              │
                                                              ↓              │
                                         drift_check_task(ds=ds)             │
                                                              │              │
                                              per-location σ + drifted flag  │
                                                              │              │
                                                              ▼              │
                                             include/data/drift/drift_{ds}.json
                                                              │              │
                                                              └─── path ─────┤
                                                                             ▼
                                                          _per_location_decisions
                                                          (Monday | bootstrap | DRIFT | F1)
                                                                             │
                                                             retrain list ──┴── keep list
                                                                  │              │
                                                          train.retrain_task    carry forward
                                                                  └──── merge ───┘
                                                                             │
                                                                metrics_{ds}.json + latest_model.pkl
                                                                             │
                                                                            XCom
```

Three things matter about this picture:

- **Drift reads raw PM2.5, not features.** The features CSV carries lags,
  rolling stats, and `is_unsafe` — but not raw `pm25`. The assignment
  language is "recent window of PM2.5 values," so the drift task reads
  `include/data/raw/pm25_{date}.csv` directly. Features ordering is still
  enforced by passing the features path as an upstream dependency, but the
  features payload itself is unused inside drift.
- **Drift writes a JSON artifact, not a DataFrame.** Same XCom convention
  as every other task: return a file path string.
- **Drift logs to MLflow under one run per ds.** Per-location metrics live
  on that single drift run, named `drift_{ds}`. MLflow failures are
  best-effort and never block the JSON write — same handling pattern as
  `log_run_to_mlflow` in `train.py`.

## Drift computation

For each `location_key, location_id` in `TARGET_LOCATIONS`:

1. **Reference series.** Concatenate raw rows from
   `include/data/raw/pm25_{d}.csv` for each `d ∈ [ds - DRIFT_REFERENCE_DAYS,
   ds - 1]` where the file exists; filter to this `location_id`; take the
   `pm25` column; drop NaNs.
2. **Recent series.** Read `include/data/raw/pm25_{ds}.csv`; filter to this
   `location_id`; take the `pm25` column; drop NaNs.
3. **Compute statistics:**

   ```python
   ref_mean = reference.mean()
   ref_std  = reference.std(ddof=0)
   recent_mean = recent.mean()
   if ref_std == 0 or not np.isfinite(ref_std):
       sigma = 0.0
       drifted = False
       inconclusive = True
   else:
       sigma = (recent_mean - ref_mean) / ref_std
       drifted = abs(sigma) > DRIFT_SIGMA_THRESHOLD
       inconclusive = False
   ```

4. **Sparse-window guard.** If `len(reference) < 24` or `len(recent) < 1`,
   set `sigma = 0.0`, `drifted = False`, `inconclusive = True`, and log a
   warning. This avoids false-positive drift on backfill days where the
   raw history is incomplete.

`drifted` is the per-location boolean the DAG reads to apply Precedence
rule 4. `mean_shift_sigma` is the float metric the assignment requires
logged.

## Drift verdict file structure

Every daily run writes `include/data/drift/drift_{ds}.json`:

```json
{
  "ds": "2026-05-13",
  "reference_window_days": 7,
  "recent_window_days": 1,
  "sigma_threshold": 2.0,
  "global_drifted": true,
  "per_location": {
    "red_butte": {
      "reference_mean": 12.4,
      "reference_std": 6.1,
      "recent_mean": 27.8,
      "n_reference": 168,
      "n_recent": 24,
      "mean_shift_sigma": 2.52,
      "drifted": true,
      "inconclusive": false
    },
    "smithfield": {
      "reference_mean": 18.0,
      "reference_std": 9.0,
      "recent_mean": 19.1,
      "n_reference": 168,
      "n_recent": 24,
      "mean_shift_sigma": 0.12,
      "drifted": false,
      "inconclusive": false
    },
    "ledges": {
      "reference_mean": 5.4,
      "reference_std": 2.1,
      "recent_mean": 6.0,
      "n_reference": 168,
      "n_recent": 24,
      "mean_shift_sigma": 0.29,
      "drifted": false,
      "inconclusive": false
    }
  }
}
```

- `global_drifted` is `any(per_location[loc]["drifted"] for loc in TARGET_LOCATIONS)`.
- `inconclusive == True` means the sparse-window or zero-std guard fired
  and the verdict for that location should not be trusted; it is logged as
  `drifted = false` so an inconclusive day never forces a retrain on noise.

## MLflow run shape

One run per `ds` under experiment `MLFLOW_EXPERIMENT`, run name
`drift_{ds}`. Logged values:

**Params**
- `ds`
- `reference_window_days`
- `recent_window_days`
- `sigma_threshold`
- `n_reference_<location_key>` — for each location
- `n_recent_<location_key>` — for each location

**Metrics**
- `mean_shift_sigma_<location_key>` — for each location (assignment-required name, suffixed for per-location)
- `drifted_<location_key>` — 0 or 1 for each location (assignment-required name, suffixed for per-location)
- `global_drifted` — 0 or 1

If `MLFLOW_URI` is unreachable or `AIRALERT_SKIP_MLFLOW` is set, the JSON
artifact is still written and the task succeeds. MLflow failures emit a
warning log line. This matches the best-effort handling in
`include/src/train.py`.

## Files that change

### 1. `include/src/constants.py` (additive)

Three new constants:

```python
# Decision 3 — drift detection (W7A1).
# Per-location absolute mean-shift sigma above this threshold trips the
# drift verdict, which is one of the three retrain triggers. 2.0 is the
# leading-indicator partner to the 0.70 F1 lagging-indicator floor; the
# reasoning is in INTERFACE.md Decision 3.
DRIFT_SIGMA_THRESHOLD: float = 2.0

# Number of prior days of raw PM2.5 data that form the reference
# distribution for the drift check. 7 matches the rolling window
# transform.py uses to build features, so drift compares against the
# same data the model was trained on.
DRIFT_REFERENCE_DAYS: int = 7

# Number of days of raw PM2.5 data that form the recent window.
# 1 = just today; aligns with the daily DAG cadence and gives the drift
# task a ~24-row recent window per location.
DRIFT_RECENT_DAYS: int = 1
```

### 2. `include/src/drift.py` (new file)

Module structure:

```python
"""drift.py — PM2.5 drift detection for AirAlert."""

from __future__ import annotations
from pathlib import Path
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from include.src.constants import (
    DATETIME_COL,
    DRIFT_RECENT_DAYS,
    DRIFT_REFERENCE_DAYS,
    DRIFT_SIGMA_THRESHOLD,
    MLFLOW_EXPERIMENT,
    MLFLOW_URI,
    TARGET_LOCATIONS,
)

DATA_RAW_DIR:   Path = Path("include/data/raw")
DRIFT_DATA_DIR: Path = Path("include/data/drift")
_MIN_REFERENCE_ROWS: int = 24


def _load_pm25_for_dates(dates: list[datetime]) -> pd.DataFrame:
    """Concat raw pm25_{d}.csv files for the dates that exist; drop NaN pm25."""


def _compute_location_drift(
    reference: pd.Series, recent: pd.Series
) -> dict[str, Any]:
    """Return {reference_mean, reference_std, recent_mean,
       n_reference, n_recent, mean_shift_sigma, drifted, inconclusive}."""


def compute_drift_verdicts(ds: str) -> dict[str, Any]:
    """Build the full drift dict for one ds (the JSON written to disk)."""


def log_drift_to_mlflow(verdicts: dict[str, Any], ds: str) -> str | None:
    """Best-effort: open one MLflow run drift_{ds}; log params + metrics;
       return run_id or None on failure / when AIRALERT_SKIP_MLFLOW is set."""


def drift_check_task(ds: str) -> str:
    """Entry point. Compute verdicts, log MLflow, write drift_{ds}.json,
       return absolute path string."""
```

Behavior contracts:

- `drift_check_task(ds)`:
  - Validates `ds` matches `YYYY-MM-DD`.
  - Calls `compute_drift_verdicts(ds)`.
  - Calls `log_drift_to_mlflow(verdicts, ds)` (best-effort).
  - Writes `DRIFT_DATA_DIR / f"drift_{ds}.json"`; creates parent dir.
  - Returns the absolute path string.
  - Idempotency note: the **DAG task** wrapping this function does the
    file-exists short-circuit, mirroring how `fetch_air_quality` and
    `engineer_features` do it today. `drift_check_task` itself always
    recomputes when called.
- `_load_pm25_for_dates` returns an empty DataFrame on no-files-found
  rather than raising — the sparse-window guard inside
  `_compute_location_drift` converts that into `inconclusive = True`.
- `compute_drift_verdicts` raises `FileNotFoundError` only when the recent
  file (`pm25_{ds}.csv`) is missing — that is a contract violation
  upstream, not a drift-check problem.

### 3. `dags/airalert_dag.py` (revisions)

Three changes:

1. **Add `DRIFT_DATA_DIR = Path("include/data/drift")`** alongside the
   other path constants near the top of the module.

2. **Insert a `check_drift` task** between `engineer_features` and
   `retrain_model`:

   ```python
   @task
   def check_drift(features_path: str) -> str:
       """
       Compute per-location PM2.5 drift verdicts for `ds` and write them
       to include/data/drift/drift_{ds}.json.

       Args:
           features_path: Upstream XCom path string from engineer_features.
               Used only to enforce DAG ordering — drift reads raw pm25,
               not the engineered features CSV.

       Returns:
           Absolute path string to include/data/drift/drift_{ds}.json.

       Raises:
           FileNotFoundError: if today's raw file
               include/data/raw/pm25_{ds}.csv is missing.
       """
       ctx = get_current_context()
       ds = ctx["ds"]
       output_path = DRIFT_DATA_DIR / f"drift_{ds}.json"

       if output_path.exists():
           return str(output_path)

       from include.src.drift import drift_check_task
       return drift_check_task(ds=ds)
   ```

3. **Update `_per_location_decisions` and `retrain_model`** to consume the
   drift JSON:

   - `_per_location_decisions(ds)` becomes
     `_per_location_decisions(ds, drift_verdicts: dict[str, bool])`.
   - The new precedence rule (rule 4 above) is inserted between bootstrap
     and the F1 check.
   - `retrain_model` reads the drift path from XCom, parses the JSON,
     builds `drift_verdicts = {loc: per_location[loc]["drifted"] for loc in TARGET_LOCATIONS}`,
     and passes it into `_per_location_decisions`.
   - The retrained-vs-skipped logging line gets the existing reason
     string, which now includes drift when drift was the cause.

4. **Wire the new 5-task chain at the bottom of `airalert_pipeline`:**

   ```python
   raw       = fetch_air_quality()
   validated = validate_schema(raw)
   features  = engineer_features(validated)
   drift     = check_drift(features)
   retrain_model(features, drift)
   ```

   `retrain_model`'s signature becomes
   `def retrain_model(features_path: str, drift_path: str) -> dict`.

### 4. `INTERFACE.md` (Decision 3 reasoning + Shared Constants + Change Log)

- **Decision 3 — Retraining trigger**: append a paragraph documenting the
  drift threshold and the consistency argument from this plan's "Decision"
  section. Do **not** rewrite the existing F1-based reasoning — drift is
  layered on top, not a replacement.
- **Shared Constants** table — add three rows:

  | Constant | Value | Used in |
  |---|---|---|
  | `DRIFT_SIGMA_THRESHOLD` | `2.0` | `include/src/drift.py`, `dags/airalert_dag.py`, `constants.py` |
  | `DRIFT_REFERENCE_DAYS` | `7` | `include/src/drift.py`, `constants.py` |
  | `DRIFT_RECENT_DAYS` | `1` | `include/src/drift.py`, `constants.py` |

- **Change Log** — add an entry:

  | Date | What changed | Why | Both partners agreed? |
  |---|---|---|---|
  | 2026-05-14 | Added `check_drift` task between `engineer_features` and `retrain_model`; per-location mean-shift sigma logged to MLflow; drift > 2.0σ added as a third retrain trigger in `_per_location_decisions` (alongside Monday backstop and F1 < 0.70). Source-of-truth design lives in `docs/drift_implementation_plan.md`. | W7A1 Part 2 requires drift detection between engineer and retrain, with mean shift logged to MLflow and a documented threshold consistent with the retraining trigger. | Yes |

## Files that do NOT change

- `include/src/ingest.py` — orthogonal.
- `include/src/transform.py` — orthogonal.
- `include/src/train.py` — `retrain_task` already accepts a
  `locations_to_retrain` list; the DAG keeps using that interface
  unchanged. Drift only edits the *decision* of what goes into that list.
- `include/src/serve.py` — out of scope for this PR (separate Part 3
  workstream).
- `app/dashboard.py` — out of scope for this PR (separate Part 4
  workstream).
- `scripts/seed_synthetic_raw.py`, `scripts/sample_openaq.py` — orthogonal.
- `tests/test_transform.py` — orthogonal.
- `docs/retrain_trigger_implementation_plan.md` — the original Decision 3
  plan stays as historical record; this drift plan extends it.

## Test scenarios

| Scenario | Setup | Expected |
|---|---|---|
| **Bootstrap (no raw history)** | Only today's `pm25_{ds}.csv` exists; no `pm25_{<ds}.csv` files for prior days | All locations: `n_reference = 0`, `inconclusive = true`, `drifted = false`. JSON written. `_per_location_decisions` falls through to its existing bootstrap rule and retrains anyway. |
| **All quiet weekday** | Reference window present; recent_mean within ±1σ of reference_mean for all 3 locations | `global_drifted = false`; `drifted = false` per location. `_per_location_decisions` retrain set comes solely from the F1 rule. |
| **Drift in one location only** | smithfield recent_mean is 3.5σ above its reference_mean; other two within ±0.5σ | `drift[smithfield].drifted = true`, others false. `global_drifted = true`. smithfield gets retrained even if its prior F1 ≥ 0.70; others follow the existing F1 rule. |
| **Monday + drift** | `ds.weekday() == 0` AND drift in all 3 locations | All 3 retrain. `retrain_decisions[loc].reason` shows the Monday reason (precedence rule 1 wins). Drift verdict still written and logged to MLflow. |
| **Sparse recent window** | Today's raw file has < 6 rows (sensor outage early in the day) for one location | That location's drift verdict is `inconclusive = true`, `drifted = false`. F1 rule still applies. |
| **Zero-std reference** | All reference pm25 values identical for one location | `sigma = 0`, `inconclusive = true`, `drifted = false`. No divide-by-zero crash. |
| **MLflow unreachable** | `MLFLOW_URI` server down | JSON still written; warning logged; task succeeds; downstream `retrain_model` consumes the JSON normally. |
| **`AIRALERT_SKIP_MLFLOW=1`** | Env flag set | Same as MLflow unreachable but no warning needed — informational log. |
| **Idempotent rerun** | Clear Airflow task state; `drift_{ds}.json` already on disk | `check_drift` task short-circuits, returns cached path. No recompute, no new MLflow run. |

## Rubric impact (W7A1)

| W7A1 rubric criterion | Impact |
|---|---|
| Drift check task between `engineer_features` and `retrain_model` | ✓ `check_drift` is the new 4th task in the 5-task chain |
| Compare recent window to reference distribution from training | ✓ Reference = 7-day raw window, matches the upstream `features.py` history window |
| Log `mean_shift_sigma` and boolean `drifted` flag to MLflow | ✓ `mean_shift_sigma_<location>` and `drifted_<location>` plus `global_drifted` logged under run `drift_{ds}` |
| Drift threshold documented in INTERFACE.md under Decision 3 | ✓ Decision 3 reasoning paragraph + Shared Constants row |
| Threshold consistent with retraining trigger | ✓ Drift is a leading indicator (2σ on input distribution); F1 < 0.70 is a lagging indicator (model outcome); both feed the same per-location retrain decision |
| All 5 tasks must go green in sequence | ✓ Drift is unconditional — no short-circuit task means no `skipped` (yellow) states |

## Rollback

A single revert of the migration commit restores the W6 4-task chain.
The three new constants in `constants.py` are dead-code-tolerant — leaving
them defined after a rollback breaks nothing. `include/data/drift/` files
on disk are harmless once the DAG no longer reads them; the directory can
be deleted at any time.
