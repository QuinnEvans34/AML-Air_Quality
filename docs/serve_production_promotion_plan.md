# Train.py Production Promotion Plan (W7A1 Part 1 dependency)

**Status:** source of truth for the migration that wires MLflow
Production-stage promotion into `train.py`. This document describes
the agreed design; the code changes follow it.

**Scope note (2026-05-14 revision):** an earlier draft of this plan
also proposed changes inside `serve.py` (version-aware cache, version
numbers in `/health`). Those changes were reviewed, judged scope-creep
for the W7A1 deadline, and dropped. The serve.py file is owned by
Gracelyn and remains untouched in this PR — its existing pickle-mtime
cache strategy and the W6 `/health` response shape (`status`,
`model_name`, `stage`) stay as written. The model_versions /
registry-cache improvements are recorded as candidate follow-ups in
the final PR description's "What you would improve with more time"
section. They are not in scope here.

## Problem statement

The serving layer (`include/src/serve.py`) loads models via the URI
`models:/AirAlert_<location>/Production` at startup, but `train.py`
never promotes any model version to the `Production` stage. The
W6-era `mlflow.sklearn.log_model(..., registered_model_name=...)` call
creates new versions only — every version registered to date sits at
the default `None` stage. As a result:

1. Cold-starting the FastAPI server (`uvicorn serve:app --port 8000`)
   raises `mlflow.exceptions.RestException: RESOURCE_DOES_NOT_EXIST: No
   versions of model 'AirAlert_<location>' are at stage 'Production'`
   inside `_load_registry_models`.
