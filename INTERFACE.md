# AirAlert — Interface Contract

# Note to professor, all the ideas and concepts were discussed as a team, and then reviewed by AI. We also used AI to help clean up grammar. We did this because we thought it was very important to be clear in our thoughts, and having poor grammar or weak explanations would create ambiguity down the line. The use was minimal, but enough to note.

**Team:** Gracelyn Jarret + Quinn Evans
**Last updated:** May 4 2026

This is a living document. You will update it as you learn more about the system. That is expected and encouraged. The rule: both partners must understand and agree to every change before it is committed. Any change that affects a module boundary must be reflected in the code within the same PR.

---

## Module Ownership

| Module | Owner (writes it) | Reviewer (reviews PR) |
|---|---|---|
| `include/src/ingest.py` | QE | GJ |
| `include/src/transform.py` | GJ | QE |
| `include/src/train.py` | QE | GJ |
| `include/src/serve.py` | GJ | QE |
| `dags/airalert_dag.py` | Both | Both |
| `app/dashboard.py` | Both | Both |

---

## Shared Constants

These values are fixed and must be identical everywhere they appear in the codebase.

| Constant | Value | Used in |
|---|---|---|
| `UNSAFE_THRESHOLD` | `35.4` | `transform.py`, `serve.py`, `dashboard.py` |
| `MLFLOW_EXPERIMENT` | `"AirAlert"` | `train.py`, `serve.py` |
| `MODEL_NAME_TEMPLATE` | `"AirAlert_{location}"` | `train.py`, `serve.py` |
| `MLFLOW_URI` | `"http://localhost:5001"` | `train.py`, `serve.py` |
| `OPENAQ_PM25_PARAMETER_ID` | `2` | `ingest.py` |
| `DATETIME_COL` | `"timestamp"` | `ingest.py`, `transform.py` |
| `TARGET_LOCATIONS` | `{"red_butte": <id>, "smithfield": <id>, "ledges": <id>}` | `ingest.py`, `train.py`, `serve.py` |

> **Timezone rule:** All datetime values in this pipeline are stored in UTC. OpenAQ returns timestamps in UTC natively (`period.datetimeFrom.utc`). Any additional constants that emerge from your design decisions should be added here once decided.

---

## Data Sources

The single external API that `ingest.py` calls. Both partners should understand the source — Person A writes the calls, Person B consumes the output.

### Source — OpenAQ API v3
- **Base URL:** `https://api.openaq.org/v3`
- **Auth:** API key required — pass as `X-API-Key` header. Store in `.env`, never commit.
- **Rate limits:** Yes — if multiple students hit the API simultaneously during development, expect HTTP 429 responses. Recommended fix: cache one day's raw JSON response locally under `include/data/mock/` and develop against that.
- **Endpoint used:** `GET /v3/sensors/{sensors_id}/hours` — returns hourly averaged PM2.5 readings
- **PM2.5 parameter ID:** `2` (use `OPENAQ_PM25_PARAMETER_ID`)
- **Key response fields used in this pipeline:**

| Field path | Maps to column | Type | Notes |
|---|---|---|---|
| `period.datetimeFrom.utc` | `timestamp` | datetime64[ns, UTC] | Truncate to hour; already UTC |
| `value` | `pm25` | float64 | μg/m³; rows where this is null are dropped at ingest |

- **Location fields** (from `GET /v3/locations/{location_id}`):

| Field | Maps to column | Notes |
|---|---|---|
| `id` | `location_id` | int64; stable OpenAQ location identifier |
| `timezone` | _(internal only)_ | For reference — do not use for datetime conversion; always convert to UTC |

---

## Design Decisions

These are the architectural questions that shape how your system is built. They are divided into two groups.

**Decisions to make in W5D4** — these six decisions must be answered before writing any code. They directly determine the shape of Contract 2. Without them, your feature column table cannot be completed and neither partner can build a mock CSV or start coding independently.

**Decisions to defer** — these two decisions emerge naturally as you implement specific modules. Leave them blank for now and return to them at the indicated week.

For every decision you make: write your answer in one clear sentence, then explain your reasoning in 2–4 sentences that describe the tradeoff you considered and why your choice fits your system. There is no single right answer — the reasoning is what matters.

---

## Decisions to make in W5D4

### Decision 1 — Data freshness
*⚠️ Complete in W5D4 — blocks Contract 1*

**The question:** Does this pipeline need to distinguish between fresh and stale sensor data? If yes — where does that distinction matter: training, serving, or both?

