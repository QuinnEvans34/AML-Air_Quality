# Decision 3 — Retrain Trigger Implementation Plan

**Status:** source of truth for the migration that wires Decision 3 into the
DAG. This document describes the agreed design; the code changes follow it.

## Decision (from `INTERFACE.md`)

Retrain a per-location model when its rolling F1 on the unsafe class falls
below **0.70**, OR unconditionally on the first run of each Monday at
06:00 UTC. Decision is **per location** — if Smithfield's model degrades but
Red Butte and Ledges are still healthy, only Smithfield is retrained.

## Why this is a code change

The W5 draft committed to the trigger but the DAG retrains all three
locations on every run. To honor the contract, `retrain_model` needs to:

1. Read each location's previous F1 from the most recent metrics file.
2. Decide per location whether to retrain.
3. Pass the list of locations needing retrain into `retrain_task`.
4. Carry forward the existing model and metrics for skipped locations.
5. Always write `metrics_{ds}.json` so every date has documentation.

---

## Architecture

The decision lives **inside** `retrain_model`, not as a separate
short-circuit task. Reason: the W6A1 rubric requires "all 4 tasks must go
green in sequence" for the screenshot. A short-circuit task would mark
`retrain_model` as `skipped` (yellow) on no-retrain days. With the decision
internal, the task is always green — it just does less work some days.

```
fetch_air_quality → validate_schema → engineer_features → retrain_model
                                                            │
                                            ┌── per-location decisions ──┐
                                            │                             │
                                       retrain list                 keep list
                                            │                             │
                                       train.retrain_task          load existing bundle
                                            │                             │
                                            └─── merge ───┐    ┌──────────┘
                                                         │    │
                                                  bundle + per-loc metrics
                                                         │
                                                metrics_{ds}.json + latest_model.pkl
                                                         │
                                                       XCom
```

---

## Decision logic (per location)

For each `location_key` in `TARGET_LOCATIONS`, compute `(retrain, reason)`:

| Condition | Decision | Reason string |
|---|---|---|
| `ds.weekday() == 0` (Monday) | retrain | `"weekly Monday backstop"` |
| no `metrics_*.json` on disk | retrain | `"bootstrap (no prior metrics)"` |
| no entry for this location in latest `per_location` | retrain | `"bootstrap (no prior {loc} metrics)"` |
| latest `per_location[loc].f1 < 0.70` | retrain | `"prior f1={x:.3f} < threshold 0.70"` |
| otherwise | skip | `"prior f1={x:.3f} ≥ threshold 0.70"` |

---

## Metrics file structure

Every daily run writes `include/models/metrics_{ds}.json` with the
following shape (top-level keys remain rubric-compliant):

```json
{
  "f1": 0.85,
  "baseline_f1": 0.0,
  "accuracy": 0.92,
  "precision": 0.88,
  "recall": 0.85,
  "false_negatives": 5,
  "true_positives": 30,
  "per_location": {
    "red_butte":  {"f1": 0.92, "baseline_f1": 0.0, "accuracy": 0.95, "precision": 0.91, "recall": 0.93, "false_negatives": 1, "true_positives": 19},
    "smithfield": {"f1": 0.65, "baseline_f1": 0.0, "accuracy": 0.85, "precision": 0.62, "recall": 0.68, "false_negatives": 3, "true_positives": 7},
    "ledges":     {"f1": 0.98, "baseline_f1": 0.0, "accuracy": 0.99, "precision": 0.98, "recall": 0.98, "false_negatives": 1, "true_positives": 4}
  },
  "retrain_history": {
    "red_butte":  "2026-05-04",
    "smithfield": "2026-05-09",
    "ledges":     "2026-05-04"
  },
  "retrain_decisions": {
    "red_butte":  {"retrained": false, "reason": "prior f1=0.920 ≥ threshold 0.70"},
    "smithfield": {"retrained": true,  "reason": "prior f1=0.650 < threshold 0.70"},
    "ledges":     {"retrained": false, "reason": "prior f1=0.980 ≥ threshold 0.70"}
  }
}
```

Top-level `f1` / `baseline_f1` / `accuracy` / `precision` / `recall` are the
**aggregate across all three locations** — what the W6 rubric requires in
XCom. They're computed as the float mean over `per_location` for the
float keys and the sum for `false_negatives` / `true_positives`.

`retrain_history` tracks when each location's model was last refreshed
(`ds` of the last successful retrain). `retrain_decisions` is the audit
trail for *this* run's decisions.

