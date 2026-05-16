# ML Accuracy Audit — Hunting Every Plausible F1 Lever

**Status:** independent second-opinion audit, written to be handed to
Codex (or any external model) so it can attack accuracy from a fresh
angle. Treats the entire pipeline — ingestion → transform → drift →
train → serve — as one optimization surface.

**Current baseline (post-StandardScaler + 60-day window):**

| Location | F1 (unsafe) | Precision | Recall | TP | FN |
|---|---|---|---|---|---|
| red_butte | 0.897 | 0.812 | 1.000 | 13 | 0 |
| smithfield | 0.816 | 0.769 | 0.870 | 20 | 3 |
| ledges | 0.759 | 0.733 | 0.786 | 11 | 3 |
| **aggregate** | **0.824** | **0.772** | **0.885** | — | — |
| naive baseline (always safe) | 0.000 | 0.000 | 0.000 | 0 | — |

**Goal:** push aggregate F1 above 0.85, ideally above 0.90, without
breaking any architectural contract or violating Decision 7's
"logistic regression" commitment.

---

## How the pipeline currently works (the surface to optimize)

1. **`ingest.py`** — OpenAQ v3 hourly endpoint, three Utah locations,
   one CSV per day under `include/data/raw/pm25_{ds}.csv`. NaN pm25
   values dropped at ingest.

2. **`transform.py`** — concatenates the last 60 days of raw CSVs,
   computes 9 engineered features per (location_id, hour):
   - `pm25_lag_1h`, `pm25_lag_3h`, `pm25_lag_24h`
   - `pm25_rolling_mean_3h`, `pm25_rolling_std_3h` (excludes current hour)
   - `hour_of_day`, `day_of_week`, `month_of_year`, `is_weekend`
   - Target: `is_unsafe = (pm25 > 35.4)`
   - Writes `include/data/features/features_{ds}.csv`.

3. **`drift.py`** — compares last 7 days raw vs last 24h raw per
   location, logs `mean_shift_sigma` + `drifted` to MLflow.

4. **`train.py`** — per location:
   - Chronological 80/20 split.
   - `Pipeline([StandardScaler, LogisticRegression(class_weight="balanced", max_iter=1000, random_state=0)])`.
   - Single-class fallback to `DummyClassifier` when `y_train.nunique() < 2`.
   - `predict()` uses sklearn's default 0.5 decision threshold.
   - Per-location pickle + MLflow registration + Production promotion.

5. **`serve.py`** — loads each location's Production model, calls
   `predict()` and `predict_proba()`, returns Contract 4 response.

---

## What's CHEAP to change (no contract amendment)

These are internal to train.py and don't touch Contracts 2 / 3 / 4 or
Decisions 4 / 6 / 7. Codex can try any of these without ripple
effects.

### 1. `LogisticRegressionCV` for C tuning

Current `LogisticRegression(C=1.0)` is sklearn's default. With our
~700 training rows per location, C is the single most under-explored
hyperparameter. Replace with:

```python
from sklearn.linear_model import LogisticRegressionCV
clf = LogisticRegressionCV(
    Cs=[0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0],
    cv=5,
    scoring="f1",          # optimize for the metric we report
    class_weight="balanced",
    max_iter=2000,
    random_state=0,
    n_jobs=-1,
)
```

Expected lift: **0.01–0.04 F1**. Free win on data where features have
mixed informativeness.

### 2. F1-optimal decision threshold (per location)

The default 0.5 threshold is wrong for class-imbalanced
`class_weight="balanced"` LR. Compute the F1-optimal threshold on a
held-out portion of training data and store it alongside the model:

```python
from sklearn.metrics import precision_recall_curve

# After fitting, on a held-out validation chunk
probs = pipeline.predict_proba(X_val)[:, 1]
precision, recall, thresholds = precision_recall_curve(y_val, probs)
f1s = 2 * precision * recall / (precision + recall + 1e-12)
best_threshold = thresholds[f1s[:-1].argmax()]
```

Store `best_threshold` as MLflow run param + alongside the bundle, so
serve.py can use it instead of 0.5. Expected lift: **0.02–0.06 F1**.

This requires a tiny serve.py change (one line: replace `predict()`
with `predict_proba() > threshold`) — that's Gracelyn's file, so it
goes in the post-submission handoff doc rather than this PR.
**Workaround for this PR only:** apply the threshold inside train.py
when computing `compute_metrics` so the reported F1 reflects the
optimal threshold even though serve.py still uses 0.5. Document the
gap clearly.