**Things to consider:**
- The training pipeline fetches yesterday's full day of readings — every reading is already hours old when processed. Does a freshness threshold add meaningful filtering, or does it just remove valid historical data?
- The serving layer responds to on-demand prediction requests — does it matter how old the input features are when someone asks "is the air safe right now?"

No, we do not think that a freshness filter is needed to distinguish between fresh and old sensor data.

We think this because we are going to be training on the data either way. It is going to be pulled into our model, where it is trained, and then it will be served to the UI. If we do not get any data for a couple hours in that day, we do not think this is a meaningful enough disruption to hold a flag in the system. If we were looking at weather, not having completely fresh data, and having gaps in the data would be really important. When it comes to air quality, the volatility is not as high, so we think that having any data will be fine, and that we do not need to mark it with a label. We can also derive how new the data is from the payload, so any changes beyond this are not necessary.


---

### Decision 2 — Missing and unreliable sensor data
*⚠️ Complete in W5D4 — blocks Contract 1*

**The question:** Some sensors go offline for stretches of time. How should the pipeline handle locations where data is missing or incomplete for a given day?

**Things to consider:**
- If you drop rows with missing data, what happens to lag features for that location — does the next valid reading's lag_1h still represent one hour ago?
- Does it matter whether the missingness is random (battery issue) or systematic (sensor in a high-pollution area that goes offline during spikes)?

We are going to drop rows that do not have any sensor readings.

When we have a sensor off, and do not have any information on that row, we then have no information to make a prediction on. Because of this, we only have invalid data. We also would not have any valid data for the lag, if we filled this with an average or any other number, it would create a large skew towards a shift that is not happening, or it would mask a pattern that could be seen by our ML model. Because of this, we want to keep our data clean, and only train the model off signals that we are confident on.

---

### Decision 3 — Retraining trigger
*⏳ Complete by W6D4 — blocks train.py structure*

**The question:** Under what conditions should the pipeline retrain the model? What metric do you track, and what threshold triggers a retrain?

**Things to consider:**
- How would you know your model has gotten worse? Do you have access to ground truth labels on live data to compute a performance metric after deployment?
- What is the cost of a false negative (predicting safe when air is actually unsafe), and what F1 floor reflects that cost?

**Your decision:** We are deferring this decision to W6D4 when we begin implementing `_retrain_task` and have a baseline model to evaluate against.

**Your reasoning:** Without a baseline model and a sense of how it actually performs on real data, picking a retrain threshold would be guesswork. The metric we expect to track is F1 on the unsafe class, since that is the project's primary evaluation metric and false negatives (predicting safe when air is actually unsafe) are the more costly error type for an air-quality alert system. The threshold and cadence will be set after observing baseline performance over a multi-week window — committing to either now would just be a number we'd revisit immediately.

**Baseline outline** From our current understanding we should trigger a retrain each day when the data comes in. we will run it on all current data, if the model performs better than it did the day before, then we will include the new model. This is a very basic idea, and will probably be changed as we go on, per our outline above. But, to show we put thought into this, we are putting a basic outline of what we are planning to do, and what we think will be best. While also acknowledging that we will likely be changing this decsion in the coming days. As of right now, new model will be trained each day after the new batch has come in.

---

### Decision 4 — Feature engineering choices
*⚠️ Complete in W5D4 — directly produces Contract 2*

**The question:** What features will `transform.py` produce for `train.py`? What lag windows, temporal features, and aggregations will you use?

**Things to consider:**
- What patterns in air quality would a model benefit from knowing — time of day, recent trend, weather — and which of those are actually available at prediction time without causing leakage?
- What is the minimum feature set needed to beat the naive baseline of always predicting safe?

**Your decision:** We are using nine engineered features, three pm25 lags (1h, 3h, 24h), two rolling stats over the prior three hours mean and std, and four temporal features hour_of_day, day_of_week, month_of_year, is_weekend.

**Your reasoning:** The lag and rolling features capture our short term signal dynamics and the 1h and 3h lags give the model recent momentum. the 24h lag anchors the daily cycle, and rolling std picks up volatility that often precedes pollution spikes. The temporal features hold patterns we already know exist in air quality such as morning traffic, weekend activity, seasonal inversions and wildfire season, without forcing the model to discover them from scratch. The rolling features deliberately exclude the current hour's pm25 to avoid leaking the target into its own predictors. We chose not to include weather features such as temperature, humidity in this version of the project to keep the pipeline focused on a single data source at the cost of losing meteorological dispersion signal — a tradeoff we may revisit later.

**Your agreed feature list** (this becomes Contract 2):

