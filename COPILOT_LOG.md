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

---

## Entry 5 — GJ — 2026-05-14
**Module:** `include/src/serve.py`

**Prompt sent to Claude:**

> Build out `include/src/serve.py` as the FastAPI serving layer for AirAlert. Start with a module docstring, then add documented Pydantic request/response schemas, a cache/state class, helper functions, startup lifespan logic, and the `/health` and `/predict` endpoints. Keep the file thin, cache models in memory, use an mtime-based refresh check, and add comments explaining the what and why for each section.

**Summary:** Created the serving layer skeleton and then filled it into a thin FastAPI service for the dashboard.
Added the module docstring, request/response schemas, cache state, helper functions, startup lifespan, and both endpoints.
Used logistic regression probabilities directly as the dashboard certainty score per Decision 7.
Kept model loading cached in memory and added an mtime-based refresh check so the app does not reload on every request.
Added comments throughout to explain why each piece exists and kept the API aligned with the serving contract.

---

## Entry 6 — QE — 2026-05-14
**Module:** `include/src/drift.py` (new), `dags/airalert_dag.py` (revised), `include/src/constants.py` (additive), `INTERFACE.md` (Decision 3 + Shared Constants + Change Log)

**Prompt sent to Claude:**

> Implement drift detection for the AirAlert pipeline (W7A1 Part 2).
> Follow the strict outline at `docs/drift_implementation_plan.md`
> exactly — that document is the source of truth for the file structure,
> every function signature, every module-level constant, the per-location
> decision precedence table, the drift verdict JSON shape, the MLflow run
> shape, the test scenarios, and the cross-review checklist coverage.
>
> Scope of this PR is **drift detection only**. Do not touch `serve.py`,
> do not create `app/dashboard.py`, do not edit Decision 7 or Decision 8
> reasoning, do not compute the naive baseline F1, and do not write the
> final PR description. Those are separate W7A1 workstreams.
>
> The four files that change in this PR — and only these four:
>
> 1. **`include/src/constants.py`** — add the three new constants
>    (`DRIFT_SIGMA_THRESHOLD = 2.0`, `DRIFT_REFERENCE_DAYS = 7`,
>    `DRIFT_RECENT_DAYS = 1`) per §"Files that change" §1 of the plan.
>    Match the inline-comment style of `F1_RETRAIN_THRESHOLD` and
>    `WEEKLY_RETRAIN_WEEKDAY` already in that file.
>
> 2. **`include/src/drift.py`** — new module per §"Files that change"
>    §2 of the plan. Module docstring (cite Decision 3 and W7A1 Part 2),
>    lazy imports for `mlflow` and `numpy` where it makes sense (match
>    the lazy-import pattern from `train.py`), and the five functions
>    listed in the plan with full Args/Returns/Raises docstrings. The
>    public entry point is `drift_check_task(ds: str) -> str`, which is
>    what the DAG imports.
>
> 3. **`dags/airalert_dag.py`** — revisions per §"Files that change"
>    §3 of the plan:
>    - Add `DRIFT_DATA_DIR = Path("include/data/drift")` near the other
>      path constants.
>    - Insert the new `check_drift` task between `engineer_features`
>      and `retrain_model`. Use the file-exists idempotency pattern
>      that `fetch_air_quality` and `engineer_features` already use.
>    - Update `_per_location_decisions` to accept the new
>      `drift_verdicts: dict[str, bool]` argument and apply precedence
>      rule 4 from the plan (drift > 2.0σ → retrain) between bootstrap
>      and the F1 < 0.70 check.
>    - Update `retrain_model` to take `drift_path: str` as a second
>      argument, parse the drift JSON, build the verdict dict, and
>      pass it into `_per_location_decisions`. Preserve every existing
>      W6 idempotency, bootstrap-fallback, MLflow best-effort, and
>      audit-trail guarantee — drift only adds a new reason string to
>      `retrain_decisions[loc].reason`; it does not change the metrics
>      dict shape.
>    - Wire the 5-task chain at the bottom exactly as shown in the
>      plan's Architecture diagram.
>
> 4. **`INTERFACE.md`** — Decision 3 reasoning gets an appended
>    paragraph documenting the 2σ threshold and the leading-vs-lagging
>    consistency argument (do not rewrite or remove the existing F1
>    reasoning — drift is layered on top of it). Shared Constants table
>    gets the three new rows from §"Files that change" §4 of the plan.
>    Change Log gets the 2026-05-14 entry. Do not edit Decision 7 or
>    Decision 8 in this PR.
>
> Do not modify any other file in the repo. Do not edit `ingest.py`,
> `transform.py`, `train.py`, `serve.py`, the contracts, the
> retrain_trigger_implementation_plan.md doc, the tests, the README,
> the setup guides, or any scripts. Do not introduce new dependencies
> beyond `numpy` and `mlflow` (both already in `requirements.txt`).
>
> Constraints from the project conventions in
> `.github/copilot-instructions.md` apply: every function gets a type-
> hinted signature and Args/Returns/Raises docstring; the DAG task
> returns a file path string, never a DataFrame; `pathlib.Path` for all
> file paths; meaningful exceptions on failure; MLflow logging is
> best-effort and honors `AIRALERT_SKIP_MLFLOW`.
>
> After implementation, the file set must satisfy every row of the
> §"Test scenarios" and §"Rubric impact" tables in the plan.

