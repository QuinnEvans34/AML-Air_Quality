"""
ingest.py — OpenAQ PM2.5 data ingestion for AirAlert.

Owner: Quinton Evans (QE)
Reviewer: Gracelyn Jarret (GJ)

This module fetches one day of hourly PM2.5 readings from the OpenAQ v3
API for each location in TARGET_LOCATIONS (Red Butte, Smithfield, Ledges)
and writes a unified CSV that conforms to Contract 1 in INTERFACE.md.

OpenAQ v3 requires a two-step lookup for each location:

    1. GET /v3/locations/{location_id}      -> metadata + sensor list
    2. GET /v3/sensors/{sensor_id}/hours    -> hourly-averaged readings
       for one parameter at one location

The PM2.5 sensor (parameter id = OPENAQ_PM25_PARAMETER_ID) is extracted
from each location's sensor list, then /hours is pulled over the target
date window (UTC midnight -> next UTC midnight).

Inputs
------
- OPENAQ_API_KEY         loaded from .env at function call time via dotenv
- target date            YYYY-MM-DD string supplied by Airflow
                         `context['ds']` or by the CLI for local runs
- TARGET_LOCATIONS       dict[str, int] mapping a location_key to its
                         OpenAQ location_id (see constants.py)

Outputs
-------
A single CSV at  ``include/data/raw/pm25_{YYYY-MM-DD}.csv``  with one row
per (location_id, hour). Schema matches Contract 1 in INTERFACE.md::

    timestamp     datetime64[ns, UTC]   non-null
    location_id   int64                 non-null
    pm25          float64               non-null

Constraints (see INTERFACE.md Decisions 1, 2, 5, 6)
---------------------------------------------------
- All timestamps are UTC. OpenAQ's ``period.datetimeFrom.utc`` is read
  directly; no timezone conversion is performed.
- Rows where pm25 is null are dropped at this layer (Decision 2).
- Output guarantees one row per (location_id, hour) — duplicates within
  the same hour are averaged before writing (Decision 5).
- This module does NOT call Open-Meteo or any weather API — weather
  features are excluded from this version of the project.
- This module ingests data for the three TARGET_LOCATIONS only; one CSV
  contains rows for all three (per-location modeling happens downstream
  in train.py — Decision 6).

Error behavior
--------------
- Missing OPENAQ_API_KEY                 -> SystemExit with clear message
- HTTP errors from any OpenAQ endpoint   -> requests.HTTPError
- Zero readings returned across all
  locations for the target date          -> ValueError
- Location has no PM2.5 sensor           -> ValueError

Airflow integration
-------------------
The XCom-friendly entry point is ``ingest_task(**context) -> str``,
which returns the absolute path to the written CSV. Per the project's
XCom convention (.github/copilot-instructions.md), tasks return file
paths, never DataFrames.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# --- Module-level config --------------------------------------------------

OPENAQ_BASE_URL: str = "https://api.openaq.org/v3"
DATA_RAW_DIR: Path = Path("include/data/raw")
REQUEST_TIMEOUT: int = 30  # seconds
PAGE_LIMIT: int = 1000  # OpenAQ v3 max page size for /hours


# --- OpenAQ API call chain ------------------------------------------------

def _build_headers() -> dict[str, str]:
    """
    Build the OpenAQ auth headers, loading OPENAQ_API_KEY from .env.

    Loads .env on every call (cheap, idempotent) so a key rotated mid-run
    is picked up without restarting the Airflow worker.

    Returns:
        Dict suitable for ``requests.get(headers=...)`` with ``X-API-Key`` set.

    Raises:
        SystemExit: if OPENAQ_API_KEY is missing or still the placeholder
            value ``"replace-me"`` from ``.env.example``.
    """


def get_location_metadata(location_id: int) -> dict[str, Any]:
    """
    Fetch a single location's metadata from OpenAQ v3.

    Calls ``GET /v3/locations/{location_id}``. The returned payload's
    ``results[0].sensors`` array is what ``find_pm25_sensor_id`` consumes.

    Args:
        location_id: OpenAQ location id (one of the values in
            TARGET_LOCATIONS).

    Returns:
        The full JSON payload as a dict (the ``meta`` + ``results`` envelope).

    Raises:
        requests.HTTPError: if the request fails (4xx / 5xx).
    """


def find_pm25_sensor_id(location_payload: dict[str, Any]) -> int:
    """
    Extract the PM2.5 sensor_id from a /v3/locations payload.

    OpenAQ locations expose multiple sensors (NO, NO2, O3, PM2.5, etc.).
    Pick the one whose ``parameter.id`` equals OPENAQ_PM25_PARAMETER_ID
    (= 2).

    Args:
        location_payload: The dict returned by ``get_location_metadata``.

    Returns:
        The PM2.5 sensor_id.

    Raises:
        ValueError: if the location has no PM2.5 sensor.
    """


def fetch_hourly_pm25(
    sensor_id: int,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """
    Pull hourly PM2.5 readings from /v3/sensors/{sensor_id}/hours.

    Walks API pagination (``limit=PAGE_LIMIT`` per page) so the same
    function works for single-day pulls (~24 rows) and multi-day
    backfills.

    Args:
        sensor_id: PM2.5 sensor_id from ``find_pm25_sensor_id``.
        start: inclusive UTC start datetime.
        end: exclusive UTC end datetime.

    Returns:
        A list of raw row dicts, each containing
        ``period.datetimeFrom.utc`` and ``value`` (the PM2.5 reading
        in μg/m³).

    Raises:
        requests.HTTPError: if any page request fails.
    """


def parse_to_dataframe(
    raw_rows: list[dict[str, Any]],
    location_id: int,
) -> pd.DataFrame:
    """
    Flatten raw OpenAQ /hours rows into a DataFrame matching Contract 1.

    Maps:

    - ``period.datetimeFrom.utc``  ->  ``timestamp`` (datetime64[ns, UTC])
    - ``value``                    ->  ``pm25``      (float64)
    - the supplied ``location_id`` ->  ``location_id`` (int64)

    Sorts by timestamp ascending. Preserves null pm25 values; null-dropping
    happens in ``fetch_all_locations`` after concatenation.

    Args:
        raw_rows: List of dicts from ``fetch_hourly_pm25``.
        location_id: The OpenAQ location id these readings came from.

    Returns:
        DataFrame with columns ``[timestamp, location_id, pm25]``.
    """


# --- Orchestration --------------------------------------------------------

def fetch_all_locations(date: str) -> pd.DataFrame:
    """
    Fetch one day of PM2.5 readings for all locations in TARGET_LOCATIONS.

    For each ``location_key -> location_id`` pair in TARGET_LOCATIONS:

      1. Call ``get_location_metadata(location_id)``.
      2. Pass the payload to ``find_pm25_sensor_id(...)``.
      3. Call ``fetch_hourly_pm25(sensor_id, start, end)``, where
         ``start = date at 00:00 UTC`` and
         ``end = (date + 1 day) at 00:00 UTC``.
      4. Pass results to ``parse_to_dataframe(rows, location_id)``.

    Concatenates per-location DataFrames, drops rows where pm25 is null
    (Decision 2), then groups by ``(location_id, timestamp)`` and averages
    pm25 to enforce one row per (location_id, hour) (Decision 5).

    Args:
        date: Target date in YYYY-MM-DD format. Treated as a UTC date.

    Returns:
        DataFrame with the Contract 1 schema::

            timestamp     datetime64[ns, UTC]   non-null
            location_id   int64                 non-null
            pm25          float64               non-null

    Raises:
        ValueError: if no readings are returned across all locations,
            if any location has no PM2.5 sensor, or if any
            TARGET_LOCATIONS value is still ``None``.
        requests.HTTPError: on any underlying API failure.
    """


def save_raw_pm25(df: pd.DataFrame, date: str) -> Path:
    """
    Write a Contract 1 DataFrame to ``include/data/raw/pm25_{date}.csv``.

    Creates the directory if it does not exist. Validates that the
    DataFrame conforms to the Contract 1 schema (column names, no nulls)
    before writing — fail loudly here rather than letting bad data
    propagate downstream.

    Args:
        df: DataFrame with the Contract 1 schema.
        date: YYYY-MM-DD; appears in the output filename.

    Returns:
        Absolute path to the written CSV.

    Raises:
        ValueError: if the DataFrame is empty, has the wrong columns,
            or contains nulls in any column.
    """


def ingest_task(**context: Any) -> str:
    """
    Airflow task: ingest one day of PM2.5 readings, return the output path.

    Pulls the execution date from ``context['ds']``, calls
    ``fetch_all_locations``, saves to disk via ``save_raw_pm25``, and
    returns the file path string for downstream tasks to consume via XCom.

    Per the project's XCom convention (.github/agents.md), this function
    returns a path string rather than a DataFrame.

    Args:
        **context: Airflow task context dict; uses ``context['ds']``
            (a YYYY-MM-DD string).

    Returns:
        Absolute path string to ``include/data/raw/pm25_{ds}.csv``.

    Raises:
        ValueError: if no readings were fetched.
        requests.HTTPError: on API failure.
    """