| Feature | Type | Nullable | How computed | Why it's useful |
|---|---|---|---|---|
| is_unsafe | int64 | No | pm25 > 35.4 | Target variable |
| pm25_lag_1h | float64 | No | pm25 shifted 1h within `location_id` | Captures very recent momentum |
| pm25_lag_3h | float64 | No | pm25 shifted 3h within `location_id` | Captures short-term trend |
| pm25_lag_24h | float64 | No | pm25 shifted 24h within `location_id` | Anchors the daily diurnal cycle (yesterday-same-hour) |
| pm25_rolling_mean_3h | float64 | No | mean over (t-3, t-2, t-1) within `location_id` | Recent baseline level — excludes current hour to prevent target leakage |
| pm25_rolling_std_3h | float64 | No | std over (t-3, t-2, t-1) within `location_id` | Recent volatility — rises sharply before pollution events |
| hour_of_day | int64 | No | timestamp.hour | Captures diurnal patterns (traffic, inversions) |
| day_of_week | int64 | No | timestamp.dayofweek (0-6) | Captures weekly variation in activity |
| month_of_year | int64 | No | timestamp.month (1-12) | Captures seasonal patterns (inversions, wildfire season) |
| is_weekend | int64 | No | day_of_week ≥ 5 | Binary flag distinguishing weekday-vs-weekend activity |


---

### Decision 5 — Aggregation granularity

We decided that moving forward with aggregation per hour per location was the best option.

Aggregating to one row per hour per location leads to much cleaner data processing. We want to use a time-series approach, and feeding the model uniform hourly data per location is what allows lag and rolling features to be computed correctly without gaps in the temporal grid. Having messy raw-format data with multiple readings per hour would distort the patterns the model is supposed to learn. Because time-series models depend on a regular cadence between observations, ensuring the time grid is clean and consistent is necessary.

---

### Decision 6 — Single location vs. multi-location model
*⚠️ Complete in W5D4 — affects train.py structure and Contract 2*

**The question:** Should the model be trained on data from all locations combined (one global model) or separately per location (one model per location)?

**Things to consider:**
- How many rows does each location contribute to your training data — is there enough per-location data to train a reliable per-location model?
- How does your choice affect `train.py`, the MLflow registry structure, and what `serve.py` needs to load at startup?

**Your decision:** We are training three separate per-location models — one each for Red Butte (Salt Lake City), Smithfield (northern Utah), and Ledges by Snow Canyon (St. George) — registered in MLflow under names like `AirAlert_red_butte`, `AirAlert_smithfield`, and `AirAlert_ledges`.

**Your reasoning:** Restricting to Utah lets us speak knowledgeably about the climate, terrain, and pollution sources at each site, which tightens the project scope and our ability to validate results. Per-location models, rather than one global model with `location_id` as a feature, let each model learn the specific patterns of its site — Smithfield's agricultural valley, Red Butte's urban-canyon air, and Ledges' high-desert profile — without the noise of cross-location averaging. The tradeoff is that each model trains on less data, which we will mitigate by accumulating a longer rolling training window in `train.py`. If a site goes data-dark on a given day, `serve.py` can fall back to the nearest other model's prediction so the dashboard remains useful, with a clear caveat that the answer is not site-specific.

---

## Decisions to defer

### Decision 7 — Classifier choice and probability calibration
*⏳ Complete by W6D3 — when you study `_retrain_task` and begin `serve.py`*

**The question:** What classifier will `train.py` train, and how will `serve.py` return a meaningful `unsafe_probability`?

**Things to consider:**
- Does your chosen model's `predict_proba` output produce well-calibrated probabilities, or do they cluster near 0 and 1 in a way that would mislead a user reading a confidence score?
- What does `unsafe_probability = 0.72` actually mean to someone using the dashboard — and is your model's output trustworthy enough to display that number?

**Your decision:**

**Your reasoning:**

---

### Decision 8 — How the dashboard sources input data
*⏳ Complete by W7D2 — when you build the dashboard*

**The question:** When a user opens the dashboard, where do the input feature values come from — manual entry, live API fetch, or pre-loaded location values?

**Things to consider:**
- Can a non-technical user reasonably be expected to know their local PM2.5 lag values, and if not, what does that mean for the usability of manual entry?
- What failure modes does each approach introduce, and which tradeoff is most acceptable given your serving architecture?

**Your decision:**

**Your reasoning:**

---

## Data Contracts

Complete these after your W5D4 design decisions are settled. Column names and types here must match what is actually in the code. Both partners must be able to build a mock CSV from these specs and develop their module independently.

---

### Contract 1: `ingest.py` → `transform.py`

Output file: `include/data/raw/pm25_{YYYY-MM-DD}.csv`

