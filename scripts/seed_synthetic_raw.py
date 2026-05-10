"""
seed_synthetic_raw.py — TEST FIXTURE: pre-populate include/data/raw/ with
synthetic Contract-1 CSVs so the pipeline can be exercised end-to-end
without hitting the OpenAQ API.

This is a developer/grading convenience and is NOT part of the production
pipeline. ``include/src/ingest.py`` is API-only — it never falls back to
synthesis. This script exists for two reasons:

1. The ``engineer_features`` task needs a multi-day rolling window of raw
   CSVs (because ``pm25_lag_24h`` requires ≥25 hours of lookback per
   location). On a fresh checkout there is no history; without seeding,
   the first DAG run produces an empty features frame.
2. Real OpenAQ data for the three Utah TARGET_LOCATIONS is often clean
   enough that an entire day has zero unsafe hours (PM2.5 < 35.4 µg/m³).
   Training a 2-class classifier on single-class data fails. The
   synthetic structure here guarantees both classes appear in train and
   test splits so the W6A1 demo run produces meaningful metrics.

Usage
-----
::

    # default: 30 days ending today (UTC), skip files that already exist
    python scripts/seed_synthetic_raw.py

    # explicit window + force overwrite
    python scripts/seed_synthetic_raw.py --days 30 --end-date 2026-05-09 --force

What the synthetic data captures (so feature engineering has signal):

* Diurnal cycle — strong morning (~08:00 UTC) and evening (~18:00 UTC)
  rush-hour peaks on weekdays; smaller midday bump on weekends.
* AR(1) persistence within day — ``pm25_lag_1h`` becomes a strong
  predictor of the current hour.
* Cross-day continuity — the prior day's last hour seeds the next day's
  first hour, so ``pm25_lag_24h`` carries information.
* Per-location signature — each TARGET_LOCATIONS entry has its own
  baseline shift and amplitude multiplier.
* Multi-hour pollution events — ~8% of days get a 4–10 hour event that
  raises the diurnal target, so rolling-mean and rolling-std features
  capture rising-edge precursors.
* Seasonal trend — small ±4 µg/m³ cosine over the year (peak ~mid-Jan,
  matching Salt Lake Valley winter inversions).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Allow running this file directly from the repo root via ``python scripts/...``.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from include.src.constants import DATETIME_COL, TARGET_LOCATIONS  # noqa: E402
from include.src.ingest import DATA_RAW_DIR, save_raw_pm25  # noqa: E402


# --- Synthetic data generator --------------------------------------------

def generate_synthetic_pm25(
    date: str, location_ids: list[int] | None = None
) -> pd.DataFrame:
    """
    Produce a Contract-1-shaped synthetic PM2.5 day with learnable structure.

    Returns a DataFrame matching the same schema as the real ingest output
    (columns ``[timestamp, location_id, pm25]``, all non-null) so the seed
    output is indistinguishable from real OpenAQ data downstream.

    Args:
        date: Target date in YYYY-MM-DD (UTC).
        location_ids: Locations to fabricate rows for. Defaults to the
            non-None values in ``TARGET_LOCATIONS``.
    """
    if location_ids is None:
        location_ids = [
            int(lid) for lid in TARGET_LOCATIONS.values() if lid is not None
        ]
    if not location_ids:
        raise ValueError(
            "TARGET_LOCATIONS has no populated location ids; cannot synthesize"
        )

    target_date = datetime.fromisoformat(date)
    seed = int(target_date.strftime("%Y%m%d"))
    rng = np.random.default_rng(seed)

    is_weekend = target_date.weekday() >= 5
    # Day-of-year seasonal trend: peak around mid-January (winter inversions
    # in Salt Lake Valley), trough in mid-July.
    doy = target_date.timetuple().tm_yday
    seasonal_offset = 4.0 * np.cos((doy - 15) * 2 * np.pi / 365.0)

    start = target_date.replace(tzinfo=timezone.utc)

    def _diurnal(hour: int) -> float:
        """Deterministic diurnal pm25 target for the given hour (UTC).

        Amplitudes are tuned so weekday rush-hour peaks reliably push the
        AR(1)-smoothed pm25 across the 35.4 µg/m³ unsafe threshold even at
        the lowest per-location amplitude multiplier — guaranteeing every
        location has unsafe hours in both train and test splits.
        """
        if is_weekend:
            return 6.0 + 12.0 * np.exp(-((hour - 12) ** 2) / (2 * 5.0 ** 2))
        morning = 38.0 * np.exp(-((hour - 8) ** 2) / (2 * 1.8 ** 2))
        evening = 48.0 * np.exp(-((hour - 18) ** 2) / (2 * 2.0 ** 2))
        return 6.0 + morning + evening

    rows: list[dict[str, Any]] = []
    for location_id in location_ids:
        # Per-location signature: stable across days, derived from id only.
        loc_seed = int(location_id) % 1009
        loc_base = 4.0 + (loc_seed % 6)               # 4..9
        loc_amp = 0.85 + (loc_seed // 7 % 5) * 0.10   # 0.85..1.25

        # Continuity across day boundary: previous day's last hour seeds
        # this day's starting pm25, deterministically.
        prev_seed = int((target_date - timedelta(days=1)).strftime("%Y%m%d"))
        prev_rng = np.random.default_rng((prev_seed, int(location_id)))
        prev_pm = max(
            0.0,
            loc_base + loc_amp * _diurnal(23) + float(prev_rng.normal(0, 3))
        )

        # Rare multi-hour event: ~8% of days, lasting 4–10 hours.
        event_active = rng.random() < 0.08
        event_start = int(rng.integers(0, 20)) if event_active else -1
        event_len = int(rng.integers(4, 11)) if event_active else 0
        event_amp = float(rng.uniform(25.0, 55.0)) if event_active else 0.0

        for hour in range(24):
            ts = start + timedelta(hours=hour)
            target_level = (
                loc_base
                + loc_amp * _diurnal(hour)
                + seasonal_offset
            )
            if event_active and event_start <= hour < event_start + event_len:
                target_level += event_amp

            # AR(1) toward target_level. Weight 0.55 leaves enough
            # responsiveness for the diurnal target to push pm25 across the
            # unsafe threshold while preserving lag-feature autocorrelation.
            noise = float(rng.normal(0.0, 2.5))
            pm25 = max(0.0, 0.55 * prev_pm + 0.45 * target_level + noise)
            prev_pm = pm25

            rows.append(
                {
                    DATETIME_COL: ts,
                    "location_id": int(location_id),
                    "pm25": float(round(pm25, 2)),
                }
            )

    df = pd.DataFrame(rows, columns=[DATETIME_COL, "location_id", "pm25"])
    df[DATETIME_COL] = pd.to_datetime(df[DATETIME_COL], utc=True)
    df["location_id"] = df["location_id"].astype("int64")
    df["pm25"] = df["pm25"].astype("float64")
    return (
        df.sort_values([DATETIME_COL, "location_id"])
        .reset_index(drop=True)
    )


# --- CLI -----------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of history to seed (default: 30).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Last (most recent) date to seed, YYYY-MM-DD. Defaults to today UTC.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing raw CSVs instead of skipping them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = (
        datetime.fromisoformat(args.end_date)
        if args.end_date
        else datetime.now(timezone.utc).replace(tzinfo=None)
    )

    written = 0
    skipped = 0
    for offset in range(args.days, -1, -1):
        target = end_date - timedelta(days=offset)
        ds = target.strftime("%Y-%m-%d")
        out_path = DATA_RAW_DIR / f"pm25_{ds}.csv"
        if out_path.exists() and not args.force:
            print(f"skip   {out_path} (exists)")
            skipped += 1
            continue
        df = generate_synthetic_pm25(ds)
        save_raw_pm25(df, ds)
        print(f"wrote  {out_path}  rows={len(df)}  unsafe={(df['pm25'] > 35.4).sum()}")
        written += 1

    print(f"\nDone — wrote {written} file(s), skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
