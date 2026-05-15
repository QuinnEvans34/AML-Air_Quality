# `serve.py` First-Run Graceful Boot — Handoff to Gracelyn

**From:** Quinn (QE)
**To:** Gracelyn (GJ)
**Status:** ~10-line change in `serve.py`. Required before W7A1 submission so the dashboard demo doesn't depend on operational ordering.

## The gap

Today, `serve.py`'s lifespan handler calls `_load_registry_models`,
which raises `RuntimeError("Failed to load registry model
models:/AirAlert_<loc>/Production")` whenever any of the three
Production-stage versions doesn't exist yet. That hard-fail propagates
out of the `lifespan` async context and uvicorn refuses to start the
server.

This is a problem in two real scenarios:

1. **First-time setup.** Brand new laptop, fresh `mlflow.db`, no DAG
   runs yet. Before the DAG fires for the first time, uvicorn can't
   boot. There's no way to demo the dashboard's UI shell (controls,
   trend chart, health badge) in this state.
2. **Mid-experiment cleanup.** Anyone runs `rm -rf mlflow.db
   mlartifacts` and then forgets to retrain before booting uvicorn —
   uvicorn fails until they remember.

The Phase 1a promotion fix in `train.py` solves the "no Production
stage" problem from the training side, but only AFTER a training run
happens. For the bootstrap moment between "no models" and "first DAG
completed," `serve.py` needs to boot gracefully.

## The fix

Change `refresh_model_cache(force=True)` to catch the `RuntimeError`
from `_load_registry_models` and start the cache empty. The rest of
the file already handles `_STATE.models = {}` correctly:

- `/health` raises 503 with "Model cache is empty" (line ~539 today).
- `/predict` raises 503 with "No cached model is loaded for location
  '...'" (line ~447 today).
- `refresh_model_cache(force=False)` runs on every `/predict` and
  will re-try the registry load — so the moment a DAG run completes
  and promotes a Production version, the next prediction request
  picks it up. No uvicorn restart needed.

Here's the exact diff to apply in `refresh_model_cache`:

```python
def refresh_model_cache(force: bool = False) -> None:
    """..."""

    # When forced, we skip the mtime check and reload immediately. This is
    # necessary during lifespan startup so models are ready for requests.
    if force:
        try:
            _STATE.models = _load_registry_models()
        except RuntimeError as exc:
            # First-run / freshly-wiped-registry case. We deliberately
            # boot in a DEGRADED state instead of failing the lifespan
            # so the dashboard UI shell still renders. /health will
            # return 503 ("Model cache is empty") and /predict will
            # return 503 until a DAG run promotes the first version.
            # The non-force refresh_model_cache calls in the predict
            # path will keep retrying the registry load, so as soon as
            # a Production-stage model exists, subsequent /predict
            # requests will load it without uvicorn restart.
            import logging
            logging.getLogger(__name__).warning(
                "Booting in DEGRADED mode — no Production-stage models "
                "in registry yet (%s). /health and /predict will return "
                "503 until the DAG runs and promotes a version.",
                exc,
            )
            _STATE.models = {}
        _STATE.bundle_mtime = _current_bundle_mtime()
        return
    # ... rest of function unchanged
```

That's it. One try/except block. Nothing else in `serve.py` changes.

## Test scenarios

| Scenario | Expected behavior |
|---|---|
| **Fresh registry, no models** | uvicorn boots, warning logged, `/health` returns 503 with "Model cache is empty", `/predict` returns 503 |
| **One Production version exists** | uvicorn boots, `/health` returns 200, `/predict` works for all locations |
| **Partial: 2 of 3 locations promoted** | `_load_registry_models` raises on the missing one → caught → `_STATE.models = {}` → entire serving layer degrades (acceptable for the project's scale; safer than serving partial coverage) |
| **DAG promotes after uvicorn already running** | Next `/predict` request triggers `refresh_model_cache(force=False)` which loads the new model; from that point on, the cache works normally |

## Why this is the right shape

- **No new endpoints, no new code paths in predict.** The empty-cache
  case was already handled — we just stop blocking the lifespan on it.
- **No long-running thread, no polling loop, no background workers.**
  The next inbound `/predict` is what triggers the registry re-check,
  which keeps the change small and predictable.
- **Doesn't change the W6 `/health` response shape.** Contract 4
  stays as-is.
- **Mirrors the best-effort pattern the rest of the codebase uses.**
  `train.py.log_run_to_mlflow` already swallows MLflow failures with a
  warning. The promotion block in Phase 1a follows the same pattern.
  This is consistent.

## How to apply

Open a small PR titled something like `serve: boot in degraded mode
when no Production model exists`. Apply the patch above to
`refresh_model_cache`. Add a Change Log row to `INTERFACE.md`:

| Date | What changed | Why | Both partners agreed? |
|---|---|---|---|
| 2026-05-15 | `serve.py.refresh_model_cache(force=True)` catches the `RuntimeError` from `_load_registry_models` so uvicorn boots in degraded mode when no Production-stage models exist yet. `/health` still returns 503 in that state; the next `/predict` retries the registry load automatically. | First-run setup and post-cleanup states were leaving uvicorn unable to boot; the dashboard's UI shell needs to render even before the first DAG run completes. | Yes |

No tests need updating; the existing `_STATE.models == {}` path is
already exercised in the W6 tests.
