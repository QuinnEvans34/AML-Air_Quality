"""
train.py — Per-location classifier training and MLflow registration.

Owner:    Quinton Evans (QE)
Reviewer: Gracelyn Jarrett (GJ)

This module trains one logistic-regression classifier per location in
TARGET_LOCATIONS, registers each in MLflow, saves a unified bundle to
``include/models/latest_model.pkl``, and returns a dict of metrics for
Airflow XCom. It is invoked by the ``retrain_model`` task in
``dags/airalert_dag.py``.

Pipeline shape (per call):

    Contract-2 features CSV
        -> split by location_id
            -> for each location:
                  chronological 80/20 split
                  -> train logistic regression with class_weight='balanced'
                  -> compute metrics on the holdout
                  -> log run + register model in MLflow as AirAlert_<location>
            -> bundle all three models into a dict
            -> save dict to include/models/latest_model.pkl
        -> aggregate metrics (mean across locations)
        -> return aggregated dict to Airflow XCom

Decision context (see INTERFACE.md)
-----------------------------------
- Decision 3 — Retraining trigger:  this module trains unconditionally
  when invoked. The DAG decides *when* to invoke (weekly Monday or on a
  detected false negative from the prior day's predictions). FN-trigger
  detection logic is not implemented in this PR — it requires a
  predictions log from serve.py, which is future work.
- Decision 6 — Per-location models: three independent classifiers, one
  per (location_key, location_id) pair in TARGET_LOCATIONS.
- Decision 7 — Classifier choice: logistic regression for v1; chosen
  because predict_proba is reasonably calibrated for this feature set
  and the model is fast to train and easy to explain.

Inputs
------
- features_path  Path string to a Contract-2 CSV (the output of
                 transform.py / engineer_features task).
- ds             YYYY-MM-DD execution date string from Airflow context.

Outputs
-------
- include/models/latest_model.pkl                 — dict of three sklearn estimators
- include/models/{location_key}_{ds}.pkl          — per-location date-stamped
- MLflow runs under experiment MLFLOW_EXPERIMENT   — one per location
- Returned dict (XCom value) with keys:
    f1, baseline_f1, accuracy, precision, recall,
    false_negatives, true_positives

Constraints
-----------
- Class imbalance: every classifier uses class_weight='balanced'.
  Without it the model collapses to "always predict safe" given the
  ~0.6% positive class rate.
- Chronological split, not random — time-series data must not have
  future bleed into the training set.
- F1 is computed with pos_label=1 and zero_division=0 (some holdout
  windows have no unsafe hours).
- FEATURE_COLS comes from include/src/constants.py — never hardcoded
  here, so Contract 3 stays the single source of truth.

Error behavior
--------------
- features_path missing or empty           -> FileNotFoundError / ValueError
- A location has fewer than ~50 rows
  in the features CSV (too sparse to split) -> ValueError per location
- MLflow tracking server unreachable        -> mlflow client error
                                              (not caught — fail loud)
- joblib pickling failure on the bundle     -> propagates

Future work
-----------
- FN-triggered retrain logic — needs predictions log from serve.py
- Calibration of predict_proba — sklearn's
  CalibratedClassifierCV may be added in a follow-up PR
- Promote-on-improvement gating — currently every call overwrites
  latest_model.pkl unconditionally; a future version may compare new
  metrics to MLflow's current "Production" model and only swap on
  improvement.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from include.src.constants import (
    MLFLOW_EXPERIMENT,
    MLFLOW_URI,
    MODEL_NAME_TEMPLATE,
    TARGET_LOCATIONS,
)

# Heavy libs (sklearn, mlflow, joblib) are imported lazily inside the
# functions that use them so DAG parsing stays fast.
if TYPE_CHECKING:
    from sklearn.linear_model import LogisticRegression


# --- Module-level constants -----------------------------------------------

MODELS_DIR: Path = Path("include/models")
TEST_FRACTION: float = 0.20  # last 20% of each location's rows -> holdout
LATEST_MODEL_FILENAME: str = "latest_model.pkl"

# FEATURE_COLS — sourced from Contract 3 in INTERFACE.md.
# Imported here from constants once Contract 3 / FEATURE_COLS lives there;
# until then, declared locally and kept exactly in sync with INTERFACE.md.
FEATURE_COLS: list[str] = [
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
TARGET_COL: str = "is_unsafe"


# --- Data loading and splitting -------------------------------------------

def load_features(path: Path) -> pd.DataFrame:
    """
    Read and validate a Contract-2 features CSV.

    Reads the CSV at ``path`` with ``timestamp`` parsed as a datetime,
    then verifies that every required column for downstream training is
    present and non-null. The required columns are ``timestamp``,
    ``location_id``, ``TARGET_COL`` (``is_unsafe``), and every name in
    ``FEATURE_COLS`` (the nine engineered features defined by
    Contract 3 in INTERFACE.md). Failing fast here keeps malformed
    upstream output from poisoning training.

    Args:
        path: Filesystem path to a Contract-2 features CSV produced by
            ``transform.py`` (typically
            ``include/data/features/features_{ds}.csv``). May be passed
            as ``str`` or ``Path``; will be normalized to ``Path``.

    Returns:
        A ``pandas.DataFrame`` containing all required columns with no
        nulls in those columns. Other columns from the CSV are
        preserved but not validated.

    Raises:
        FileNotFoundError: ``path`` does not exist on disk.
        ValueError: One or more required columns are missing from the
            CSV, or one or more required columns contain nulls. The
            error message lists every offender (and per-column null
            counts on the null path).
    """


def split_by_location(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """
    Partition a Contract-2 DataFrame into one DataFrame per location.

    Decision 6 in INTERFACE.md commits us to three independent
    per-location classifiers. This helper groups the unified features
    DataFrame by ``location_id`` and emits a dict suitable for the
    per-location loop in ``retrain_task``. Each per-location frame is
    sorted ascending by ``timestamp`` so the chronological split
    downstream is deterministic.

    Args:
        df: Validated Contract-2 features DataFrame as returned by
            ``load_features``.

    Returns:
        A dict mapping each ``location_id`` (int, drawn from
        ``TARGET_LOCATIONS.values()``) to that location's rows, sorted
        ascending by ``timestamp``. Exactly one key per entry in
        ``TARGET_LOCATIONS``.

    Raises:
        ValueError: The set of ``location_id`` values present in ``df``
            does not match the set of ids in ``TARGET_LOCATIONS.values()``
            (either an extra unknown id appears, or one of the three
            target locations is missing from the data).
    """


def chronological_split(
    df: pd.DataFrame, test_fraction: float = TEST_FRACTION
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Split a per-location DataFrame chronologically into train and test.

    Time-series data must never be random-shuffled — leaking future
    rows into the training set inflates metrics and produces a model
    that cannot generalize forward in time. This function takes the
    last ``test_fraction`` of rows (sorted ascending by ``timestamp``)
    as the holdout and the remaining earlier rows as the training set.
    With ``test_fraction = TEST_FRACTION = 0.20`` this is a chronological
    80/20 split per location.

    Args:
        df: A per-location DataFrame (one of the values from
            ``split_by_location``). Already sorted by ``timestamp``;
            this function re-sorts defensively in case a caller passes
            an unsorted frame.
        test_fraction: Proportion of rows (taken from the tail of the
            time-sorted frame) reserved for the holdout. Defaults to
            ``TEST_FRACTION`` (0.20).

    Returns:
        A 4-tuple ``(X_train, X_test, y_train, y_test)`` where:

        - ``X_train`` and ``X_test`` are DataFrames containing only the
          columns in ``FEATURE_COLS``.
        - ``y_train`` and ``y_test`` are integer Series of ``TARGET_COL``
          values (0 for safe, 1 for unsafe).

    Raises:
        ValueError: With message ``"Not enough rows for chronological
            split"`` when the implied training cutoff would be fewer
            than 24 rows (less than roughly one day of training data).
    """