2. W7A1 Part 5 — End-to-End Verification step 3 ("Confirm the Production
   model in MLflow Registry is accessible") cannot pass.
3. The dashboard cannot make a prediction because `/predict` depends
   on the lifespan loader succeeding.

The fix is entirely within `train.py`. Once that promotion happens,
the existing serve.py code resolves `models:/.../Production` cleanly.

## Decision

**`train.py` promotes every retrained location to Production after
logging.** Inside `log_run_to_mlflow`, after the new version is
registered, look up that version's number, transition it to
`Production`, and archive the prior `Production` version if one
existed. This is best-effort — wrapped in try/except with a warning,
matching the existing pattern in `retrain_task` where MLflow
exceptions are caught and logged but never raised.

## Architecture

```
                ┌─────── train.py ────────────────────────────────────┐
                │                                                      │
       per-loc training run                                            │
                │                                                      │
                ▼                                                      │
       mlflow.sklearn.log_model(..., registered_model_name="AirAlert_<loc>")
                │                                                      │
                ▼                                                      │
       MlflowClient.get_latest_versions(name, stages=["None"])         │
                │                                                      │
                ▼                                                      │
       MlflowClient.transition_model_version_stage(                    │
           name, new_version, stage="Production",                      │
           archive_existing_versions=True                              │
       )                                                                │
                │                                                      │
                └──────────────────────────────────────────────────────┘
                                  │
                                  ▼
              MLflow Registry: AirAlert_<loc> @ Production
                                  │
                                  ▼
                ┌─────── serve.py (UNCHANGED) ────────────────────────┐
                │                                                      │
       _load_registry_models()                                         │
         for each loc:                                                 │
           uri = "models:/AirAlert_<loc>/Production"                   │
           model = mlflow.sklearn.load_model(uri)                      │
         -> cache (models dict, bundle_mtime)                          │
                                                                       │
       refresh_model_cache():                                          │
         pickle mtime comparison (Decision 8 — unchanged)              │
                │                                                      │
                ▼                                                      │
       /health  -> {status, model_name, stage}  (W6 shape, unchanged)  │
       /predict -> unchanged                                           │
                └──────────────────────────────────────────────────────┘
```

Three things to note:

- **Best-effort by design.** If `transition_model_version_stage` fails
  (network blip, registry-permission error, etc.), the new version is
  still registered but stays at stage `None`. The serving layer will
  continue to serve the previous Production version (if any). The DAG
  task does not retry — a future Monday backstop run will retry
  promotion.
- **No XCom changes.** Promotion happens inside the existing MLflow
  best-effort block in `retrain_task`; the metrics dict shape is
  unchanged. Drift JSON shape, retrain decisions, and Contract 3 stay
  the same.
- **The pickle fallback survives.** `include/models/latest_model.pkl`
  is still written by `save_model_bundle`. If MLflow is fully down,
  any future direct-pickle loader still finds the file. The Production
  promotion fix is additive — it doesn't remove any existing path.

## Files that change

### 1. `include/src/train.py`

Two edits:

**1a — Promote `logger` to module level.** Today `logger =
logging.getLogger(__name__)` is defined inside `retrain_task` only.
`log_run_to_mlflow` (a sibling function) needs to use it too. Move
the definition to module top:

```python
import logging
logger = logging.getLogger(__name__)
```

And remove the duplicate local definition inside `retrain_task`.

**1b — Add the promotion block to `log_run_to_mlflow`.** Immediately
after the existing `mlflow.sklearn.log_model(...)` call, before the
function returns:

```python
# Promote the newly registered version to Production and archive the
# prior Production version. Best-effort — wrapped in try/except so
# registry hiccups never break the training run. Matches the
# best-effort pattern used elsewhere in this module.
try:
    from mlflow.tracking import MlflowClient
    client = MlflowClient(tracking_uri=MLFLOW_URI)
    latest = client.get_latest_versions(registered_name, stages=["None"])
    if latest:
        new_version = latest[0].version
        client.transition_model_version_stage(
            name=registered_name,
            version=new_version,
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info(
            "Promoted %s version %s to Production",
            registered_name, new_version,
        )
except Exception as exc:  # noqa: BLE001 — best-effort
    logger.warning(
        "Failed to promote %s to Production (%s: %s); "
        "model is registered but stage remains None",
        registered_name, type(exc).__name__, exc,
    )
```

The function's return value (the `run_id`) is unchanged.

### 2. `INTERFACE.md` (Change Log only)

One new row:

| Date | What changed | Why | Both partners agreed? |
|---|---|---|---|
| 2026-05-14 | `train.py.log_run_to_mlflow` now promotes each newly registered model version to MLflow's Production stage and archives the prior Production version (best-effort, warning on failure). Module-level `logger` introduced so `log_run_to_mlflow` and `retrain_task` share one logger. No other module touched in this PR. | Cold-starting `uvicorn serve:app` previously failed because no version was ever at the Production stage; W7A1 Part 5 end-to-end verification step 3 requires Production-stage models. | Yes |

No Decision is added or modified in this PR. Decision 3 already
documents the F1-based retrain trigger and the W7A1 drift trigger;
the promotion is a wiring fix, not a decision change.

## Files that do NOT change

- `include/src/serve.py` — Gracelyn's file. Existing pickle-mtime
  cache and W6 `/health` response shape are correct as written.
- `include/src/ingest.py`, `include/src/transform.py`,
  `include/src/drift.py`, `include/src/constants.py` — orthogonal.
- `dags/airalert_dag.py` — orthogonal. Continues calling
  `retrain_task` with the same signature; promotion happens inside
  the existing MLflow best-effort block.
- All Decisions in `INTERFACE.md` — orthogonal.

## Test scenarios

| Scenario | Setup | Expected |
|---|---|---|
| **First-time promotion** | No prior versions registered for any location | `retrain_task` registers v1 for each loc; `transition_model_version_stage(..., archive_existing_versions=True)` runs successfully; `mlflow models list` shows each `AirAlert_<loc>` v1 at stage Production. |
| **Subsequent promotion** | One prior version at Production per loc; new retrain registers v2 | After `retrain_task`, v1 is at Archived and v2 is at Production for each retrained loc; non-retrained locs keep their existing Production version. |
| **Promotion failure** | MlflowClient.transition_model_version_stage raises | Warning logged with exception details; `retrain_task` still returns successfully; new version exists at stage None; existing Production version (if any) is unchanged. |
| **Serve.py cold start with Production version present** | `mlflow models list` shows AirAlert_<loc> v1 at Production for all three | `uvicorn serve:app` starts cleanly; `/health` returns the W6 response shape `{status: "ok", model_name: "...", stage: "Production"}`. |
| **Serve.py cold start with NO Production version** | `mlflow models list` shows everything at None | `RuntimeError("Failed to load registry model models:/.../Production")` raised inside `_load_registry_models`; lifespan startup fails loudly. This is the desired behavior — the dashboard should not connect to a stale or empty serving layer. |
| **AIRALERT_SKIP_MLFLOW for tests** | Env flag set | `log_run_to_mlflow` short-circuits as it does today; no promotion attempted; no warning needed. |

## Rubric impact (W7A1)

| W7A1 rubric criterion | Impact |
|---|---|
| Part 3 — FastAPI app loads Production model at startup | ✓ Loader now actually succeeds because there's something at Production stage |
| Part 5 step 3 — Production model in MLflow Registry is accessible | ✓ Promotion happens inside every retrain |
| Part 5 step 4 — POST to /predict returns valid response | ✓ unchanged, but cold-start no longer blocks it |
| /health returns model name, stage, status indicator | ✓ W6 shape preserved; serve.py untouched |

## Rollback

A single revert of the migration commit removes the promotion call.
Models registered between the merge and the revert remain at
Production stage in the registry — harmless, can be manually archived
via MLflow UI if desired.