> This file is the OpenAQ output for the three target locations, aggregated to one row per `(location_id, hour)`. Rows where pm25 is null are dropped at ingest.

| Column | Source | Type | Nullable | Notes |
|---|---|---|---|---|
| `timestamp` | OpenAQ | datetime64[ns, UTC] | No | UTC; one row per location per hour |
| `location_id` | OpenAQ | int64 | No | OpenAQ location ID; one of `TARGET_LOCATIONS` |
| `pm25` | OpenAQ | float64 | No | μg/m³; rows where pm25 is null are dropped at ingest |

---

### Contract 2: `transform.py` → `train.py`

Output file: `include/data/features/features_{YYYY-MM-DD}.csv`

| Column | Type | Nullable | Example |
|---|---|---|---|
| timestamp | datetime64[ns, UTC] | No | 2026-04-29 14:00:00+00:00 |
| location_id | int64 | No | 221401 |
| is_unsafe | int64 | No | 0 |
| pm25_lag_1h | float64 | No | 11.6 |
| pm25_lag_3h | float64 | No | 4.2 |
| pm25_lag_24h | float64 | No | 7.7 |
| pm25_rolling_mean_3h | float64 | No | 5.7 |
| pm25_rolling_std_3h | float64 | No | 2.1 |
| hour_of_day | int64 | No | 14 |
| day_of_week | int64 | No | 2 |
| month_of_year | int64 | No | 4 |
| is_weekend | int64 | No | 0 |

---

### Contract 3: `train.py` → `serve.py`

Three models registered in MLflow as `AirAlert_red_butte`, `AirAlert_smithfield`, and `AirAlert_ledges` at `Production` stage.

Feature columns the models expect (must match Contract 2, excluding timestamp, location_id, is_unsafe):

```python
FEATURE_COLS = [
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
```

*Complete Decision 7 (classifier choice) before finalising this contract.*

---

### Contract 4: `serve.py` → `dashboard.py`

*Complete Decision 8 (dashboard data sourcing) before finalising this contract.*

**API endpoint:** `POST http://localhost:8000/predict`

**Request body:**
```json
{
  "location": "red_butte",
  "pm25_lag_1h": 11.6,
  "pm25_lag_3h": 4.2,
  "pm25_lag_24h": 7.7,
  "pm25_rolling_mean_3h": 5.7,
  "pm25_rolling_std_3h": 2.1,
  "hour_of_day": 14,
  "day_of_week": 2,
  "month_of_year": 4,
  "is_weekend": 0
}
```
The `location` field selects which of the three per-location models `serve.py` loads to make the prediction.

**Response body:**
```json
{
  "is_unsafe": 0,
  "unsafe_probability": 0.12,
  "threshold_used": 35.4
}
```

**Health check:** `GET http://localhost:8000/health` → `{"status": "ok"}`

---

## Branch and Commit Conventions

| Convention | Your decision |
|---|---|
| Branch naming format | `<initials>/<feature>` → e.g. `qe/ingest-foundation`, `gj/transform-features` |
| Commit message format | `<module>: <description>` → e.g. `ingest: add openaq client`, `transform: add lag features` |
| PR review rule | Neither partner merges their own PR — the other must approve |
| Main branch protection | Direct pushes to main are not allowed |

---

## Contract Review Checklist

Before committing this file, both partners confirm:

- [ ] Decisions 1–6 have answers with reasoning — not just values
- [ ] Contract 2 has no blank rows
- [ ] Both partners can build a mock CSV from Contract 1 and Contract 2 independently
- [ ] Both partners have read every contract entry and agreed to it
- [ ] Both partners understand what will break in their module if the upstream contract changes
- [ ] Decisions 7 and 8 are present and marked as deferred with target weeks

---

## Mock Data

Once contracts are finalised, each partner creates a small mock CSV for the boundary they consume. Save to `include/data/mock/` (gitignored). Use for development and testing before the upstream module produces real data.

| Partner | File to create | Matches |
|---|---|---|
| Gracelyn (builds `transform.py`) | `include/data/mock/mock_ingest_output.csv` | Contract 1 exactly |
| Quinn (builds `train.py`) | `include/data/mock/mock_transform_output.csv` | Contract 2 exactly |

---

## Change Log

When you update this document mid-project, record it here.

| Date | What changed | Why | Both partners agreed? |
|---|---|---|---|
| 2026-05-04 | Initial commit of finalized contracts and decisions; renamed from template; unified naming convention; removed weather/Open-Meteo references; locked three per-location models | Lock in W5D4 design decisions and reconcile mock CSV with contracts | Yes |
