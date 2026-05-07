# Ingest Implementation Plan — `include/src/ingest.py`

> **Purpose.** Strict outline for filling in the function bodies of
> `include/src/ingest.py`. Used by the team and by any AI assistant
> generating the code.
> If this document disagrees with `INTERFACE.md` or with a docstring
> already present in `ingest.py`, **the docstring wins, then INTERFACE.md.**

> **Owner of this document:** Quinton Evans (QE)
> **Reviewer:** Gracelyn Jarrett (GJ)
> **Last updated:** 2026-05-04

---

## 1. Goal

`include/src/ingest.py` already exists with a complete module docstring,
typed function signatures, and per-function docstrings (Args / Returns /
Raises). Function bodies are currently empty. This plan governs **filling
in those bodies and only those bodies** — it must not change any
signature, docstring, or import that already exists.

The end state: running `ingest_task(**context)` on a date for which all
three `TARGET_LOCATIONS` are populated produces a Contract-1-compliant
CSV at `include/data/raw/pm25_{ds}.csv` that the Airflow DAG's
`fetch_air_quality` task can consume.

---

## 2. Source-of-truth references

Read these before writing code:

| Reference | What it governs |
|---|---|
| The docstrings already in `include/src/ingest.py` | The exact behavior of each function — bodies must do what the docstrings say, no more, no less |
| `INTERFACE.md` Contract 1 | Output schema (`timestamp`, `location_id`, `pm25` — all non-nullable) |
| `INTERFACE.md` Decision 2 | Drop rows where `pm25` is null |
| `INTERFACE.md` Decision 5 | One row per `(location_id, hour)` — average duplicates within the same hour |
| `include/src/constants.py` | `OPENAQ_PM25_PARAMETER_ID`, `DATETIME_COL`, `TARGET_LOCATIONS` |
| `scripts/sample_openaq.py` | Working reference implementation of the OpenAQ API call chain — the five API-chain functions in `ingest.py` should match its behavior |
| `.github/copilot-instructions.md` Code Style | `pathlib.Path`, `response.raise_for_status()`, descriptive variable names |

---

## 3. Hard rules

1. **Do not change any function signature.** Names, parameter types, return
   types, and parameter order in `ingest.py` are the public contract that
   the DAG and tests already depend on.
2. **Do not change any docstring** beyond the existing wording. The
   docstrings are the per-function spec.
3. **Do not add new module-level functions.** If a helper is unavoidable,
   nest it inside the function that needs it.
4. **Do not remove any existing function.** All eight stay.
5. **Do not change module-level imports** unless adding `os`, `sys`,
   `requests`, and `from dotenv import load_dotenv`, which are required
   by the API call chain implementations.
6. **Do not modify any other file in the repo.** Pipeline scripts, the
   DAG, INTERFACE.md, constants.py, copilot-instructions.md — all
   off-limits for this task.
7. **Use `response.raise_for_status()`** after every `requests.get(...)`
   call.
8. **Use `pathlib.Path`** for the output CSV path. Never hardcode.
9. **Validate before writing.** `save_raw_pm25` must reject empty
   DataFrames, missing columns, and nulls before writing the CSV.

---

## 4. File location and filename

- **Path:** `include/src/ingest.py` — already exists. Edit in place.

---

## 5. Imports to add

The current top-of-file imports are minimal because the previous PR was
docstring-only. Add the imports the implementations require:

```python
# Already present (do not remove):
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

# Add:
import os
import sys
from datetime import timedelta, timezone
import requests
from dotenv import load_dotenv
```

The existing `from include.src.constants import (DATETIME_COL,
OPENAQ_PM25_PARAMETER_ID, TARGET_LOCATIONS)` import is already correct
in the docstring-era file? — verify; if missing, add it back. These
constants are referenced by the implementations.

---

## 6. Per-function implementation requirements

Each subsection lists exactly what the body must do. Bodies should be
short; if a body is exceeding ~25 lines, simplify.

### 6.1 `_build_headers() -> dict[str, str]`

**Body must:**
1. Call `load_dotenv()` to populate environment from `.env`.
2. Read `OPENAQ_API_KEY` from `os.environ`.
3. If missing or equal to `"replace-me"`, call `sys.exit(...)` with the
   exact error message specified in the docstring.
4. Return `{"X-API-Key": api_key, "Accept": "application/json"}`.

**Reference:** identical to `_headers()` in `scripts/sample_openaq.py`.

### 6.2 `get_location_metadata(location_id: int) -> dict[str, Any]`

**Body must:**
1. Build `url = f"{OPENAQ_BASE_URL}/locations/{location_id}"`.
2. Call `requests.get(url, headers=_build_headers(), timeout=REQUEST_TIMEOUT)`.
3. Call `response.raise_for_status()`.
4. Return `response.json()`.

**Reference:** identical pattern to `get_location()` in
`scripts/sample_openaq.py`.

### 6.3 `find_pm25_sensor_id(location_payload: dict[str, Any]) -> int`

