"""
bootstrap_train.py — train and promote AirAlert models for local dev.

Usage:
    python3 scripts/bootstrap_train.py [YYYY-MM-DD]

What it does:
    1. Ensures features_{ds}.csv exists for the requested ds (builds it
       from raw if needed).
    2. Calls retrain_task to train all three location models, log them
       to MLflow, and (via the Phase 1a promotion block in
       train.py.log_run_to_mlflow) transition them to the Production
       stage.
    3. Prints a short summary so the operator knows the next step.

When to use it:
    - The Astro DAG is the canonical training entry point and is what
      runs every day at 06:00 UTC in production.
    - This script is the FAST PATH for local dev: when you've wiped
      mlflow.db (or are setting up a fresh laptop) and need models in
      the registry before booting uvicorn, you don't want to spin up
      Astro just for that one bootstrap.
    - It's idempotent — safe to re-run. Re-running just registers a
      new version and promotes it to Production, archiving the prior
      Production version.

Pre-requisites:
    - MLflow tracking server already running at
      $MLFLOW_TRACKING_URI (default: http://localhost:5001).
    - Raw pm25_{ds-N..ds}.csv files already on disk under
      include/data/raw/ (these come from ingest.py runs).

After it succeeds:
    1. Visit the MLflow UI Models tab — each AirAlert_<loc> should
       have a version at Stage: Production.
    2. Start FastAPI: uvicorn include.src.serve:app --reload --port 8000
    3. Start the dashboard: cd app/dashboard && npm run dev
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Default to the host MLflow server. Override via env if your setup differs.
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5001")

# Make INFO log lines visible so the user sees "Promoted ... to Production"
# from train.py's promotion block. Without this, the messages get filtered
# by Python's default WARNING threshold.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)

# Imports happen after env var setup so include.src.constants.MLFLOW_URI
# picks up the right value.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from include.src.constants import TARGET_LOCATIONS  # noqa: E402
from include.src.train import retrain_task  # noqa: E402
from include.src.transform import build_features  # noqa: E402


def _today_iso_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _ensure_features_csv(ds: str) -> Path:
    """
    Always rebuild features_{ds}.csv from raw.

    We deliberately do NOT short-circuit if the features file already
    exists on disk. The bootstrap script's contract is "train fresh
    from the current state of include/data/raw/ and the current value
    of transform.py's _HISTORY_DAYS." Reusing a stale features file
    would silently train against an obsolete window — that's exactly
    the bug that caused F1 to collapse on the first bootstrap run.
    """
    features_path = Path("include/data/features") / f"features_{ds}.csv"
    raw_path = Path("include/data/raw") / f"pm25_{ds}.csv"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Missing raw file for {ds}: {raw_path}\n"
            f"  Run the ingest task first (or pick a date that has raw data)."
        )

    if features_path.exists():
        print(f"  • removing stale {features_path} so it is rebuilt …")
        features_path.unlink()

    print(f"  • building features_{ds}.csv from {raw_path} …")
    out = build_features(raw_data_path=raw_path, output_path=features_path)
    print(f"  • wrote {out}")
    return Path(out)


def _print_summary(metrics: dict) -> None:
    print()
    print("=" * 64)
    print("Training complete")
    print("=" * 64)
    print(f"  aggregate F1:          {metrics['f1']:.3f}")
    print(f"  aggregate accuracy:    {metrics['accuracy']:.3f}")
    print(f"  aggregate precision:   {metrics['precision']:.3f}")
    print(f"  aggregate recall:      {metrics['recall']:.3f}")
    print(f"  naive baseline F1:     {metrics['baseline_f1']:.3f}")
    print()
    print("Per-location:")
    for loc in TARGET_LOCATIONS:
        m = metrics["per_location"].get(loc, {})
        print(
            f"  {loc:>12s}: "
            f"f1={m.get('f1', 0):.3f}  "
            f"precision={m.get('precision', 0):.3f}  "
            f"recall={m.get('recall', 0):.3f}  "
            f"FN={m.get('false_negatives', 0)}  "
            f"TP={m.get('true_positives', 0)}"
        )
    print()
    print("Next steps:")
    print("  1. Open http://localhost:5001 → Models tab. Confirm three")
    print("     AirAlert_* entries are at stage: Production.")
    print("  2. In a new terminal, start FastAPI:")
    print(
        "       export MLFLOW_TRACKING_URI="
        + os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
    )
    print("       uvicorn include.src.serve:app --reload --port 8000")
    print("  3. In another terminal:")
    print("       cd app/dashboard && npm run dev")
    print()


def main() -> int:
    ds = sys.argv[1] if len(sys.argv) > 1 else _today_iso_utc()
    print(f"Bootstrap training for ds={ds}")
    print(f"MLflow tracking URI = {os.environ['MLFLOW_TRACKING_URI']}")
    print()

    features_path = _ensure_features_csv(ds)
    print()
    print(f"Training all three locations on {features_path} …")
    metrics = retrain_task(features_path=str(features_path), ds=ds)
    _print_summary(metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