### 3. `CalibratedClassifierCV` wrapper

Wraps the LR pipeline to produce better-calibrated probabilities.
Doesn't directly improve F1 at the default threshold, but combined
with threshold tuning (item 2) it usually adds **0.01–0.03 F1**:

```python
from sklearn.calibration import CalibratedClassifierCV
base = Pipeline([("scaler", StandardScaler()),
                 ("lr", LogisticRegression(C=best_C, class_weight="balanced", ...))])
calibrated = CalibratedClassifierCV(base, method="sigmoid", cv=3)
calibrated.fit(X_train, y_train)
```

The output has `predict_proba` and `classes_` exactly like LR; serve.py
works unchanged.

### 4. L1 / ElasticNet penalty (with `saga` solver)

L1 induces feature sparsity — useful if some of the 9 features add
noise. ElasticNet (mix of L1 + L2) is the safer default. With only 9
features the lift is small but worth trying.

```python
clf = LogisticRegressionCV(
    Cs=[...], penalty="elasticnet", solver="saga",
    l1_ratios=[0.1, 0.3, 0.5, 0.7], cv=5, scoring="f1",
    class_weight="balanced", max_iter=4000, random_state=0,
)
```

Expected lift: **0.0–0.02 F1**. Lower priority than items 1+2.

### 5. SMOTE / class-balanced sampling

Replace `class_weight="balanced"` with explicit oversampling of the
minority class via `imbalanced-learn`'s SMOTE:

```python
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

pipe = ImbPipeline([
    ("scaler", StandardScaler()),
    ("smote", SMOTE(random_state=0)),
    ("clf", LogisticRegression(max_iter=2000, random_state=0)),
])
```

Expected lift: **-0.01 to +0.03 F1** — high variance, sometimes hurts
on imbalanced regression-style problems. **Worth trying once.**

### 6. Per-location hyperparameter search

Currently every location uses identical hyperparameters. Smithfield
and Ledges might want different `C` values. Item 1's
`LogisticRegressionCV` already does per-location tuning since it's
called inside the per-location loop. **Free with item 1.**

---

## What's MEDIUM cost (extend Contract 2 + Contract 3)

Adding features changes Contract 2 (transform.py output) and
Contract 3 (the columns serve.py expects). Both partners need to
agree; INTERFACE.md Change Log row required. Each addition needs:

- Update `FEATURE_COLS` in `include/src/constants.py`
- Update `FEATURE_COLS` in `include/src/train.py` (mirrored)
- Update `FEATURE_COLS` in `include/src/serve.py` (mirrored)
- Update `FEATURE_COLS` in `app/dashboard/lib/constants.ts` (mirrored)
- Update the feature-prep function in `app/dashboard/lib/featurePrep.ts`
- Update transform.py to compute the new feature
- Add the new column to Contract 2 in INTERFACE.md
- Add the new column to Contract 3 in INTERFACE.md
- Change Log row

### 7. Cyclical encoding of temporal features

The single highest-impact feature change. Current `hour_of_day=23` and
`hour_of_day=0` look ~maximally different to LR but are 1 hour apart.
Sin/cos encoding fixes this:

```python
df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)
df["dow_sin"]  = np.sin(2 * np.pi * df["day_of_week"] / 7)
df["dow_cos"]  = np.cos(2 * np.pi * df["day_of_week"] / 7)
df["month_sin"] = np.sin(2 * np.pi * df["month_of_year"] / 12)
df["month_cos"] = np.cos(2 * np.pi * df["month_of_year"] / 12)
```

Could either ADD these alongside the existing raw temporal features
or REPLACE the raw ones. For LR, replacing is usually better
(reduces collinearity). Expected lift: **0.03–0.06 F1**.

**Contract amendment scope.** Replacing means changing Contract 2's
9 columns to a different 12-column set. Adding means going from 9
to 15. Either way, INTERFACE.md needs an amendment.

### 8. More lag windows

```python
df["pm25_lag_6h"]  = location_groups["pm25"].shift(6)
df["pm25_lag_12h"] = location_groups["pm25"].shift(12)
df["pm25_lag_48h"] = location_groups["pm25"].shift(48)  # yesterday-ish
```