# --- Modeling and metrics -------------------------------------------------

def train_logistic_regression(
    X_train: pd.DataFrame, y_train: pd.Series
) -> "LogisticRegression":
    """
    Fit a class-balanced logistic regression classifier (Decision 7).

    The classifier is configured with ``class_weight="balanced"`` —
    this is non-negotiable for AirAlert. With a positive-class rate
    around 0.6% on Utah PM2.5 data, an unweighted classifier collapses
    to "always predict safe" and recall on the unsafe class drops to
    zero. ``max_iter=1000`` gives the LBFGS solver enough room to
    converge on the engineered features, and ``random_state=0`` makes
    the fit reproducible.

    Args:
        X_train: Training features. Columns must equal ``FEATURE_COLS``.
        y_train: Training targets — 0 for safe hours, 1 for unsafe.

    Returns:
        A fitted ``sklearn.linear_model.LogisticRegression`` instance,
        ready for ``predict`` / ``predict_proba``.
    """


def compute_metrics(
    model: "LogisticRegression",
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, float | int]:
    """
    Score a fitted model on its holdout and return AirAlert's metric set.

    Computes the five metrics required by the assignment (``f1``,
    ``baseline_f1``, ``accuracy``, ``precision``, ``recall``) plus the
    two decision-relevant counts called out by Decision 3
    (``false_negatives``, ``true_positives``) — a missed unsafe hour is
    the costly error mode for an air-quality alert system, so we surface
    the raw FN/TP counts alongside the rate metrics. F1, precision, and
    recall are computed on the unsafe class with ``pos_label=1`` and
    ``zero_division=0`` — the latter matters because some holdout
    windows contain no positives.

    Args:
        model: A classifier fitted by ``train_logistic_regression``.
        X_test: Holdout features. Columns must equal ``FEATURE_COLS``.
        y_test: Holdout targets (0 / 1).

    Returns:
        A dict with the following keys:

        - ``f1`` (float)              — F1 of the unsafe class.
        - ``baseline_f1`` (float)     — F1 of the always-predict-safe
          baseline (will be 0.0 by definition; the model must beat it).
        - ``accuracy`` (float)        — Overall accuracy.
        - ``precision`` (float)       — Precision on the unsafe class.
        - ``recall`` (float)          — Recall on the unsafe class.
        - ``false_negatives`` (int)   — Count of unsafe hours predicted safe.
        - ``true_positives`` (int)    — Count of unsafe hours predicted unsafe.
    """


