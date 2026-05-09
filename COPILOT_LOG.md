## Entries

## Entry 1 — QE — 2026-05-04
**Module:** `dags/airalert_dag.py`

**Prompt sent to Claude:**

> Implement the file `dags/airalert_dag.py` for the AirAlert pipeline.
> Follow the strict outline at `docs/dag_implementation_plan.md` exactly —
> that document is the source of truth for the file's structure, every
> task's signature, every constraint from the Week 6 assignment Part 2,
> and the cross-review checklist coverage.
>
> The DAG must contain four `@task` functions (`fetch_air_quality`,
> `validate_schema`, `engineer_features`, `retrain_model`) wired in a
> linear chain inside a `@dag`-decorated function `airalert_pipeline`.
> Use the TaskFlow API (no `PythonOperator`), pull `ds` from
> `get_current_context()["ds"]`, include idempotency file-existence
> checks where applicable, raise meaningful exceptions on failure, and
> use `pathlib.Path` for all file paths under `include/data/`.
>
> Do not modify any other file in the repo. Do not implement
> `ingest_task`, `transform_task`, or `retrain_task` — those live in
> their pipeline scripts and are imported lazily inside each task.

**Summary:** Created full dag file, with 4 major functions. Calls ingest data, then validates schema, builds the features, and then triggers a re-train on our respective re-train metrics (any false negatives)


## Entry 3 — QE — 2026-05-04
**Module:** `include/src/train.py` (commit 1 of 2 — signatures + docstrings)

**Prompt sent to Claude:**

> Create `include/src/train.py` for the AirAlert pipeline. Follow the
> strict outline at `docs/train_implementation_plan.md` exactly — that
> document is the source of truth for the file's structure, every
> function signature, every per-function docstring, the module
> docstring, and the rules about not changing any other file.
>
> For this commit, produce ONLY the module docstring (per §5),
> imports (per §6), module-level constants (per §7), and the nine
> typed function signatures with full Args/Returns/Raises docstrings
> (per §8.1–§8.9 of the plan). **Function bodies must be docstring-only
> — no `pass`, no `raise`, no implementation logic.** The body of each
> function is just the docstring; everything else gets filled in in a
> follow-up commit.
>
> The entry-point function is `retrain_task(features_path: str, ds: str)
> -> dict`. The DAG (`dags/airalert_dag.py`) already imports and calls
> it with that signature — do not change it.
>
> Reference Decisions 3, 6, and 7 from `INTERFACE.md` in the module
> docstring as instructed in §5 of the plan. Use `FEATURE_COLS` from
> Contract 3 (declared at module level per §7), with `class_weight =
> "balanced"`, chronological 80/20 split per location, and per-location
> MLflow registration under `MODEL_NAME_TEMPLATE.format(location=...)`.
>
> Do not modify any other file in the repo. Do not implement any
> function bodies. Do not change `include/src/constants.py`,
> `INTERFACE.md`, the DAG, ingest.py, or anything outside
> `include/src/train.py`.

**Summary:** created train.py file, followed specifications inside our train_implementation_plan.md file (outlined the full code implementation) this contained only the doc strings, per assignment outline, full file with functioning code will be implemented in next prompt/commit.

---

## Entry 4 — QE — 2026-05-05
**Module:** `include/src/train.py` (commit 2 of 2 — function bodies)

**Prompt sent to Claude:**

> Fill in the function bodies of `include/src/train.py`. Follow §8 of
> `docs/train_implementation_plan.md` verbatim — each subsection
> (8.1 through 8.9) specifies exactly what the corresponding function's
> body must do.
>
> Do not change any function signature, parameter type, return type, or
> docstring already present in the file. Do not add new module-level
> functions. Do not modify any file other than `include/src/train.py`.
> Use the lazy-import pattern from §6.2 — sklearn, mlflow, joblib
> imports go inside the functions that use them, not at module top.
>
> After implementation, the file must satisfy every item in the §11
> cross-review checklist and the §12 acceptance criteria of the plan.

**Summary:** filled in code following the outline of md file, and doc strings. Very basic prompt, all the documentation was inside the MD, created all our metrics when it comes to training our ML model, used logical regression, calculated basic accuracy metrics such as F1, precision and accuracy.

---

## Entry 2 — QE — 2026-05-04
**Module:** `include/src/ingest.py`

**Prompt sent to Claude:**

> Implement the function bodies in `include/src/ingest.py` for the
> AirAlert pipeline. Follow the strict outline at
> `docs/ingest_implementation_plan.md` exactly — that document is the
> source of truth for what each body must do, plus the rules about not
> changing any signature, docstring, or other file in the repo.
>
> The module already contains a complete module docstring and eight
> typed function signatures with Args / Returns / Raises docstrings.
> Your job is to fill in the function bodies so each function does
> exactly what its docstring promises, and so the implementation is
> consistent with `INTERFACE.md` Contract 1, Decision 2, and Decision 5.
>
> Use the existing `scripts/sample_openaq.py` as a reference for the
> five OpenAQ API call chain functions (`_build_headers`,
> `get_location_metadata`, `find_pm25_sensor_id`, `fetch_hourly_pm25`,
> `parse_to_dataframe`) — the patterns there are correct, just adapted
> to the new function names and the strict-typed signatures already
> present in `ingest.py`.
>
> The three orchestration functions (`fetch_all_locations`,
> `save_raw_pm25`, `ingest_task`) must be implemented per
> §6.6 / §6.7 / §6.8 of the implementation plan. `fetch_all_locations`
> must raise `ValueError` if any value in `TARGET_LOCATIONS` is `None`,
> and `save_raw_pm25` must validate Contract 1 schema before writing.
>
> Do not modify any other file in the repo. Do not change any function
> signature, parameter type, return type, or docstring. Do not add new
> module-level functions. Do not change `scripts/sample_openaq.py`,
> `include/src/constants.py`, `INTERFACE.md`, the DAG, or anything
> outside `include/src/ingest.py` itself.

**Summary:** This prompt included the full implementation of our ingest.py file, we had already filled out the doc strings, and corresponding MD file, so this acutally implemented the code necessary for it to run. 
