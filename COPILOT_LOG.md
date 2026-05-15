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

## Entry 7 — QE — 2026-05-14
**Module:** `include/src/train.py` (promotion block + module-level logger), `INTERFACE.md` (Decision 7 calibration append, Decision 8 full write-up, two Change Log rows). Branch: `feat/dashboard`.

**Prompt sent to Claude:**

> Implement the W7A1 dashboard foundation: the `train.py` Production
> promotion fix AND the Decision 7 + Decision 8 INTERFACE.md polish.
> Follow the strict outlines at
> `docs/serve_production_promotion_plan.md` and
> `docs/phase_2_interface_md_patch.md` exactly — those documents are
> the source of truth for every code block, every paragraph of prose,
> the test scenarios, and the cross-review checklist coverage.
>
> Scope of this PR is **the train.py promotion + INTERFACE.md polish
> only.** Do not start the dashboard (Phase 3 lives in Entry 8), do
> not touch `serve.py`, do not extend Contract 4, do not compute the
> naive baseline, and do not write the final PR description. Those
> are separate W7A1 phases.
>
> The two files that change in this PR — and only these two:
>
> 1. **`include/src/train.py`** — apply both edits from §"Files
>    that change" §1 of `docs/serve_production_promotion_plan.md`:
>    - **1a.** Move `logger = logging.getLogger(__name__)` to module
>      top so `log_run_to_mlflow` and `retrain_task` share one
>      logger. Remove the duplicate definition inside `retrain_task`.
>    - **1b.** Add the Production promotion block to
>      `log_run_to_mlflow` immediately after the existing
>      `mlflow.sklearn.log_model(...)` call. Use the lazy import
>      pattern (`from mlflow.tracking import MlflowClient` inside
>      the function, not at module top). Wrap in try/except so
>      registry hiccups log a warning but never break the training
>      run. Match the best-effort message style of the existing
>      MLflow warning in `retrain_task`.
>
> 2. **`INTERFACE.md`** — apply two patches:
>    - **2a.** Apply all three blocks from
>      `docs/phase_2_interface_md_patch.md`: append the calibration
>      paragraph to Decision 7 reasoning, replace Decision 8
>      reasoning wholesale with the Next.js + recent-pattern
>      write-up, and append the 2026-05-14 Decision 7+8 Change Log
>      row.
>    - **2b.** Append the 2026-05-14 Change Log row from §"Files
>      that change" §2 of `docs/serve_production_promotion_plan.md`
>      (the train.py promotion row). Place it below the Phase 2
>      row from 2a.
>    - Delete `docs/phase_2_interface_md_patch.md` in the same
>      commit — it is a staging doc that should not survive past the
>      patch being applied.
>
> Do not modify any other file. Do not touch `ingest.py`,
> `transform.py`, `serve.py`, `drift.py`, `constants.py`, the DAG,
> the contracts (Contracts 1/2/3/4 are unchanged), the existing
> Decisions 1–6, tests, README, setup guides, or scripts. Do not
> introduce new dependencies.
>
> Conventions from `.github/copilot-instructions.md` apply: type-
> hinted signatures, Args/Returns/Raises docstrings on every new or
> modified function, `pathlib.Path` for any new file paths, best-
> effort MLflow handling honoring `AIRALERT_SKIP_MLFLOW`.
>
> After implementation, the file set must satisfy every row of the
> §"Test scenarios" and §"Rubric impact" tables in the promotion
> plan. Run `python -m py_compile include/src/train.py` to confirm
> the file parses cleanly.

**Summary:** [to be filled in after implementation]

---

## Entry 8 — QE + GJ — 2026-05-14
**Module:** `app/dashboard/` (Next.js project skeleton + lib functions, sub-phases 3a–3b). Branch: `feat/dashboard`.

> **Note (revised 2026-05-14):** Entry 8 originally covered the entire
> dashboard implementation. After sub-phases 3a (project skeleton) and
> 3b (lib functions: `readRawCsv.ts`, `featurePrep.ts`,
> `plainLanguage.ts`, `api.ts`, plus `constants.ts` and `types.ts`)
> shipped, the remaining UI work (sub-phases 3c API routes, 3d
> components, 3e page composition) was split into Entry 9 below so the
> visual design decisions agreed on after sub-phase 3b — the
> three-color verdict strip, glyph reinforcement, plain-language
> headline grouping — could be captured in their own dedicated UI
> spec (`docs/dashboard_ui_spec.md`) and the prompt grader would have
> a single self-contained reference for the UI surface.
>
> Entry 8 above remains the source-of-truth prompt for what already
> shipped (skeleton + lib). Entry 9 below is the source-of-truth
> prompt for what ships next (API routes + components + composition).