def baseline_f1_score(y_test: pd.Series) -> float:
    """
    F1 of the trivial "always predict safe" baseline on the holdout.

    The baseline predicts class 0 for every row. Its F1 on the unsafe
    class is therefore 0.0 by construction (no true positives, so
    precision and recall are both 0). Reporting it alongside the
    model's F1 makes the lift over the trivial baseline explicit — any
    real model has to beat zero.

    Args:
        y_test: Holdout targets (0 / 1).

    Returns:
        ``0.0`` in essentially every case. Computed via
        ``f1_score(..., pos_label=1, zero_division=0)`` so the
        all-zero-predictions edge case does not raise.
    """


# --- MLflow + persistence -------------------------------------------------

def log_run_to_mlflow(
    model: "LogisticRegression",
    metrics: dict[str, float | int],
    location_key: str,
    ds: str,
) -> str:
    """
    Log a per-location training run and register the model in MLflow.

    Per Decision 6, each of the three locations gets its own registered
    model in the MLflow Model Registry. This function configures the
    tracking server (``MLFLOW_URI``), selects the AirAlert experiment
    (``MLFLOW_EXPERIMENT``), opens a run named ``f"{location_key}_{ds}"``,
    logs run-identifying params and the full metrics dict, and finally
    registers the trained estimator under
    ``MODEL_NAME_TEMPLATE.format(location=location_key)`` — i.e.
    ``AirAlert_red_butte``, ``AirAlert_smithfield``, or
    ``AirAlert_ledges``. MLflow client failures are not caught here:
    if the tracking server is unreachable we want training to fail
    loudly rather than silently drop the registration step.

    Args:
        model: The fitted estimator from ``train_logistic_regression``.
        metrics: The dict returned by ``compute_metrics``. MLflow accepts
            both float and int metric values.
        location_key: One of ``"red_butte"``, ``"smithfield"``,
            ``"ledges"``. Used in the run name and as the substitution
            for ``{location}`` in ``MODEL_NAME_TEMPLATE``.
        ds: YYYY-MM-DD execution date string. Used in the run name and
            as a logged param so runs are searchable by date.

    Returns:
        The MLflow ``run_id`` (UUID string) for the run that was just
        created.

    Raises:
        Any ``mlflow`` client exception (e.g. connection error to the
        tracking URI, registry-permission errors) propagates uncaught.
    """


