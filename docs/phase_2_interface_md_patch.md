# Phase 2 — INTERFACE.md Patch (Decision 7 + Decision 8 polish)

**Status:** staging doc for the W7A1 Part 1 work. Once you're on the
`feature/dashboard` branch (which builds on `feature/drift-detection`),
paste the three blocks below into `INTERFACE.md` at the indicated
locations. Delete this file in the same commit that applies the patch
so the staging doc doesn't survive past the merge.

This is split into three blocks because the right INTERFACE.md
location for each one is different:

1. **Decision 7** — append a paragraph to the existing reasoning. Do
   not rewrite the original; this is additive.
2. **Decision 8** — replace the placeholder paragraph wholesale with
   the new full write-up.
3. **Change Log** — append one row.

---

## Block 1 — Append to Decision 7 reasoning

Find the existing Decision 7 reasoning paragraph in INTERFACE.md (the
one that ends "We are leaning towards being as safe as possible,
ensuring that the predictions are ensuring students stay inside if the
air quality is predicted to be low."). Add a blank line and paste this
paragraph immediately after it.

```markdown
**Calibration (W7A1 addition).** Two implementation details matter for how the dashboard should present `unsafe_probability`. First, `train.py` uses `LogisticRegression(class_weight="balanced", max_iter=1000)`. The balanced class weighting is required at our positive-class rate of ~0.6 percent — without it the model collapses to "always predict safe" and recall on the unsafe class drops to zero. But balanced class weighting also deliberately biases the model's `predict_proba` output toward the minority class, so the raw probability is **not a calibrated absolute probability** that the air will be unsafe — it is a *relative ranking score* that orders hours from least to most likely to exceed 35.4 μg/m³. Second, we are not adding `sklearn.calibration.CalibratedClassifierCV` in this PR — calibration requires a hold-out validation set we don't have enough data to spare on a daily retraining cadence with a 7-day rolling window. To prevent the dashboard from over-claiming, the user-facing certainty is shown as one of three buckets (high ≥ 0.70, medium ≥ 0.40, low < 0.40) rather than a raw percentage. Inside the API response, `unsafe_probability` continues to carry the raw float so consumers that want it have it; the bucketing happens in the dashboard layer. This tradeoff is documented as a known limitation in the project README and in the final PR description.
```

---

## Block 2 — Replace Decision 8 reasoning wholesale

Find the existing Decision 8 reasoning paragraph (currently the one
that starts "We are going to be using fastAPI, caching our model, and
using m_time..."). Replace the entire reasoning section — keep the
question header and the "Things to consider" bullets — with the prose
below.

```markdown
**Your decision:** The dashboard is a Next.js + React + Tailwind application at `app/dashboard/`. The user picks a location and a future date plus an hour range; the dashboard's Node-side API layer reads `include/data/raw/pm25_*.csv` from the pipeline's output directory, computes the nine Contract 3 feature values for each hour using a hour-of-day "recent pattern" approach over the last 14 days of raw data, and POSTs each row to `serve.py`'s `/predict` endpoint via a thin proxy route. The browser never talks to FastAPI directly — every external call goes through Next.js, which means we add zero CORS surface area on the serving side.

**Your reasoning:** A non-technical user — the project's stakeholder framing is parents and elementary-school administrators making the "indoor vs outdoor recess" call — cannot reasonably enter `pm25_lag_1h`, `pm25_rolling_std_3h`, and the other engineered features that Contract 3 requires. Manual entry was off the table from that first principle. Three alternatives remained: live-fetch from OpenAQ at request time (couples the dashboard to a third-party API and inherits its rate limit), maintain a separate `/features` endpoint in `serve.py` (cleaner separation but requires expanding the serving surface area beyond what the rubric specified), or have the dashboard read the same raw CSVs that `transform.py` already reads downstream. We chose the third option because the dashboard and pipeline run on the same host for the assignment-scale deployment, the raw CSVs are already the system's source-of-truth for actual measurements, and it keeps the `serve.py` surface area exactly as Contract 4 documents.

The hourly-pattern approach handles three time horizons cleanly. **Past dates with raw data on disk** use the actual measured pm25 values to build lag and rolling features — same path the training pipeline takes. **Past dates with missing raw entries** (sensor outage that day) fall back to the recent-pattern mean for the matching hour-of-day and flag the prediction as `fallback_used`. **Future dates** always use the recent pattern: for each requested hour-of-day, take the mean (and standard deviation) of pm25 readings at that hour-of-day across the last 14 days, then derive the lag-1h / lag-3h / lag-24h / rolling-mean / rolling-std features by reading or pattern-substituting the relevant prior hours. Temporal features (`hour_of_day`, `day_of_week`, `month_of_year`, `is_weekend`) come from the requested datetime directly with no fallback. Rows with fewer than 7 observations available for their hour-of-day are returned with a low-confidence flag the UI surfaces with a small ⚠ icon so the user sees that the prediction is operating on thin evidence.

In production at scale this would be promoted to a `GET /features/recent_pattern` endpoint on `serve.py` so the dashboard could be deployed independently. The current "same-host filesystem" approach is intentionally a hackathon-grade decision documented as such in the final PR description; the full design lives in `docs/dashboard_implementation_plan.md`.
```

---

## Block 3 — Append a Change Log row

Find the existing Change Log table at the bottom of INTERFACE.md.
Append this row directly below the most recent entry (the one dated
2026-05-14 for the drift detection work). If the drift entry has not
yet landed on the branch you're on, just append this row at the end of
the table.

```markdown
| 2026-05-14 | Decision 7 reasoning expanded with the calibration limitation note (balanced LR `predict_proba` is a relative ranking score, not an absolute probability; dashboard shows high/medium/low buckets per the existing W6 rule). Decision 8 reasoning replaced with the full Next.js + recent-pattern feature-prep design. Full design in `docs/dashboard_implementation_plan.md`; substituted Next.js for the rubric's suggested Streamlit and renamed `app/dashboard.py` → `app/dashboard/`. | W7A1 Part 1 finalizes both deferred decisions before `serve.py` (done) and the dashboard (in progress) ship. The class-weight calibration note prevents the dashboard from over-claiming certainty. | Yes |
```

---

## Acceptance check after pasting

After applying the three blocks, verify:

- [ ] Decision 7 reasoning now has two paragraphs — the original W6 reasoning and the new calibration paragraph.
- [ ] Decision 8 reasoning has the new three-paragraph design (decision sentence + reasoning + hourly-pattern detail).
- [ ] Change Log table has the new 2026-05-14 Decision 7+8 row immediately below the drift row (or appended at the end if drift hasn't merged yet on this branch).
- [ ] Both partners initial the row before the commit lands (Gracelyn agrees to the changes by reviewing the PR).
- [ ] `docs/phase_2_interface_md_patch.md` is deleted in the same commit that applies the patch.