On a no-retrain day for a given location:
- the location's `per_location[loc]` entry is **carried forward verbatim**
  from the previous metrics file
- the location's `retrain_history[loc]` carries forward unchanged
- the location's `retrain_decisions[loc]` shows `retrained: false`

On a retrain day for a given location:
- the location's `per_location[loc]` entry is computed fresh from the new model
- the location's `retrain_history[loc]` is set to today's `ds`
- the location's `retrain_decisions[loc]` shows `retrained: true`

---

## Bundle (`latest_model.pkl`) semantics

`latest_model.pkl` contains a dict `{location_key: fitted_estimator}` with
exactly the three `TARGET_LOCATIONS` keys. After every run:

- For locations that retrained: the dict entry points to the freshly fitted
  classifier.
- For locations that skipped: the dict entry is the estimator from the
  prior bundle, preserved unchanged.

Per-location date-stamped pickles (`{location_key}_{ds}.pkl`) are written
**only** for locations that retrained — so the file system shows exactly
which days each location got a fresh model.

---

## Files that change

### 1. `include/src/constants.py` (additive)

Two new constants for Decision 3:

```python
# Decision 3 — retraining trigger.
# Retrain a per-location model when its rolling F1 on the unsafe class
# drops below this floor. Below 0.70, recall typically falls under 0.50,
# meaning we miss more than half the unsafe hours — at that point a
# sensitive-group resident is better off ignoring our dashboard than
# trusting it, so the model has stopped serving its public-health purpose.
F1_RETRAIN_THRESHOLD: float = 0.70

# Weekly retrain backstop: Python weekday() index for Monday.
WEEKLY_RETRAIN_WEEKDAY: int = 0
```

### 2. `include/src/train.py` (signature + body)

`retrain_task` gets a new optional argument:

```python
def retrain_task(
    features_path: str,
    ds: str,
    locations_to_retrain: list[str] | None = None,
) -> dict:
    """
    Train per-location classifiers for the requested locations.

    Args:
        features_path: Path string to a Contract-2 features CSV.
        ds:            YYYY-MM-DD execution date string.
        locations_to_retrain: List of TARGET_LOCATIONS keys to retrain.
            None (default) retrains all three (legacy behavior).
            [] retrains none — useful only for upstream callers that have
            already decided no retrain is needed; this still requires a
            previous bundle on disk and previous per-location metrics, or
            it raises.
    """
```

Behavior:
- When `locations_to_retrain` is `None`: identical to current behavior
  (train all three).
- Otherwise: load the existing bundle and the previous metrics file. For
  each location:
  - In `locations_to_retrain` → train fresh, get new metrics.
  - Not in `locations_to_retrain` → reuse model from existing bundle and
    metrics from previous metrics file.
- Save merged bundle (new + preserved entries).
- Write date-stamped per-location pickles **only** for retrained locations.
- Run MLflow logging (best-effort) **only** for retrained locations.
- Return aggregated metrics with `per_location` nested dict and
  `retrain_history`.

Bootstrap edge case: if a location is in the keep-list but has no entry in
the existing bundle (or no entry in previous per-location metrics), force
its retrain — log a warning. This protects against half-corrupt state.

### 3. `dags/airalert_dag.py` (revised `retrain_model` task)

Add two helpers (module-level, above the DAG):

```python
def _read_latest_metrics() -> dict | None:
    files = sorted(MODELS_DIR.glob("metrics_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def _per_location_decisions(ds: str) -> dict[str, tuple[bool, str]]:
    """Apply Decision 3 per location. Returns {loc_key: (retrain, reason)}."""
    from include.src.constants import (
        F1_RETRAIN_THRESHOLD, TARGET_LOCATIONS, WEEKLY_RETRAIN_WEEKDAY,
    )
    is_monday = datetime.fromisoformat(ds).weekday() == WEEKLY_RETRAIN_WEEKDAY
    prev = _read_latest_metrics() or {}
    prev_per_loc = prev.get("per_location", {})

    decisions: dict[str, tuple[bool, str]] = {}
    for loc_key in TARGET_LOCATIONS:
        if is_monday:
            decisions[loc_key] = (True, "weekly Monday backstop")
            continue
        if not prev_per_loc:
            decisions[loc_key] = (True, "bootstrap (no prior metrics)")
            continue
        if loc_key not in prev_per_loc:
            decisions[loc_key] = (True, f"bootstrap (no prior {loc_key} metrics)")
            continue
        f1 = float(prev_per_loc[loc_key].get("f1", 0.0))
        if f1 < F1_RETRAIN_THRESHOLD:
            decisions[loc_key] = (True, f"prior f1={f1:.3f} < threshold {F1_RETRAIN_THRESHOLD}")
        else:
            decisions[loc_key] = (False, f"prior f1={f1:.3f} ≥ threshold {F1_RETRAIN_THRESHOLD}")
    return decisions
```

