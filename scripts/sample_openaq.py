"""
Throwaway sample script — pulls 7 days of hourly PM2.5 readings from the
OpenAQ v3 API for one location (BV, Bountiful UT — location_id 221401).

Goal: get a real sample of data into data/raw/ so we can eyeball the shape
before locking in INTERFACE.md contract decisions.

Run from the project root:
    python scripts/sample_openaq.py

Outputs (under data/raw/, which is gitignored):
    location_<id>.json          — full /v3/locations response
    sensor_<id>_hours.json      — full /v3/sensors/{id}/hours response
    pm25_sample_loc_<id>.csv    — flattened (timestamp, location_id, pm25)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# --- Config ---------------------------------------------------------------

LOCATION_ID = 221401          # BV — Bountiful, UT
DAYS_BACK = 7
BASE_URL = "https://api.openaq.org/v3"
OUT_DIR = Path("data/raw")
REQUEST_TIMEOUT = 30          # seconds

# --- Helpers --------------------------------------------------------------

def _headers() -> dict[str, str]:
    """Build the auth header. Fails loudly if the key is missing."""
    load_dotenv()
    api_key = os.environ.get("OPENAQ_API_KEY")
    if not api_key or api_key == "replace-me":
        sys.exit(
            "OPENAQ_API_KEY is not set. Copy .env.example to .env and fill "
            "in your key from https://explore.openaq.org/account"
        )
    return {"X-API-Key": api_key, "Accept": "application/json"}


def get_location(location_id: int) -> dict:
    """Fetch one location's metadata, including its sensor list."""
    url = f"{BASE_URL}/locations/{location_id}"
    response = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def find_pm25_sensor(location_payload: dict) -> int | None:
    """Return the sensor_id of the PM2.5 sensor at this location, or None."""
    results = location_payload.get("results", [])
    if not results:
        return None
    sensors = results[0].get("sensors", [])
    for sensor in sensors:
        param = sensor.get("parameter", {})
        if param.get("name") == "pm25" or param.get("id") == 2:
            return sensor["id"]
    return None


def list_sensors(location_payload: dict) -> list[tuple[int, str, str]]:
    """Return [(sensor_id, parameter_name, units)] for all sensors at this location."""
    results = location_payload.get("results", [])
    if not results:
        return []
    out = []
    for sensor in results[0].get("sensors", []):
        param = sensor.get("parameter", {})
        out.append((sensor["id"], param.get("name", "?"), param.get("units", "?")))
    return out


def fetch_hourly(sensor_id: int, start: datetime, end: datetime) -> list[dict]:
    """Pull /v3/sensors/{id}/hours rows between start and end (UTC).

    Walks pagination. 7 days = 168 hours, well under any single page, but the
    loop is here so the same code handles longer windows later.
    """
    url = f"{BASE_URL}/sensors/{sensor_id}/hours"
    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "datetime_from": start.isoformat(),
            "datetime_to": end.isoformat(),
            "limit": 1000,
            "page": page,
        }
        response = requests.get(
            url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        page_results = response.json().get("results", [])
        if not page_results:
            break
        rows.extend(page_results)
        if len(page_results) < 1000:
            break
        page += 1
    return rows


def flatten_to_dataframe(raw_rows: list[dict], location_id: int) -> pd.DataFrame:
    """Turn the raw /hours response into (timestamp, location_id, pm25) rows."""
    records = []
    for row in raw_rows:
        period = row.get("period", {})
        ts_utc = period.get("datetimeFrom", {}).get("utc")
        records.append({
            "timestamp": ts_utc,
            "location_id": location_id,
            "pm25": row.get("value"),
        })
    df = pd.DataFrame(records)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# --- Main -----------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] Fetching location {LOCATION_ID} metadata...")
    location_payload = get_location(LOCATION_ID)
    location_json_path = OUT_DIR / f"location_{LOCATION_ID}.json"
    location_json_path.write_text(json.dumps(location_payload, indent=2))
    print(f"      saved -> {location_json_path}")

    sensor_id = find_pm25_sensor(location_payload)
    if sensor_id is None:
        print(f"\nLocation {LOCATION_ID} has no PM2.5 sensor.")
        print("Sensors at this location:")
        for sid, name, units in list_sensors(location_payload):
            print(f"  - sensor {sid}: {name} ({units})")
        print("\nPick a different location_id and rerun.")
        return
    print(f"      PM2.5 sensor_id = {sensor_id}")

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=DAYS_BACK)
    print(f"\n[2/3] Fetching hourly PM2.5 from {start.isoformat()} "
          f"to {end.isoformat()}...")
    raw_rows = fetch_hourly(sensor_id, start, end)
    sensor_json_path = OUT_DIR / f"sensor_{sensor_id}_hours.json"
    sensor_json_path.write_text(json.dumps(raw_rows, indent=2))
    print(f"      pulled {len(raw_rows)} raw rows -> {sensor_json_path}")

    print("\n[3/3] Flattening to CSV...")
    df = flatten_to_dataframe(raw_rows, LOCATION_ID)
    csv_path = OUT_DIR / f"pm25_sample_loc_{LOCATION_ID}.csv"
    df.to_csv(csv_path, index=False)
    print(f"      saved {len(df)} rows -> {csv_path}")

    if df.empty:
        print("\nNo readings returned for that window. Try widening DAYS_BACK.")
        return

    print("\n--- Preview (first 10 rows) ---")
    print(df.head(10).to_string(index=False))
    print("\n--- pm25 summary ---")
    print(df["pm25"].describe())
    print(f"\nNull pm25 rows : {df['pm25'].isna().sum()} / {len(df)}")
    print(f"Time range     : {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(f"Unsafe (>35.4) : {(df['pm25'] > 35.4).sum()} hours")


if __name__ == "__main__":
    main()