**Body must:**
1. Pull `results = location_payload.get("results", [])`.
2. If empty, raise `ValueError("Location payload contains no results")`.
3. Iterate `sensors = results[0].get("sensors", [])`. For each sensor,
   read `sensor.get("parameter", {})`.
4. If `parameter.get("id") == OPENAQ_PM25_PARAMETER_ID` or
   `parameter.get("name") == "pm25"`, return `int(sensor["id"])`.
5. If the loop completes without finding one, raise
   `ValueError(f"Location {results[0].get('id', '<unknown>')} has no PM2.5 sensor")`.

**Reference:** matches `find_pm25_sensor()` in
`scripts/sample_openaq.py`, except it raises rather than returning
`None`.

### 6.4 `fetch_hourly_pm25(sensor_id, start, end) -> list[dict[str, Any]]`

**Body must:**
1. Build `url = f"{OPENAQ_BASE_URL}/sensors/{sensor_id}/hours"`.
2. Initialize `rows: list[dict[str, Any]] = []` and `page = 1`.
3. Loop:
   - Build params:
     ```
     {
         "datetime_from": start.isoformat(),
         "datetime_to":   end.isoformat(),
         "limit":         PAGE_LIMIT,
         "page":          page,
     }
     ```
   - Call `requests.get(url, headers=_build_headers(), params=params, timeout=REQUEST_TIMEOUT)`.
   - Call `response.raise_for_status()`.
   - Pull `page_results = response.json().get("results", [])`.
   - If empty, break.
   - `rows.extend(page_results)`.
   - If `len(page_results) < PAGE_LIMIT`, break (last page).
   - Else `page += 1`.
4. Return `rows`.

**Reference:** identical to `fetch_hourly()` in `scripts/sample_openaq.py`.

### 6.5 `parse_to_dataframe(raw_rows, location_id) -> pd.DataFrame`

**Body must:**
1. Build a list of `records` — for each row in `raw_rows`:
   - `period = row.get("period", {})`
   - `ts_utc = period.get("datetimeFrom", {}).get("utc")`
   - Append `{DATETIME_COL: ts_utc, "location_id": location_id, "pm25": row.get("value")}`.
2. Build `df = pd.DataFrame(records, columns=[DATETIME_COL, "location_id", "pm25"])`.
3. If df is non-empty:
   - `df[DATETIME_COL] = pd.to_datetime(df[DATETIME_COL], utc=True)`
   - `df["location_id"] = df["location_id"].astype("int64")`
   - `df["pm25"] = df["pm25"].astype("float64")`
   - `df = df.sort_values(DATETIME_COL).reset_index(drop=True)`
4. Return `df`. **Do not drop nulls here** — that happens in
   `fetch_all_locations`.

### 6.6 `fetch_all_locations(date: str) -> pd.DataFrame`

**Body must:**
1. Parse `date` (YYYY-MM-DD) as a UTC date. Compute:
   - `start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)`
   - `end = start + timedelta(days=1)`
2. Initialize `frames: list[pd.DataFrame] = []`.
3. For each `location_key, location_id in TARGET_LOCATIONS.items()`:
   - If `location_id is None`, raise `ValueError(f"TARGET_LOCATIONS[{location_key!r}] is None — populate constants.py before running ingest")`.
   - `payload = get_location_metadata(location_id)`
   - `sensor_id = find_pm25_sensor_id(payload)`
   - `raw_rows = fetch_hourly_pm25(sensor_id, start, end)`
   - `frame = parse_to_dataframe(raw_rows, location_id)`
   - Append to `frames`.
4. `df = pd.concat(frames, ignore_index=True)`.
5. Drop rows where `pm25` is null:
   `df = df.dropna(subset=["pm25"]).reset_index(drop=True)`.
6. Enforce one row per (location_id, hour): group by both keys and
   take the mean of `pm25`:
   ```python
   df = (df.groupby(["location_id", DATETIME_COL], as_index=False)["pm25"]
           .mean()
           .sort_values([DATETIME_COL, "location_id"])
           .reset_index(drop=True))
   ```
7. If `df.empty`, raise `ValueError(f"No PM2.5 readings returned across all locations for {date}")`.
8. Return `df`.

### 6.7 `save_raw_pm25(df: pd.DataFrame, date: str) -> Path`

**Body must:**
1. If `df.empty`, raise `ValueError("Refusing to write empty DataFrame")`.
2. Required columns set: `{DATETIME_COL, "location_id", "pm25"}`.
   If any are missing, raise `ValueError(f"Contract 1 columns missing: {missing}")`.
3. If `df[required].isna().any().any()`, raise
   `ValueError(f"Nulls present in Contract 1 output: {df.isna().sum().to_dict()}")`.
4. Compute `out_path = DATA_RAW_DIR / f"pm25_{date}.csv"`.
5. `out_path.parent.mkdir(parents=True, exist_ok=True)`.
6. `df.to_csv(out_path, index=False)`.
7. Return `out_path`.

### 6.8 `ingest_task(**context: Any) -> str`

