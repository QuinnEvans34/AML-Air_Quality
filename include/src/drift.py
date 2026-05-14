"""
drift.py — PM2.5 drift detection for AirAlert (W7A1 Part 2).

Owner:    Quinton Evans (QE)
Reviewer: Gracelyn Jarrett (GJ)

This module compares a recent window of raw PM2.5 readings against a
reference distribution drawn from the prior ``DRIFT_REFERENCE_DAYS`` of
raw data, per location. It is invoked by the ``check_drift`` task in
``dags/airalert_dag.py`` between ``engineer_features`` and
``retrain_model``.

Pipeline shape (per call):

    raw pm25 history (ds-7..ds-1) + today's pm25_{ds}.csv
        -> for each TARGET_LOCATIONS entry:
              load the two series, drop NaN pm25
              -> compute mean_shift_sigma =
                     (recent.mean() - reference.mean()) / reference.std()
              -> drifted = |mean_shift_sigma| > DRIFT_SIGMA_THRESHOLD
        -> assemble verdicts dict (one entry per location + global flag)
        -> log to MLflow under run name "drift_{ds}" (best-effort)
        -> write include/data/drift/drift_{ds}.json
        -> return JSON path string for XCom

Decision context (see INTERFACE.md)
-----------------------------------
- Decision 3 — Retraining trigger: drift is layered on top of the
  existing Monday backstop and the F1 < 0.70 floor. Per-location
  ``drifted = True`` is the third retrain trigger, applied inside
  ``_per_location_decisions`` in the DAG.
- Decision 6 — Per-location models: drift is computed independently per
  location_id; the global flag is ``any(per_location[*].drifted)``.

Inputs
------
- ds         YYYY-MM-DD execution date string from Airflow context.
- Raw CSVs at include/data/raw/pm25_{date}.csv for the reference window
  and the recent window. Missing reference-window files are tolerated
  (the resulting drift verdict is marked ``inconclusive``); a missing
  recent file is a contract violation and raises ``FileNotFoundError``.

Outputs
-------
- include/data/drift/drift_{ds}.json — verdict dict matching the shape
  documented in docs/drift_implementation_plan.md.
- One MLflow run named ``drift_{ds}`` under experiment
  ``MLFLOW_EXPERIMENT``, with per-location ``mean_shift_sigma_*`` and
  ``drifted_*`` metrics, plus a ``global_drifted`` metric.

Constraints
-----------
- Drift reads raw ``pm25``, never the engineered features CSV. The
  recent window therefore contains ~24 rows per location (one full day
  of hourly readings); the reference window contains ~24 *
  ``DRIFT_REFERENCE_DAYS`` rows per location.
- Sparse-window guard: if ``len(reference) < _MIN_REFERENCE_ROWS`` (24)
  or ``len(recent) < 1``, the verdict for that location is forced to
  ``mean_shift_sigma = 0.0``, ``drifted = False``, ``inconclusive =
  True``. This prevents false-positive drift on backfill or outage days.
- Zero-std reference guard: if ``reference.std(ddof=0) == 0`` or is
  non-finite (a flat-lined sensor), same guard applies — no divide-by-zero.
- MLflow logging is best-effort. The JSON is always written even if
  MLflow is unreachable, and the ``AIRALERT_SKIP_MLFLOW`` env flag
  (same flag honored by ``train.py``) skips MLflow entirely.

Error behavior
--------------
- ``ds`` not YYYY-MM-DD                   -> ValueError
- Missing recent raw file                  -> FileNotFoundError
- Empty / NaN-only recent file             -> inconclusive verdict (no raise)
- MLflow tracking server unreachable       -> warning log, JSON still written
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from include.src.constants import (
    DATETIME_COL,
    DRIFT_RECENT_DAYS,
    DRIFT_REFERENCE_DAYS,
    DRIFT_SIGMA_THRESHOLD,
    MLFLOW_EXPERIMENT,
    MLFLOW_URI,
    TARGET_LOCATIONS,
)


# --- Module-level constants -----------------------------------------------

DATA_RAW_DIR:   Path = Path("include/data/raw")
DRIFT_DATA_DIR: Path = Path("include/data/drift")

# Minimum reference-window row count per location before we trust the
# sigma. Below this we mark the verdict inconclusive — the assignment's
# 2σ threshold loses meaning on a handful of points.
_MIN_REFERENCE_ROWS: int = 24

_DS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

logger = logging.getLogger(__name__)


# --- Helpers --------------------------------------------------------------

def _date_window(ds: str, min_offset: int, max_offset: int) -> list[datetime]:
    """
    Build the list of dates [ds - max_offset .. ds - min_offset], inclusive.

    Used by ``compute_drift_verdicts`` to enumerate the calendar dates
    of the raw files to load for the reference and recent windows. The
    offset arithmetic is explicit per window:

    - Reference window (e.g. ``DRIFT_REFERENCE_DAYS = 7``):
      ``_date_window(ds, min_offset=1, max_offset=7)`` → seven dates
      ``[ds - 7 .. ds - 1]``, exclusive of today. Today's pm25 must
      never appear in the reference distribution — including it would
      bias the reference toward the day we are testing for drift.
    - Recent window (e.g. ``DRIFT_RECENT_DAYS = 1``):
      ``_date_window(ds, min_offset=0, max_offset=0)`` → one date
      ``[ds]``. With ``DRIFT_RECENT_DAYS = 2`` it would expand to
      ``[ds - 1, ds]``.

    Args:
        ds: YYYY-MM-DD execution date string.
        min_offset: Smallest day offset to include (0 means today,
            1 means yesterday).
        max_offset: Largest day offset to include (must be >= ``min_offset``).

    Returns:
        List of ``datetime`` objects in descending offset order (oldest
        first). Empty list if ``max_offset < min_offset``.
    """
    if max_offset < min_offset:
        return []
    anchor = datetime.strptime(ds, "%Y-%m-%d")
    return [
        anchor - timedelta(days=offset)
        for offset in range(max_offset, min_offset - 1, -1)
    ]


def _load_pm25_for_dates(dates: list[datetime]) -> pd.DataFrame:
    """
    Concat raw ``pm25_{date}.csv`` files for the given dates; drop NaN pm25.

    Skips files that do not exist on disk rather than raising — the
    caller (the sparse-window guard inside ``_compute_location_drift``)
    converts an empty result into an ``inconclusive = True`` verdict.

    Args:
        dates: List of ``datetime`` objects whose dates name the raw
            files to read (one per day, format ``pm25_{YYYY-MM-DD}.csv``).

    Returns:
        Concatenated DataFrame with columns
        ``[timestamp, location_id, pm25]``. Empty DataFrame with the
        same column shape if no files in the list exist on disk.

    Raises:
        None. Missing files are silently skipped; corrupt CSVs propagate
        the pandas error to the caller.
    """
    frames: list[pd.DataFrame] = []
    for d in dates:
        candidate = DATA_RAW_DIR / f"pm25_{d.strftime('%Y-%m-%d')}.csv"
        if not candidate.exists():
            continue
        frame = pd.read_csv(candidate)
        if frame.empty:
            continue
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=[DATETIME_COL, "location_id", "pm25"])

    combined = pd.concat(frames, ignore_index=True)
    # Drop NaN pm25 here so callers operate on the same Decision-2-clean
    # series that train.py sees downstream.
    combined = combined.dropna(subset=["pm25"]).reset_index(drop=True)
    return combined


def _compute_location_drift(
    reference: pd.Series, recent: pd.Series
) -> dict[str, Any]:
    """
    Compute per-location drift statistics from two pm25 series.

    Implements both sparse-window and zero-std guards: when the
    reference is too small or has zero variance, the verdict is forced
    to ``mean_shift_sigma = 0.0``, ``drifted = False``,
    ``inconclusive = True``. This is the leading-indicator behavior
    described in docs/drift_implementation_plan.md.

    Args:
        reference: pm25 values (float) for one ``location_id`` over the
            reference window (typically ds-7..ds-1).
        recent: pm25 values (float) for the same ``location_id`` over
            the recent window (typically ds).

    Returns:
        Dict with these keys:

        - ``reference_mean`` (float): mean of the reference series, or
          ``0.0`` when the series is empty.
        - ``reference_std`` (float): population std (``ddof=0``), or
          ``0.0`` when the series is empty.
        - ``recent_mean`` (float): mean of the recent series, or
          ``0.0`` when the series is empty.
        - ``n_reference`` (int): row count of the reference series.
        - ``n_recent`` (int): row count of the recent series.
        - ``mean_shift_sigma`` (float): ``(recent_mean - reference_mean)
          / reference_std`` when the guards pass; ``0.0`` otherwise.
        - ``drifted`` (bool): ``|mean_shift_sigma| > DRIFT_SIGMA_THRESHOLD``
          and not inconclusive.
        - ``inconclusive`` (bool): True when any guard fires.

    Raises:
        None. All edge cases fall through to ``inconclusive = True``.
    """
    n_reference = int(len(reference))
    n_recent = int(len(recent))

    ref_mean = float(reference.mean()) if n_reference > 0 else 0.0
    ref_std = float(reference.std(ddof=0)) if n_reference > 0 else 0.0
    recent_mean = float(recent.mean()) if n_recent > 0 else 0.0

    inconclusive = False
    sigma = 0.0
    drifted = False

    if n_reference < _MIN_REFERENCE_ROWS:
        inconclusive = True
    elif n_recent < 1:
        inconclusive = True
    elif ref_std == 0.0 or not np.isfinite(ref_std):
        inconclusive = True
    else:
        sigma = (recent_mean - ref_mean) / ref_std
        if not np.isfinite(sigma):
            inconclusive = True
            sigma = 0.0
        else:
            drifted = abs(sigma) > DRIFT_SIGMA_THRESHOLD

    return {
        "reference_mean": ref_mean,
        "reference_std": ref_std,
        "recent_mean": recent_mean,
        "n_reference": n_reference,
        "n_recent": n_recent,
        "mean_shift_sigma": float(sigma),
        "drifted": bool(drifted),
        "inconclusive": bool(inconclusive),
    }


# --- Public entry points --------------------------------------------------

def compute_drift_verdicts(ds: str) -> dict[str, Any]:
    """
    Compute the full drift verdict dict for one execution date.

    Reads ``DRIFT_REFERENCE_DAYS`` of prior raw pm25 history and the
    single ``pm25_{ds}.csv`` recent file, partitions by ``location_id``,
    and computes per-location drift statistics via
    ``_compute_location_drift``. Aggregates into the JSON shape
    documented in docs/drift_implementation_plan.md.

    Args:
        ds: YYYY-MM-DD execution date string from Airflow context.

    Returns:
        Dict matching the drift JSON schema:

        - ``ds`` (str)
        - ``reference_window_days`` (int) — value of ``DRIFT_REFERENCE_DAYS``
        - ``recent_window_days`` (int) — value of ``DRIFT_RECENT_DAYS``
        - ``sigma_threshold`` (float) — value of ``DRIFT_SIGMA_THRESHOLD``
        - ``global_drifted`` (bool) — True iff any per-location drifted is True
        - ``per_location`` (dict[str, dict]): one entry per
          ``TARGET_LOCATIONS`` key with the keys returned by
          ``_compute_location_drift``.

    Raises:
        ValueError: ``ds`` is not YYYY-MM-DD.
        FileNotFoundError: today's raw file
            ``include/data/raw/pm25_{ds}.csv`` is missing — this is a
            contract violation upstream, not a drift-check problem.
    """
    if not isinstance(ds, str) or not _DS_RE.match(ds):
        raise ValueError(f"ds must be a YYYY-MM-DD string; got {ds!r}")

    recent_path = DATA_RAW_DIR / f"pm25_{ds}.csv"
    if not recent_path.exists():
        raise FileNotFoundError(
            f"Recent raw file missing: {recent_path} — drift cannot proceed"
        )

    # Reference: [ds - DRIFT_REFERENCE_DAYS .. ds - 1], exclusive of today.
    # Recent:    [ds - (DRIFT_RECENT_DAYS - 1) .. ds], inclusive of today.
    reference_dates = _date_window(
        ds,
        min_offset=1,
        max_offset=DRIFT_REFERENCE_DAYS,
    )
    recent_dates = _date_window(
        ds,
        min_offset=0,
        max_offset=max(DRIFT_RECENT_DAYS - 1, 0),
    )

    reference_df = _load_pm25_for_dates(reference_dates)
    recent_df = _load_pm25_for_dates(recent_dates)

    per_location: dict[str, dict[str, Any]] = {}
    global_drifted = False

    for location_key, location_id in TARGET_LOCATIONS.items():
        if location_id is None:
            raise ValueError(
                f"TARGET_LOCATIONS[{location_key!r}] is None — populate "
                "constants.py before running drift_check_task"
            )

        ref_series = (
            reference_df.loc[reference_df["location_id"] == location_id, "pm25"]
            if not reference_df.empty
            else pd.Series(dtype="float64")
        )
        recent_series = (
            recent_df.loc[recent_df["location_id"] == location_id, "pm25"]
            if not recent_df.empty
            else pd.Series(dtype="float64")
        )

        verdict = _compute_location_drift(ref_series, recent_series)
        per_location[location_key] = verdict
        if verdict["drifted"]:
            global_drifted = True

        if verdict["inconclusive"]:
            logger.warning(
                "Drift verdict for %s on %s is inconclusive "
                "(n_reference=%d, n_recent=%d, reference_std=%.4f); "
                "treating as drifted=False.",
                location_key,
                ds,
                verdict["n_reference"],
                verdict["n_recent"],
                verdict["reference_std"],
            )

    return {
        "ds": ds,
        "reference_window_days": int(DRIFT_REFERENCE_DAYS),
        "recent_window_days": int(DRIFT_RECENT_DAYS),
        "sigma_threshold": float(DRIFT_SIGMA_THRESHOLD),
        "global_drifted": bool(global_drifted),
        "per_location": per_location,
    }


def log_drift_to_mlflow(verdicts: dict[str, Any], ds: str) -> str | None:
    """
    Log the drift verdict dict to MLflow under run name ``drift_{ds}``.

    Best-effort: MLflow client failures and the ``AIRALERT_SKIP_MLFLOW``
    env flag both short-circuit this function. This matches the
    error-handling pattern in ``include.src.train.log_run_to_mlflow``.

    Logs:
        Params  — ``ds``, ``reference_window_days``, ``recent_window_days``,
                  ``sigma_threshold``, plus per-location row counts
                  ``n_reference_<location_key>`` and ``n_recent_<location_key>``.
        Metrics — per-location ``mean_shift_sigma_<location_key>`` and
                  ``drifted_<location_key>`` (0/1), plus the aggregate
                  ``global_drifted`` (0/1).

    Args:
        verdicts: Dict returned by ``compute_drift_verdicts``.
        ds: YYYY-MM-DD execution date string.

    Returns:
        The MLflow ``run_id`` string when logging succeeded, or ``None``
        when MLflow logging was skipped (env flag set) or failed
        (warning logged).

    Raises:
        None. All MLflow exceptions are caught and converted to a
        warning log line so the upstream task always succeeds.
    """
    if os.environ.get("AIRALERT_SKIP_MLFLOW", "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        logger.info(
            "AIRALERT_SKIP_MLFLOW set; skipping MLflow drift run for %s", ds
        )
        return None

    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)

        params: dict[str, Any] = {
            "ds": verdicts["ds"],
            "reference_window_days": verdicts["reference_window_days"],
            "recent_window_days": verdicts["recent_window_days"],
            "sigma_threshold": verdicts["sigma_threshold"],
        }
        metrics: dict[str, float] = {
            "global_drifted": 1.0 if verdicts["global_drifted"] else 0.0,
        }
        for location_key, per_loc in verdicts["per_location"].items():
            params[f"n_reference_{location_key}"] = per_loc["n_reference"]
            params[f"n_recent_{location_key}"] = per_loc["n_recent"]
            metrics[f"mean_shift_sigma_{location_key}"] = float(
                per_loc["mean_shift_sigma"]
            )
            metrics[f"drifted_{location_key}"] = (
                1.0 if per_loc["drifted"] else 0.0
            )

        with mlflow.start_run(run_name=f"drift_{ds}") as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            return run.info.run_id

    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(
            "MLflow drift logging failed for %s (%s: %s); "
            "drift JSON is still written to disk",
            ds, type(exc).__name__, exc,
        )
        return None


def drift_check_task(ds: str) -> str:
    """
    Airflow entry point: compute drift verdicts, log MLflow, write JSON.

    This function is called by the ``check_drift`` task in
    ``dags/airalert_dag.py``. Per the project's XCom convention
    (``.github/copilot-instructions.md``), it returns a file path string
    rather than a DataFrame or dict.

    The DAG task is responsible for the file-exists idempotency check;
    this function always recomputes when called.

    Args:
        ds: YYYY-MM-DD execution date string from Airflow context.

    Returns:
        Absolute path string to ``include/data/drift/drift_{ds}.json``.

    Raises:
        ValueError: ``ds`` is not YYYY-MM-DD.
        FileNotFoundError: today's raw file
            ``include/data/raw/pm25_{ds}.csv`` is missing.
    """
    verdicts = compute_drift_verdicts(ds)

    # MLflow first so a logging hiccup doesn't strand us between a
    # successful compute and a written JSON. The function is best-effort
    # and never raises.
    log_drift_to_mlflow(verdicts, ds)

    DRIFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DRIFT_DATA_DIR / f"drift_{ds}.json"
    output_path.write_text(json.dumps(verdicts, indent=2))

    logger.info(
        "Drift check for %s: global_drifted=%s; per-location sigmas: %s",
        ds,
        verdicts["global_drifted"],
        {k: round(v["mean_shift_sigma"], 3) for k, v in verdicts["per_location"].items()},
    )

    return str(output_path)