`retrain_model` body becomes:

```python
ds = get_current_context()["ds"]
metrics_path = MODELS_DIR / f"metrics_{ds}.json"
bundle_path  = MODELS_DIR / "latest_model.pkl"

# Idempotency: if today already wrote both, return cached
if metrics_path.exists() and bundle_path.exists():
    return json.loads(metrics_path.read_text())

decisions = _per_location_decisions(ds)
locations_to_retrain = [loc for loc, (r, _) in decisions.items() if r]

import logging
logger = logging.getLogger("airflow.task")
logger.info("Decision 3 — retrain plan for %s:", ds)
for loc, (r, reason) in decisions.items():
    logger.info("  %s: %s (%s)", loc, "retrain" if r else "skip", reason)

from include.src.train import retrain_task
metrics = retrain_task(
    features_path=features_path,
    ds=ds,
    locations_to_retrain=locations_to_retrain,
)

# Audit trail of this run's decisions
metrics["retrain_decisions"] = {
    loc: {"retrained": r, "reason": reason}
    for loc, (r, reason) in decisions.items()
}

MODELS_DIR.mkdir(parents=True, exist_ok=True)
metrics_path.write_text(json.dumps(metrics))
return metrics
```

### 4. `INTERFACE.md` (Shared Constants + Change Log)

Add to **Shared Constants** table:

| Constant | Value | Used in |
|---|---|---|
| `F1_RETRAIN_THRESHOLD` | `0.70` | `dags/airalert_dag.py`, `constants.py` |
| `WEEKLY_RETRAIN_WEEKDAY` | `0` (Monday) | `dags/airalert_dag.py`, `constants.py` |

Add to **Change Log**:

| Date | What changed | Why | Both partners agreed? |
|---|---|---|---|
| 2026-05-09 | Decision 3 wired into DAG: `retrain_model` evaluates per-location F1 against 0.70 floor; Monday 06:00 UTC is unconditional weekly backstop; non-retrained locations carry forward existing model and metrics. | W5 committed to the trigger but DAG always retrained. W6 rubric explicitly requires F1-on-unsafe-class metric tied to public-health cost. | Yes |

---

## Files that do NOT change

- `include/src/ingest.py` — orthogonal
- `include/src/transform.py` — orthogonal
- `scripts/seed_synthetic_raw.py` — orthogonal
- `tests/test_transform.py` — orthogonal

---

## Test scenarios

| Scenario | Setup | Expected |
|---|---|---|
| **Bootstrap** | No `metrics_*.json` exists | All 3 locations retrain. Metrics file written with `retrain_decisions` showing all 3 retrained. |
| **Monday backstop** | latest `per_location[*].f1 = 0.95`, `ds = 2026-05-11` (Monday) | All 3 retrain regardless of F1. |
| **All healthy weekday** | `per_location[*].f1 = 0.85`, `ds = Tuesday` | Zero locations retrain. Metrics file written, all `per_location` entries copied forward, `retrain_history` unchanged for all. `latest_model.pkl` byte-identical to yesterday. |
| **One degraded weekday** | `smithfield.f1 = 0.65`, others 0.90, `ds = Tuesday` | Only smithfield retrains. Bundle has fresh smithfield estimator + preserved red_butte and ledges estimators. `retrain_history[smithfield] = ds`, others unchanged. |
| **Idempotent rerun** | clear task state, today's `metrics_{ds}.json` and `latest_model.pkl` both present | Task short-circuits, returns cached metrics. No decision logic invoked, no writes. |

---

## Rubric impact

| W6 rubric criterion | Impact |
|---|---|
| Pipeline execution — all 4 tasks green | ✓ `retrain_model` is always green (decision is internal, not branching) |
| Contract adherence | ✓ Contracts 1, 2, 3 unchanged; XCom still has top-level `f1`, `baseline_f1`, `accuracy`, `precision`, `recall` |
| Decision 3 reasoning | ✓ INTERFACE.md has 0.70 / public-health framing; this PR makes the code agree |
| Cross-review quality | unaffected |

---

## Rollback

A single revert of the migration commit restores always-retrain behavior.
The two new constants in `constants.py` are dead-code-tolerant — leaving
them defined after a rollback breaks nothing.