**Prompt sent to Claude:**

> Build the AirAlert dashboard at `app/dashboard/` as a Next.js +
> React + Tailwind project (W7A1 Part 4). Follow the strict outline
> at `docs/dashboard_implementation_plan.md` exactly — that document
> is the source of truth for the directory layout, every API route
> contract, the feature-prep algorithm, the UI flow, the plain-
> language headline logic, the trend chart spec, the constants
> mirror, and the cross-review checklist coverage.
>
> Pre-requisites for this prompt (must be merged on `feat/dashboard`
> before this work starts):
> - Entry 7 (Phase 1a + Phase 2) is committed: `train.py` promotes
>   newly registered model versions to MLflow's Production stage,
>   AND `INTERFACE.md` has the finalized Decision 7 calibration
>   paragraph and Decision 8 full write-up. The dashboard
>   implementation reads from `INTERFACE.md` to know what `is_unsafe`
>   and `unsafe_probability` actually mean and where the user-
>   visible high/medium/low buckets come from.
> - Drift detection commits are merged into `feat/dashboard` (already
>   done via the `git merge feature/drift-detection` step).
>
> Scope of this PR is **the dashboard implementation only.** Do not
> touch `ingest.py`, `transform.py`, `train.py` (Phase 1a already
> shipped in Entry 7), `drift.py`, `constants.py`, the DAG, or
> `serve.py`. `serve.py` is Gracelyn's file and stays exactly as
> she wrote it — the dashboard renders against the W6 `/health`
> three-field response shape (`status`, `model_name`, `stage`) and
> POSTs to `/predict` per Contract 4 unchanged.
>
> The files that change in this PR — and only these:
>
> 1. **`app/dashboard/`** — new Next.js project per §"Files that
>    change" §1 of `docs/dashboard_implementation_plan.md`.
>    Bootstrap with `create-next-app`, TypeScript + Tailwind, app
>    router, no src dir, no import alias. Implement every component,
>    every API route, every lib file in the directory tree the plan
>    documents. Use the exact dependency list from the plan's
>    `package.json` block — do not add new packages without a
>    written reason in the PR description.
>
> 2. **`app/dashboard/lib/constants.ts`** — mirror of the subset of
>    `include/src/constants.py` listed in §"Constants kept in sync"
>    of the plan. Add a header comment naming the Python file as the
>    source of truth and instructing future readers to update both
>    copies together.
>
> 3. **`INTERFACE.md`** — add ONE Phase-3 Change Log entry per
>    §"Files that change" §3 of the plan. The Decision 7 and
>    Decision 8 reasoning text MUST NOT be edited in this PR — that
>    work was done in Entry 7. Touching it here would create a merge
>    conflict and confuse the cross-review reviewer.
>
> Do not modify any other file. Conventions from
> `.github/copilot-instructions.md` apply to the Python side; the
> TypeScript side follows Next.js + Tailwind community conventions
> (functional components with TS, no class components; no inline
> styles, Tailwind classes; named exports for components; one
> component per file).
>
> Three specific design points the plan calls out that need to be
> implemented carefully:
>
> - **The browser never talks to FastAPI directly.** All three
>   routes under `app/dashboard/app/api/` (`health`, `predict`,
>   `features`) are the only thing that talks to FastAPI or to the
>   filesystem. The browser side only ever fetches
>   `/api/{health,predict,features}` — never `localhost:8000`
>   directly. This is why we do NOT add CORS middleware to
>   `serve.py`.
>
> - **The plain-language headline is not optional.** Implement the
>   `plainLanguageHeadline` function from §"Plain-language headline
>   logic" of the plan precisely — group consecutive unsafe hours
>   into ranges, name the location in the sentence, produce a
>   recommendation ("indoor recess" / "outdoor activities should be
>   fine"). The W7A1 rubric is explicit that "`is_unsafe: 1` is not
>   sufficient." High/medium/low confidence buckets must match
>   Decision 7's thresholds (≥0.70 / ≥0.40 / <0.40).
>
> - **The recent-pattern feature prep follows Decision 8 exactly.**
>   Implement the algorithm from §"Feature-prep algorithm" of the
>   plan: actual-or-pattern fallback per lag hour, hour-of-day mean
>   for future dates, `inconclusive` flag when fewer than 7
>   observations are available for the target hour. The lookup
>   window is `REFERENCE_WINDOW_DAYS = 14` days of raw history.
>
> After implementation, the project must satisfy every row of the
> §"Test scenarios" and §"Rubric impact" tables in the plan. The
> final smoke test must include: cold start with all three services
> running (Airflow producing data, FastAPI on :8000, Next.js on
> :3000) plus making at least one prediction through the UI for a
> future date and confirming the plain-language headline renders
> sensibly.

**Summary:** [to be filled in after implementation]

---

## Entry 9 — QE + GJ — 2026-05-14
**Module:** `app/dashboard/app/api/`, `app/dashboard/components/`, `app/dashboard/app/page.tsx`, `INTERFACE.md` (Phase 3 Change Log row). Branch: `feat/dashboard`.

**Prompt sent to Claude:**

> Build the AirAlert dashboard UI surface (W7A1 Part 4 — sub-phases
> 3c, 3d, and 3e on top of the skeleton + lib that already shipped
> on `feat/dashboard`). Follow the strict outlines at
> **`docs/dashboard_ui_spec.md`** (visual + interaction surface) and
> **`docs/dashboard_implementation_plan.md`** (architecture, API
> contracts, feature-prep algorithm). The UI spec is the source of
> truth for what the user sees and how they interact with it; the
> implementation plan is the source of truth for how the dashboard
> is technically structured. Where the two overlap, the UI spec wins
> on visual decisions.
>
> Pre-requisites already on this branch (no need to re-implement):
> - `app/dashboard/` Next.js project bootstrapped — `package.json`,
>   `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`,
>   `next.config.mjs`, `.eslintrc.json`, `.gitignore`,
>   `.env.local.example`, `app/layout.tsx`, `app/globals.css`,
>   `app/page.tsx` (placeholder), `README.md`.
> - `app/dashboard/lib/` populated — `constants.ts`, `types.ts`,
>   `readRawCsv.ts`, `featurePrep.ts`, `plainLanguage.ts`, `api.ts`.
> - Phase 1a (train.py Production promotion) and Phase 2 (Decision
>   7 calibration paragraph + Decision 8 full write-up) are merged
>   on this branch already.
>
> Scope of this PR is **the API routes, the UI components, and the
> page composition only.** Do not re-bootstrap the project, do not
> touch the lib files, do not touch `serve.py` (Gracelyn's file —
> the W6 `/health` three-field shape is what we consume), do not
> touch `ingest.py`, `transform.py`, `train.py`, `drift.py`,
> `constants.py`, the DAG, the contracts, the existing Decisions
> 1–8, tests, README, setup guides, or scripts.
>
> The files that change in this PR — and only these:
>
> 1. **`app/dashboard/app/api/health/route.ts`** — GET that proxies
>    `${FASTAPI_URL}/health`. On any error from FastAPI, return HTTP
>    503 with a JSON body matching `HealthResponse` shape but with
>    `status: "fastapi_unreachable"`. Pass through the W6 three-field
>    response (`status`, `model_name`, `stage`) unchanged on success.
>
> 2. **`app/dashboard/app/api/predict/route.ts`** — POST that proxies
>    `${FASTAPI_URL}/predict` with the request body. Validate the
>    incoming body matches `PredictRequest` (TypeScript runtime
>    check via a small zod-free hand-rolled guard — keep deps minimal).
>    Pass through Contract 4 (`is_unsafe`, `unsafe_probability`,
>    `threshold_used`) unchanged.
>
> 3. **`app/dashboard/app/api/features/route.ts`** — GET that wraps
>    `buildFeatureRows` from `lib/featurePrep.ts`. Query params:
>    `location` (one of the three LocationKey values), `from` (ISO
>    8601 UTC datetime), `hours` (1–24). Return a `FeaturesResponse`
>    per Decision 8 — one row per hour with `features`,
>    `data_source`, `fallback_used`, plus the aggregate
>    `reference_window_days` and `any_fallback_used`.
>
> 4. **`app/dashboard/app/api/trend/route.ts`** — GET that wraps
>    `buildTrendSeries` from `lib/featurePrep.ts`. Query params:
>    `location`, `days` (default 7, max 30). Return `{location,
>    days, points: TrendPoint[]}` where each point has
>    `{timestamp, pm25, is_unsafe}`.
>
> 5. **`app/dashboard/components/`** — implement every component
>    documented in §"Components" of `docs/dashboard_ui_spec.md`,
>    one component per file, named exports:
>    - `HealthBadge.tsx` — three-state pill, 30s polling.
>    - `LocationPicker.tsx` — three-button segmented control with
>      radiogroup semantics.
>    - `DateTimePicker.tsx` — date input with `minDate` / `maxDate`
>      bounds per the UI spec.
>    - `HourRangeSlider.tsx` — dual-thumb slider; thumbs cannot cross;
>      min span 1, max span 12.
>    - `PredictButton.tsx` — primary button with the three states
>      (default / loading / disabled) from the UI spec.
>    - `PredictionCard.tsx` — narrative box with the four-row
>      layout (label / headline / recommendation / confidence). Reads
>      `state` and renders `empty | loading | result | error`.
>    - `HourlyPredictionStrip.tsx` — the 11-cell strip per
>      §"HourlyPredictionStrip" of the UI spec. Five visual states
>      from `cellState()` in `lib/plainLanguage.ts`; glyphs from
>      Tabler outline (or inline SVGs if Tabler isn't readily
>      available — match the icon names called out in the spec);
>      ⓘ fallback indicator on cells with `fallback_used: true`;
>      hover/tap popover with the raw probability and metadata.
>    - `TrendChart.tsx` — Recharts `LineChart` with the 35.4
>      reference line, the above-threshold red recoloring, axis
>      labels, tooltips, loading skeleton, error card, accessible
>      `aria-label`.
>    - `DataSourceLegend.tsx` — small footer line with the
>      dynamic copy from §"DataSourceLegend" of the UI spec.
>    - `ui/Button.tsx`, `ui/Card.tsx`, `ui/Select.tsx` — small
>      primitives used by the above. Functional, no animations
>      beyond hover/focus state.
>
> 6. **`app/dashboard/app/page.tsx`** — replace the placeholder
>    scaffold with the full composition documented in §"Page
>    anatomy" of the UI spec. Manages the top-level state machine
>    (`INITIAL → READY → PREDICTING → HAS_RESULT | ERROR`). Reads
>    `getHealth`, `predictRange`, `getTrend` from `lib/api.ts`.
>    Default values: location=red_butte, date=tomorrow, hours=8-18.
>    Responsive grid per the spec.
>
> 7. **`INTERFACE.md`** — append ONE Phase-3 Change Log row stating
>    that the dashboard implementation landed. Do not modify any
>    Decision in this PR.
>
> Conventions (must follow):
> - TypeScript functional components with named exports. No class
>   components.
> - One component per file. File names match the exported component.
> - Tailwind utility classes only — no inline `style={{}}` except
>   for Recharts internals that require it.
> - Use the color tokens from the UI spec §"Color tokens" — pull from
>   `tailwind.config.ts` for `safe-*`, `caution-*`, `unsafe-*`.
> - `aria-label` on every glyph-only interactive element.
> - `role="status"` + `aria-live="polite"` on the result regions
>   (HealthBadge, PredictionCard result state).
> - Loading states everywhere — never render a flash of empty
>   content while data is in flight.
> - No raw `unsafe_probability` numbers in the UI outside the cell
>   popover. The user sees high/medium/low buckets per Decision 7.
>
> The browser MUST never call `localhost:8000` directly. Every
> outbound request from the browser goes through one of the four
> `app/api/*` routes. This is the architectural commitment in
> Decision 8 that lets `serve.py` skip CORS middleware.
>
> After implementation, the project must satisfy every row of
> §"Acceptance criteria" in `docs/dashboard_ui_spec.md`. Run
> `npm run typecheck` and `npm run lint` from `app/dashboard/` and
> ensure both pass (lint may warn but must not error). Then run
> `npm run dev` and walk the §"Acceptance criteria" checklist with
> FastAPI live on `:8000`.

**Summary:** [to be filled in after implementation]