Pm25 has strong diurnal cycle, so lag_48h captures "same hour two
days ago" which differs from lag_24h's "same hour yesterday."
Expected lift: **0.01–0.03 F1**.

### 9. More rolling windows

```python
df["pm25_rolling_max_3h"]   = shifted.rolling(3).max()
df["pm25_rolling_mean_6h"]  = shifted.rolling(6).mean()
df["pm25_rolling_mean_24h"] = shifted.rolling(24).mean()
```

Rolling max catches inversion onsets (spike in recent hours).
Expected lift: **0.01–0.03 F1**.

### 10. Rate-of-change features

```python
df["pm25_rate_1h"] = df["pm25_lag_1h"] - df["pm25_lag_2h"]
df["pm25_rate_3h"] = df["pm25_lag_1h"] - df["pm25_lag_4h"]
```

These require pm25_lag_2h and pm25_lag_4h to exist (which they don't
currently). Expected lift: **0.01–0.03 F1**.

### 11. Interaction terms

`hour_of_day × pm25_lag_1h`, `is_weekend × pm25_lag_24h`, etc. LR
can't learn interactions natively, so engineering them as features
is the only way. Expected lift: **0.01–0.04 F1**, with risk of
overfitting on small training sets.

---

## What's EXPENSIVE (Decision 7 amendment)

Switching models. Decision 7 commits the project to Logistic
Regression. Amending it requires a paragraph in INTERFACE.md
explaining why, what changes, and what the user-facing impact is.

### 12. `HistGradientBoostingClassifier`

sklearn's native GBT, fast (no XGBoost dep), handles non-linearity
and feature interactions natively. Likely the single biggest possible
F1 lift on this data.

```python
from sklearn.ensemble import HistGradientBoostingClassifier
clf = HistGradientBoostingClassifier(
    max_iter=500, learning_rate=0.05, max_depth=4,
    early_stopping=True, validation_fraction=0.15,
    class_weight="balanced", random_state=0,
)
```

Expected lift: **0.05–0.12 F1**. With our positive-class rate ~10% and
~700 rows per location, this is likely well-suited.