def save_model_bundle(
    models_by_location: dict[str, "LogisticRegression"], ds: str
) -> Path:
    """
    Persist all three trained models to disk — bundle plus per-location.

    Writes two kinds of artifacts under ``MODELS_DIR`` (``include/models``):

    1. Per-location, date-stamped pickles
       ``{location_key}_{ds}.pkl`` — one per location, useful for
       reproducing the exact model used on a given day.
    2. A single bundle pickle named ``LATEST_MODEL_FILENAME``
       (``latest_model.pkl``) containing the entire dict — this is the
       file ``serve.py`` (or the assignment's verification step) loads
       with ``joblib.load()`` to obtain all three classifiers.

    The bundle is overwritten unconditionally on each call; rolling
    back to a prior day's models is done via the date-stamped per-
    location files.

    Args:
        models_by_location: Dict keyed by ``location_key`` (one of
            ``"red_butte"``, ``"smithfield"``, ``"ledges"``) with
            fitted estimators as values. Must have exactly the three
            keys in ``set(TARGET_LOCATIONS)``.
        ds: YYYY-MM-DD execution date string used in the per-location
            filenames.

    Returns:
        The ``Path`` to the bundle file
        (``include/models/latest_model.pkl``).

    Raises:
        ValueError: ``models_by_location.keys()`` does not equal
            ``set(TARGET_LOCATIONS)``. The message lists missing and
            unexpected keys.
    """


# --- Airflow entry point --------------------------------------------------

def retrain_task(features_path: str, ds: str) -> dict:
    """
    Public entry point: train all three per-location models for ``ds``.

    This is the function imported and called by the ``retrain_model``
    task in ``dags/airalert_dag.py``. The signature is fixed by that
    caller and must not change. Per Decision 3, this function trains
    unconditionally whenever it is invoked — the DAG owns the question
    of *when* to retrain (weekly cadence plus on-FN trigger).

    Per call, it:

    1. Loads and validates the Contract-2 features CSV at
       ``features_path``.
    2. Splits the frame by ``location_id``.
    3. For each ``(location_key, location_id)`` in
       ``TARGET_LOCATIONS``, performs a chronological 80/20 split,
       fits a balanced logistic regression, scores it on the holdout,
       and registers the run in MLflow under
       ``MODEL_NAME_TEMPLATE.format(location=location_key)``.
    4. Saves a unified ``latest_model.pkl`` plus per-location
       date-stamped pickles under ``include/models/``.
    5. Aggregates metrics across locations: float metrics are
       averaged, integer counts (FN, TP) are summed. The returned
       dict is the XCom value for the downstream task.

    Args:
        features_path: Path string to a Contract-2 features CSV
            (typically the output of the upstream
            ``engineer_features`` task — i.e.
            ``include/data/features/features_{ds}.csv``). Must be a
            non-empty string.
        ds: Airflow execution date in ``YYYY-MM-DD`` format.

    Returns:
        An aggregated metrics dict with keys ``f1``, ``baseline_f1``,
        ``accuracy``, ``precision``, ``recall`` (floats — mean across
        the three locations) and ``false_negatives``, ``true_positives``
        (ints — sum across the three locations). Per-location detail
        is not in the return value; it lives in MLflow.

    Raises:
        ValueError: ``features_path`` is empty / not a string, or
            ``ds`` is not a YYYY-MM-DD string, or any downstream
            validation in ``load_features`` /
            ``split_by_location`` / ``chronological_split`` /
            ``save_model_bundle`` fails.
        FileNotFoundError: ``features_path`` does not exist.
        Exception: Any ``sklearn``, ``mlflow``, or ``joblib`` error
            from the underlying calls propagates uncaught — failures
            in training, registration, or persistence should fail
            the Airflow task loudly rather than silently produce an
            incomplete run.
    """
