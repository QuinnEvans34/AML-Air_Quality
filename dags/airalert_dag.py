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

from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


RAW_DATA_DIR      = Path("include/data/raw")
FEATURES_DATA_DIR = Path("include/data/features")
MODELS_DIR        = Path("include/models")


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
                        (raised inside transform_task).
        """
        ctx = get_current_context()
        ds = ctx["ds"]
        output_path = FEATURES_DATA_DIR / f"features_{ds}.csv"

        if output_path.exists():
            return str(output_path)

        from include.src.transform import transform_task
        return transform_task(input_path=validated_path, **ctx)

    @task
    def retrain_model(features_path: str) -> dict:
        """
        Retrain the per-location classifiers and register them in MLflow.

        Args:
            features_path: file path string from engineer_features.

        Returns:
            Metrics dict with keys: f1, baseline_f1, accuracy, precision, recall.
            Visible in XCom for the Part 4 verification.

        Raises:
            ValueError: if features_path is missing or empty
                        (raised inside retrain_task).
        """
        import json

        ctx = get_current_context()
        ds = ctx["ds"]
        metrics_path = MODELS_DIR / f"metrics_{ds}.json"

        if metrics_path.exists():
            return json.loads(metrics_path.read_text())

        from include.src.train import retrain_task
        metrics = retrain_task(features_path=features_path, ds=ds)

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics))
        return metrics

    raw       = fetch_air_quality()
    validated = validate_schema(raw)
    features  = engineer_features(validated)
    retrain_model(features)


airalert_pipeline()
