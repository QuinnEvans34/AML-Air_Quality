"""
airalert_dag.py — Daily AirAlert pipeline.

Owner:    Quinton Evans (QE)
Reviewer: Gracelyn Jarrett (GJ)

Schedule: 06:00 UTC daily (cron `0 6 * * *`).

Pipeline (linear chain — TaskFlow API):

    fetch_air_quality        ->  include/data/raw/pm25_{ds}.csv
    validate_schema          ->  pass-through (Contract 1 assertions)
    engineer_features        ->  include/data/features/features_{ds}.csv
    retrain_model            ->  metrics dict in XCom + model artifacts on disk

Each task pulls the execution date from get_current_context()["ds"] and
checks for an existing output file before doing work (idempotency).

Pipeline scripts live in include/src/ and are imported lazily inside each
task to keep DAG-parse-time cheap.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


RAW_DATA_DIR      = Path("include/data/raw")
FEATURES_DATA_DIR = Path("include/data/features")
MODELS_DIR        = Path("include/models")


# --- Decision 3: per-location retrain trigger -----------------------------
# Source of truth for the design: docs/retrain_trigger_implementation_plan.md.
# Threshold and weekday come from include.src.constants so the DAG and the
# Shared Constants table in INTERFACE.md cannot drift.

def _read_latest_metrics() -> dict | None:
    """Return the most recent ``metrics_*.json`` contents, or ``None``."""
    files = sorted(MODELS_DIR.glob("metrics_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:  # noqa: BLE001 — corrupt file → treat as missing
        return None


def _per_location_decisions(ds: str) -> dict[str, tuple[bool, str]]:
    """
    Apply Decision 3 per location.

    Returns a dict mapping every key in ``TARGET_LOCATIONS`` to a
    ``(retrain: bool, reason: str)`` tuple. Order of precedence:

    1. Monday → retrain (weekly backstop).
    2. No previous metrics file at all → retrain (bootstrap).
    3. No previous per-location entry for this location → retrain (bootstrap).
    4. Previous F1 < ``F1_RETRAIN_THRESHOLD`` → retrain.
    5. Otherwise → skip.
    """
    from include.src.constants import (
        F1_RETRAIN_THRESHOLD,
        TARGET_LOCATIONS,
        WEEKLY_RETRAIN_WEEKDAY,
    )

    is_monday = (
        datetime.fromisoformat(ds).weekday() == WEEKLY_RETRAIN_WEEKDAY
    )
    prev = _read_latest_metrics() or {}
    prev_per_loc = prev.get("per_location") or {}

    decisions: dict[str, tuple[bool, str]] = {}
    for loc_key in TARGET_LOCATIONS:
        if is_monday:
            decisions[loc_key] = (True, "weekly Monday backstop")
            continue
        if not prev_per_loc:
            decisions[loc_key] = (True, "bootstrap (no prior metrics)")
            continue
        if loc_key not in prev_per_loc:
            decisions[loc_key] = (
                True, f"bootstrap (no prior {loc_key} metrics)"
            )
            continue
        f1 = float(prev_per_loc[loc_key].get("f1", 0.0))
        if f1 < F1_RETRAIN_THRESHOLD:
            decisions[loc_key] = (
                True,
                f"prior f1={f1:.3f} < threshold {F1_RETRAIN_THRESHOLD}",
            )
        else:
            decisions[loc_key] = (
                False,
                f"prior f1={f1:.3f} ≥ threshold {F1_RETRAIN_THRESHOLD}",
            )
    return decisions


@dag(
    dag_id="airalert_pipeline",
    description="Daily AirAlert PM2.5 ingestion → features → retrain pipeline",
    start_date=datetime(2026, 5, 1),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airalert-team",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        "depends_on_past": False,
    },
    tags=["airalert", "pm25", "production"],
)
def airalert_pipeline():
    @task
    def fetch_air_quality() -> str:
        """
        Ingest one day of PM2.5 readings for all TARGET_LOCATIONS via OpenAQ.

        Returns:
            Absolute path string to include/data/raw/pm25_{ds}.csv.

        Raises:
            ValueError:           if no readings were returned across all locations.
            requests.HTTPError:   on OpenAQ API failure (raised inside ingest_task).
        """
        ctx = get_current_context()
        ds = ctx["ds"]
        output_path = RAW_DATA_DIR / f"pm25_{ds}.csv"

        if output_path.exists():
            return str(output_path)

        from include.src.ingest import ingest_task
        return ingest_task(**ctx)

    @task
    def validate_schema(raw_path: str) -> str:
        """
        Assert Contract 1 schema on the raw CSV; pass-through on success.

        Args:
            raw_path: file path string from fetch_air_quality.

        Returns:
            The same raw_path (no transformation — pass-through pattern).

        Raises:
            FileNotFoundError: if raw_path does not exist on disk.
            ValueError:        if Contract 1 columns are missing, dtypes wrong,
                               or any null appears in a non-nullable column.
        """
        import pandas as pd

        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Upstream file missing: {raw_path}")

        df = pd.read_csv(path, parse_dates=["timestamp"])

        required = {"timestamp", "location_id", "pm25"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Contract 1 columns missing from {path}: {missing}")

        null_counts = df[list(required)].isna().sum()
        bad = null_counts[null_counts > 0].to_dict()
        if bad:
            raise ValueError(f"Nulls in Contract 1 output {path}: {bad}")

        if not pd.api.types.is_numeric_dtype(df["pm25"]):
            raise ValueError(f"pm25 is not numeric (dtype={df['pm25'].dtype})")
        if not pd.api.types.is_integer_dtype(df["location_id"]):
            raise ValueError(f"location_id is not integral (dtype={df['location_id'].dtype})")

        return raw_path

    @task
    def engineer_features(validated_path: str) -> str:
        """
        Build the Contract 2 feature matrix from validated raw data.

        Args:
            validated_path: file path string from validate_schema.

        Returns:
            Absolute path string to include/data/features/features_{ds}.csv.

        Raises:
            ValueError: if no rows survive feature computation
                        (raised inside build_features).
        """
        ctx = get_current_context()
        ds = ctx["ds"]
        output_path = FEATURES_DATA_DIR / f"features_{ds}.csv"

        if output_path.exists():
            return str(output_path)

        from include.src.transform import build_features
        return build_features(
            raw_data_path=Path(validated_path),
            output_path=output_path,
        )

    @task
    def retrain_model(features_path: str) -> dict:
        """
        Apply Decision 3 and (re)train per-location classifiers as needed.

        Per Decision 3 (see docs/retrain_trigger_implementation_plan.md):

        - Each location's model is retrained when its prior F1 on the unsafe
          class falls below ``F1_RETRAIN_THRESHOLD`` (0.70).
        - All three locations are retrained unconditionally on Mondays.
        - On bootstrap (no prior metrics file, or no prior entry for a given
          location), that location is retrained.

        On no-retrain days for a given location, the existing estimator and
        previous per-location metrics are carried forward into today's
        ``latest_model.pkl`` and ``metrics_{ds}.json`` respectively. Today's
        metrics file is **always** written so every date has documentation.

        Args:
            features_path: file path string from engineer_features.

        Returns:
            Aggregated metrics dict with rubric-required top-level keys
            (``f1``, ``baseline_f1``, ``accuracy``, ``precision``, ``recall``,
            ``false_negatives``, ``true_positives``) plus ``per_location``,
            ``retrain_history``, and ``retrain_decisions`` for audit.

        Idempotency:
            Skips the work only when BOTH ``include/models/metrics_{ds}.json``
            and ``include/models/latest_model.pkl`` already exist — guarantees
            cached metrics correspond to a real, loadable model bundle. Touch
            (delete) either file to force a rerun.

        Raises:
            ValueError: if features_path is missing or empty
                        (raised inside retrain_task).
        """
        log = logging.getLogger("airflow.task")

        ctx = get_current_context()
        ds = ctx["ds"]
        metrics_path = MODELS_DIR / f"metrics_{ds}.json"
        bundle_path  = MODELS_DIR / "latest_model.pkl"

        # Idempotency: both artifacts must already exist to short-circuit.
        if metrics_path.exists() and bundle_path.exists():
            log.info("Idempotency: %s and %s present, returning cached metrics.",
                     metrics_path, bundle_path)
            return json.loads(metrics_path.read_text())

        decisions = _per_location_decisions(ds)
        locations_to_retrain = [
            loc for loc, (retrain, _) in decisions.items() if retrain
        ]

        log.info("Decision 3 — retrain plan for %s:", ds)
        for loc, (retrain, reason) in decisions.items():
            log.info("  %s: %s (%s)",
                     loc, "retrain" if retrain else "skip", reason)

        from include.src.train import retrain_task
        metrics = retrain_task(
            features_path=features_path,
            ds=ds,
            locations_to_retrain=locations_to_retrain,
        )

        # Audit trail: include this run's per-location decisions in the dict
        # we serialize. retrain_history is set inside retrain_task.
        metrics["retrain_decisions"] = {
            loc: {"retrained": retrain, "reason": reason}
            for loc, (retrain, reason) in decisions.items()
        }

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics))
        return metrics

    raw       = fetch_air_quality()
    validated = validate_schema(raw)
    features  = engineer_features(validated)
    retrain_model(features)


airalert_pipeline()