**Body must:**
1. `ds = context["ds"]`.
2. `df = fetch_all_locations(ds)`.
3. `out_path = save_raw_pm25(df, ds)`.
4. Return `str(out_path)`.

---

## 7. Prerequisite — populate `TARGET_LOCATIONS`

`include/src/constants.py` currently has:

```python
TARGET_LOCATIONS: dict[str, int | None] = {
    "red_butte":  None,
    "smithfield": None,
    "ledges":     None,
}
```

`fetch_all_locations` will raise immediately if any value is `None`. The
real OpenAQ ids must be filled in before `ingest.py` can run end-to-end.
**This is a separate task — not part of implementing `ingest.py` itself.**

How to find the ids (one-time manual lookup, not part of this code):

1. **Easiest — OpenAQ Explorer web UI.** Open
   <https://explore.openaq.org/>, search by name (e.g. "Red Butte",
   "Smithfield", "Snow Canyon"), filter to PM2.5 sensors. The location
   id appears in the URL: `https://explore.openaq.org/locations/<ID>`.
2. **Alternative — modify `scripts/sample_openaq.py`.** Change `LOCATION_ID`
   to a candidate id and run; the script prints whether the location has a
   PM2.5 sensor and what its name is. Repeat for candidates.
3. **Alternative — query the API directly** with a Utah bounding box
   (`bbox=-114.05,37.0,-109.04,42.0&parameters_id=2`) via curl or a one-off
   Python script.

Once found, update `constants.py` `TARGET_LOCATIONS` with the three ids
and commit on the appropriate branch.

---

## 8. Testing strategy

After implementation, verify (in this order):

1. **Imports resolve.** From the project root with `.venv` active:
   `python -c "from include.src.ingest import *"` — must not error.
2. **Parsing against cached payload.** The repo already has cached
   real OpenAQ data at `include/data/raw/location_221401.json` and
   `include/data/raw/sensor_1287320_hours.json`. Use them to test
   `find_pm25_sensor_id` and `parse_to_dataframe` without hitting the
   network.
3. **End-to-end smoke test** (after `TARGET_LOCATIONS` is populated):
   ```
   python -m include.src.ingest
   ```
   The existing `if __name__ == "__main__":` block in `ingest.py` (if
   present) or a manual `python -c "from include.src.ingest import
   ingest_task; print(ingest_task(ds='2026-05-04'))"` should produce
   a CSV at `include/data/raw/pm25_2026-05-04.csv`.
4. **Schema verification:** read the CSV, confirm 3 columns
   (`timestamp`, `location_id`, `pm25`), all non-nullable, with rows for
   all three locations.

---

## 9. What NOT to change

- Any function signature in `ingest.py`.
- Any docstring in `ingest.py`.
- The module-level constants `OPENAQ_BASE_URL`, `DATA_RAW_DIR`,
  `REQUEST_TIMEOUT`, `PAGE_LIMIT`.
- Any other file in the repo (`constants.py`, the DAG, INTERFACE.md,
  `scripts/sample_openaq.py`, etc.).
- The contents of `scripts/sample_openaq.py` — it is the reference
  implementation, untouched.

---

## 10. Cross-review checklist coverage

| Item | Where it's enforced |
|---|---|
| Returns a string file path | `ingest_task` returns `str(out_path)` |
| Output file saved before return | `save_raw_pm25` writes the CSV before returning |
| Filename includes execution date | `f"pm25_{date}.csv"` |
| Idempotency check | Handled by the DAG `fetch_air_quality` task — `ingest_task` itself is unconditional, but is only called when the DAG sees the file is missing |
| Column names match Contract 1 | `save_raw_pm25` validates exact column set |
| No null pm25 in output | `fetch_all_locations` drops nulls; `save_raw_pm25` re-asserts |
| Meaningful exception on failure | `ValueError` with specific messages for empty data, missing columns, null cells, missing PM2.5 sensor, unpopulated `TARGET_LOCATIONS`; `requests.HTTPError` from `raise_for_status()` |
| Paths use `include/data/` | `DATA_RAW_DIR = Path("include/data/raw")` already in module-level config |
| No hardcoded API keys or absolute paths | API key loaded from `.env`; paths relative |

---

## 11. Acceptance criteria

The implementation is complete when:

- [ ] All 8 function bodies are implemented.
- [ ] No function signature has changed.
- [ ] No docstring has changed.
- [ ] No file other than `include/src/ingest.py` has been modified.
- [ ] `python -c "from include.src.ingest import *"` runs without error.
- [ ] `find_pm25_sensor_id` correctly returns `1287320` when given
      the cached `location_221401.json` payload (verifies the parser).
- [ ] `parse_to_dataframe` correctly returns 165 rows when given the
      cached `sensor_1287320_hours.json` payload (verifies the parser).
- [ ] After populating `TARGET_LOCATIONS`, `ingest_task(ds=<some_date>)`
      writes `include/data/raw/pm25_{date}.csv` with three locations'
      worth of rows and Contract 1 schema.
- [ ] All cross-review checklist items in §10 are visibly satisfied
      in the code.