**Contract impact:** Decision 7 amendment in INTERFACE.md. Calibration
note in Decision 7 needs updating (GBT's `predict_proba` is naturally
better-calibrated than LR's). Dashboard's calibration disclaimer
needs softening.

### 13. `RandomForestClassifier`

Less likely to outperform GBT but worth a fold of CV to confirm.

### 14. Ensemble (stack LR + GBT)

```python
from sklearn.ensemble import StackingClassifier
ensemble = StackingClassifier(
    estimators=[("lr", lr_pipeline), ("gbt", gbt_pipeline)],
    final_estimator=LogisticRegression(class_weight="balanced"),
    cv=5,
)
```

Captures both linear and non-linear signal. Expected lift over GBT
alone: **0.0–0.02 F1**, with significant complexity cost.

---

## Diagnostic — which features are actually doing work today?

Before optimizing, Codex should run a feature-importance diagnostic
on the current model to see which of the 9 features carry signal:

```python
# After fitting the StandardScaler+LR pipeline:
lr = pipeline.named_steps["classifier"]
print(dict(zip(FEATURE_COLS, lr.coef_[0])))
```

Or for a model-agnostic view:

```python
from sklearn.inspection import permutation_importance
imp = permutation_importance(pipeline, X_test, y_test,
                             n_repeats=20, random_state=0,
                             scoring="f1")
for col, mean in sorted(zip(FEATURE_COLS, imp.importances_mean), key=lambda x: -x[1]):
    print(f"  {col:22s}  {mean:+.4f}")
```

If one of the temporal features (e.g. `month_of_year`) shows ~0
importance, that's a hint the cyclical encoding isn't urgent. If
`pm25_lag_24h` dominates everything, lag_48h is unlikely to add
much. **Run this first, optimize second.**

---

## Recommended attack order for Codex

Rank-ordered by expected lift × cost:

| # | Change | Expected lift | Contract impact | Effort |
|---|---|---|---|---|
| 1 | `LogisticRegressionCV` for C tuning | +0.01 to +0.04 | None | ~30 min |
| 2 | F1-optimal threshold per location | +0.02 to +0.06 | Need internal-only validation; production threshold defer to GJ | ~45 min |
| 3 | Cyclical encoding (replace raw hour/dow/month) | +0.03 to +0.06 | Contract 2 + 3 amendment | ~90 min |
| 4 | `HistGradientBoostingClassifier` | +0.05 to +0.12 | **Decision 7 amendment** | ~60 min |
| 5 | More lag/rolling windows | +0.01 to +0.03 each | Contract 2 + 3 amendment | ~45 min each |
| 6 | `CalibratedClassifierCV` | +0.01 to +0.03 (with threshold tuning) | None | ~30 min |
| 7 | SMOTE | -0.01 to +0.03 | None (adds imbalanced-learn dep) | ~30 min |
| 8 | L1 / ElasticNet | +0.0 to +0.02 | None | ~20 min |
| 9 | Ensemble | +0.0 to +0.02 over GBT | Decision 7 amendment | ~60 min |

**Codex's safest aggressive bet:** items 1 + 2 + 3 stacked. Stays in
LR family (Decision 7 unchanged), can plausibly push F1 from 0.82 to
0.88–0.92.

**Codex's biggest swing:** item 4 alone (HistGBT). One amendment,
biggest expected lift.

---

## Validation methodology Codex must follow

For every change Codex tries:

1. **Hold the data window fixed.** Use `features_2026-05-15.csv` (the
   60-day window). Don't refetch ingest.
2. **Compare against the current baseline.** Aggregate F1 = 0.824.
3. **Per-location matters.** A change that lifts aggregate by 0.05 but
   tanks ledges by 0.20 is bad — the assignment's stakeholder cares
   about every location.
4. **Reproducibility.** Always pass `random_state=0` so re-runs match.
5. **Report both numbers.** Train-set F1 AND test-set F1. If
   train-test gap widens, the change is overfitting and should be
   rejected.
6. **Acceptance threshold.** Don't ship a change unless aggregate test
   F1 improves by ≥ 0.02 AND no location drops by more than 0.05.

---

## Guardrails — things Codex MUST NOT do

- ❌ Don't fetch new data via OpenAQ (rate limits + assignment scope).
- ❌ Don't change `is_unsafe = pm25 > 35.4` — that's the target.
- ❌ Don't use stratified shuffle split — Decision 4 commits to
  chronological splits to prevent target leakage.
- ❌ Don't change the per-location modeling structure — Decision 6
  commits to three independent models.
- ❌ Don't break serve.py's expectations: model must have
  `predict_proba` and `classes_=[0,1]`, regardless of the underlying
  estimator type.
- ❌ Don't break the dashboard's `lib/featurePrep.ts` — if Contract 3
  features change, both the Python side AND the TypeScript side need
  updating in the same PR.
- ❌ Don't add a new ML dependency without a one-line justification.
  `imbalanced-learn` and `xgboost` are common enough that the
  justification is just "needed for item 5 / item 12 of the audit."
- ❌ Don't disable the drift detection or single-class fallback —
  both are production-readiness features.

---

## Prompt for Codex

Paste this whole block into Codex (along with the audit doc as a
file attachment):

```
You are auditing an end-to-end ML pipeline for accuracy improvements.
The full design + every accuracy lever I want you to consider lives in
docs/ml_accuracy_audit.md. Read that file first.

Project context:
  - AirAlert is a PM2.5 unsafe-air predictor for three Utah K-5
    school sites.
  - Three per-location logistic regression models, currently F1 =
    0.824 aggregate (red_butte 0.897 / smithfield 0.816 /
    ledges 0.759) vs naive baseline F1 = 0.000.
  - Target metric: F1 on the unsafe class. Goal: aggregate F1 > 0.85,
    ideally > 0.90.
  - Decision 7 (INTERFACE.md) commits to logistic regression.
    Amending Decision 7 is allowed if a model change is the right
    call, but must include a paragraph in INTERFACE.md justifying
    the switch and updating the calibration narrative.

Your job:
  1. Run the feature-importance diagnostic from §"Diagnostic" of the
     audit doc to see which features actually carry signal in the
     current model. Print the per-location importance scores.
  2. Pick a strategy from §"Recommended attack order." I suggest you
     try the "safest aggressive bet" first (items 1 + 2 + 3 stacked
     — LogisticRegressionCV + F1-optimal threshold + cyclical
     temporal encoding) since it stays within Decision 7. If that
     stalls below 0.88 aggregate, escalate to item 4
     (HistGradientBoostingClassifier) and amend Decision 7.
  3. For every change, re-run the metrics and compare aggregate +
     per-location F1 against the baseline (0.824 / 0.897 / 0.816 /
     0.759). Accept the change only if it satisfies the §"Validation
     methodology" criteria in the audit doc.
  4. When Contract 2 / 3 (the 9-column feature schema) changes,
     update EVERY mirror simultaneously:
       - include/src/constants.py FEATURE_COLS
       - include/src/train.py FEATURE_COLS
       - include/src/serve.py FEATURE_COLS
       - app/dashboard/lib/constants.ts FEATURE_COLS
       - app/dashboard/lib/featurePrep.ts (compute the new features
         the same way transform.py does)
       - INTERFACE.md Contract 2 + Contract 3 columns + Change Log row
       - INTERFACE.md Decision 4 reasoning (the feature list lives
         there too)
  5. When Decision 7 changes (model swap), update:
       - include/src/train.py train_logistic_regression (rename or
         add a sibling function for the new estimator)
       - INTERFACE.md Decision 7 reasoning paragraph
       - INTERFACE.md Change Log row
       - Update Decision 7's calibration narrative IF the new
         model's predict_proba is better-calibrated (e.g. GBT).
  6. Use scripts/bootstrap_train.py to re-train end-to-end with your
     changes applied — that's the canonical training entry point
     locally. It uses the 60-day window via transform.py's
     _HISTORY_DAYS = 60.
  7. Document every change in COPILOT_LOG.md as a new entry. Include
     the prompt you were given, the changes you made, and the F1
     deltas you measured.

Hard guardrails (from §"Guardrails — things Codex MUST NOT do"):
  - No new ingest. No new OpenAQ calls.
  - No stratified shuffle split (Decision 4 violation).
  - No global model (Decision 6 violation).
  - serve.py must still work without modification — your trained
    estimator must expose predict, predict_proba, and classes_=[0,1].
  - The single-class DummyClassifier fallback in
    train_logistic_regression must continue to work (or be
    reimplemented if you swap models).
  - Drift detection (drift.py and the DAG's check_drift task) is
    untouched.

Deliverables:
  - A summary table at the end: change made, aggregate F1 before,
    aggregate F1 after, per-location F1 deltas, any negative
    side-effects observed.
  - The final improved model registered to MLflow at Production
    stage via the existing log_run_to_mlflow path.
  - A short README addition or PR description bullet describing
    what you did and why, in language a grader will understand.

Don't ship anything you haven't measured. Don't shortcut the
validation methodology even if a change "feels obvious."
```

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Codex amends Decision 7 to switch to GBT and the calibration narrative in INTERFACE.md becomes inconsistent | Medium | The Codex prompt explicitly requires updating Decision 7's calibration paragraph if the model changes |
| Codex adds features that break the dashboard's TypeScript mirror | High | The prompt enumerates every mirror file that must be updated atomically |
| Codex's improvements overfit the May-13 window and don't generalize | Medium | §"Validation methodology" item 5 requires reporting train-test gap |
| Codex pushes a change with -0.02 F1 because aggregate went up but ledges tanked | Low | §"Acceptance threshold" requires no location loses > 0.05 |
| Threshold tuning gets done in train.py but serve.py still uses 0.5 in production | High | The audit doc flags this explicitly; the fix is either (a) accept the gap and document it, or (b) write a serve_threshold_handoff.md for Gracelyn |
| Codex breaks Contract 4 by changing what serve.py returns | Low | Contract 4 is `is_unsafe`, `unsafe_probability`, `threshold_used` — none of these change with model improvements |

---

## What "done" looks like

When Codex finishes, the repo should have:

1. A measurable F1 lift (≥ 0.02 aggregate or you reject the change).
2. Updated constants + INTERFACE.md if Contracts 2/3 or Decisions 4/7 amended.
3. A new entry in COPILOT_LOG.md (Quinn's or Gracelyn's count gets
   bumped — Codex should pick the right author).
4. Re-run `python3 scripts/bootstrap_train.py 2026-05-15` succeeds
   end-to-end and prints the new metrics summary.
5. Production models in MLflow registry have been updated (the
   Phase 1a promotion block handles this automatically).
6. `tsc --noEmit` in `app/dashboard/` still passes if the TypeScript
   mirror was touched.

Once that's confirmed, the PR description gets a one-line update:
"Model F1 improved from 0.824 to X.XXX via {summary of what was
done}." Drop the new numbers into `docs/assignment_readiness.md`'s
"Model performance vs. naive baseline" table.