**Summary:** [to be filled in after implementation]

---

## Entry 7 — GJ — 2026-05-05
**Module:** `include/src/transform.py` (commit 1 of 2 — signatures + docstrings)

**Prompt sent to Claude:**

> Create `include/src/transform.py` for the AirAlert pipeline. Follow the
> strict outline at `docs/transform_implementation_plan.md` exactly — that
> document is the source of truth for the module's public API, the required
> lag and rolling-window semantics, and the contract with `ingest.py` and
> `train.py` (Contract 1 and Contract 2). Produce the module docstring,
> imports, module-level constants, and the typed function signatures with
> full Args/Returns/Raises docstrings. Do not implement function bodies in
> this commit; function bodies will be added in a follow-up commit.

**Summary:** Added the `transform.py` module scaffold: module-level
documentation, typed function signatures (`validation_helper`, `lag_feature`,
`rolling_feature`, `date_feature`, `_gather_raw_history`, and `build_features`),
and contract-oriented docstrings. This commit intentionally left bodies for a
later implementation pass to preserve incremental reviewability.

---

## Entry 8 — GJ — 2026-05-09
**Module:** `include/src/transform.py` (commit 2 of 2 — function bodies)

**Prompt sent to Claude:**

> Fill in the function bodies of `include/src/transform.py` per
> `docs/transform_implementation_plan.md`. Implement validation of the raw
> schema, UTC timestamp parsing, per-`location_id` sorting, lag features
> (1h, 3h, 24h), 3-hour rolling mean/std excluding the current hour, temporal
> features (`hour_of_day`, `day_of_week`, `month_of_year`, `is_weekend`),
> `is_unsafe` target creation using the `UNSAFE_THRESHOLD`, and the final
> contract-limited CSV output. Use `pathlib.Path` for paths and raise
> meaningful `ValueError`/`FileNotFoundError` where appropriate. Preserve the
> DAG-friendly pattern of returning an output file path string.

**Summary:** Implemented the feature-engineering pipeline for AirAlert.
Included robust schema validation, per-location lag/rolling computations that
exclude current-hour leakage, temporal feature extraction, target creation,
and CSV export to `include/data/features/features_{ds}.csv`. The helpers were
designed to be testable and follow the project's docstring-and-typehint
conventions.

---

## Entry 9 — GJ — 2026-05-15
**Module:** `scripts/run_app.ps1` (new), `scripts/bootstrap_train.py` (patch)

**Summary:** Created a Windows PowerShell launcher (`scripts/run_app.ps1`) for the full AirAlert stack. The launcher starts MLflow (port 5001), FastAPI (port 8000), and Next.js dashboard (port 3000) in a single command. It automatically detects the latest raw PM2.5 data, seeds synthetic data on first run, bootstraps models if needed, and opens the dashboard URL in the default browser once all services are ready. Includes process monitoring and graceful cleanup on Ctrl+C. Also patched `scripts/bootstrap_train.py` line 124 to change Unicode arrow `→` to ASCII `->` for Windows console compatibility.




## Entry 10 — QE — 2026-05-16
## End of project reflection:

The most useful interaction that I had through out the process of developing this project was very recent. Today, I did a full audit of the code, and had claude write out a full summary and audit based on the assignment outline. Here I was able to pick up a few problems that I wanted to fix before our final submission, and I was also able to feel more confident about my final submission. Knowing what was working, and what needed to be done allowed me to really fine tune the final submission. I found a few details that I wanted to fix, such as changing the time zone to MST instead of UTC in the dashboard UI. We trained all the models on UTC, but this did not make sense in the context of our dashboard, and would not be useful to our shareholders. Because of this, I was able to make final fixes, and really clean up the UI and UX. The most suprising failure stems from the final accuracy that our models ended up getting. The past week we were sitting in the mid to low 90s, and now we have been sitting in the mid to low 80s. This is because I was giving the model more access to our data, and having it make more predictions. I thought we had a better accuracy than we really did, just because the scope of the predictions were so small. If it made 4 accurate predicitions, then we would end up with a really high F1, but predicting a full day brought our accuracy down. I am happy with the final accuracy scores, and think that using a logical regression was the best choice, because it is very explainable. Our stakeholders are schools, they will be basing if students should be outside for recess and after school activities. Having clear explainability to a non technical audience will be very important for our dashboard, so I beleive the final product ended up working great for our specific use case. I ended up playing with a few different models just to see what they looked like, a hist gradient boost model had much higher accuracy, being high 90s, but is not as clear in the predictions that it makes. So I think the explainability and clarity that comes from our dashboard out weighs this. If I were to do this project again, I would have tried to add more locations, we ended up having 3, but I think having more locations would have made our case a little stronger, and would have given us more data to look through. I really could not find any clear patterns, working with small amounts of data, and I think it would have been helpful to be able to look into patterns in different parts of the state to see if they line up with each other, or if certain parts of the state have much safer or unsafe air quality. Overall, I am really happy with this project, I think our final dashboard turned out really good, and I had a great experience going through all the decision making. I also think working with a team mate ended up making this project flow much better. I was able to bounch ideas of Gracelyn, and see what she thought about each of the decisions we made. This made me much more confident in the final choices we made, because I was able to really walk through each step of the planning process.


