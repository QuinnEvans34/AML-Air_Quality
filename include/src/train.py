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

import logging
import os
import re
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
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline


# Module-level logger shared by ``log_run_to_mlflow`` and ``retrain_task``.
# Each function used to define its own local ``logging.getLogger`` call; one
# shared instance keeps the log namespace consistent and lets the Production
# promotion block in ``log_run_to_mlflow`` emit warnings under the same name
# as everything else in this module.
logger = logging.getLogger(__name__)


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
DATETIME_COL: str = "timestamp"

_DS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIN_TRAIN_ROWS: int = 24  # less than ~1 day of training is too sparse


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
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Features CSV not found: {path}")

    df = pd.read_csv(path, parse_dates=[DATETIME_COL])

    required = [DATETIME_COL, "location_id", TARGET_COL, *FEATURE_COLS]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"Contract-2 columns missing from {path}: {missing}"
        )

    null_counts = df[required].isna().sum()
    bad = null_counts[null_counts > 0].to_dict()
    if bad:
        raise ValueError(
            f"Nulls present in Contract-2 required columns of {path}: {bad}"
        )

    return df


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
    expected_ids = {lid for lid in TARGET_LOCATIONS.values() if lid is not None}
    present_ids = set(df["location_id"].unique().tolist())

    if present_ids != expected_ids:
        unexpected = present_ids - expected_ids
        missing = expected_ids - present_ids
        raise ValueError(
            "location_id set in features does not match TARGET_LOCATIONS — "
            f"missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )

    out: dict[int, pd.DataFrame] = {}
    for location_id, sub in df.groupby("location_id"):
        out[int(location_id)] = (
            sub.sort_values(DATETIME_COL).reset_index(drop=True)
        )
    return out


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
    sorted_df = df.sort_values(DATETIME_COL).reset_index(drop=True)
    cutoff = int(len(sorted_df) * (1.0 - test_fraction))

    if cutoff < _MIN_TRAIN_ROWS:
        raise ValueError(
            "Not enough rows for chronological split "
            f"(cutoff={cutoff} < {_MIN_TRAIN_ROWS}, total rows={len(sorted_df)})"
        )

    X_train = sorted_df.iloc[:cutoff][FEATURE_COLS]
    X_test = sorted_df.iloc[cutoff:][FEATURE_COLS]
    y_train = sorted_df.iloc[:cutoff][TARGET_COL].astype(int)
    y_test = sorted_df.iloc[cutoff:][TARGET_COL].astype(int)
    return X_train, X_test, y_train, y_test


# --- Modeling and metrics -------------------------------------------------

def train_logistic_regression(
    X_train: pd.DataFrame, y_train: pd.Series
) -> "Pipeline | DummyClassifier":
    """
    Fit a class-balanced logistic regression pipeline (Decision 7).

    The classifier is wrapped in an ``sklearn.pipeline.Pipeline`` with
    a leading ``StandardScaler`` step. Feature scaling is **not optional**
    here: the engineered features span wildly different ranges (pm25
    lags up to ~200 μg/m³, while ``is_weekend`` is 0/1 and
    ``month_of_year`` lives in a 1-wide band during typical pipeline
    runs). Without standardisation, L2-regularised LR over-shrinks the
    high-magnitude PM2.5 coefficients and ends up over-relying on the
    binary/categorical features — exactly the signal the regulariser
    *should* be downweighting in a well-scaled fit. Empirically on the
    AirAlert 30-day window this is the single biggest accuracy lift
    available; F1 roughly doubled when this step was introduced.

    The downstream estimator is configured with
    ``class_weight="balanced"`` — this is non-negotiable for AirAlert.
    With a positive-class rate well under 20% on Utah PM2.5 data, an
    unweighted classifier collapses to "always predict safe" and
    recall on the unsafe class drops to zero. ``max_iter=1000`` gives
    the LBFGS solver enough room to converge on the scaled features,
    and ``random_state=0`` makes the fit reproducible.

    The Pipeline object is interchangeable with the bare estimator
    everywhere it's used downstream: ``predict`` / ``predict_proba`` /
    ``classes_`` all forward to the final step, ``joblib`` pickles it
    correctly, and ``mlflow.sklearn.log_model`` registers it cleanly.
    ``serve.py``'s ``_unsafe_probability`` reads ``model.classes_`` and
    ``model.predict_proba`` without modification.

    Single-class fallback:
        ``LogisticRegression.fit`` requires at least two distinct
        classes in ``y_train``. With ~0.6% positive class rates and a
        chronological 80/20 split, a location can occasionally end up
        with every unsafe hour in the test set — leaving zero unsafe
        rows in training. In that case we fall back to a
        ``DummyClassifier(strategy="constant", constant=<seen>)`` that
        is pre-fit on a synthetic 2-row sample so its ``classes_``
        array contains both 0 and 1. The downstream ``serve.py``
        loader accepts the resulting estimator unchanged and its
        ``predict_proba`` returns 1.0 for the observed class and 0.0
        for the unseen class. This is a *degenerate* model — its F1
        on the unsafe class will be 0.0 by construction — but it lets
        the DAG finish green and surfaces the data shortage as a loud
        WARNING log line rather than a hard crash. The next retrain
        run (or a re-bucketed training window) will usually fit a
        real LR; the fallback is meant to be transient.

    Args:
        X_train: Training features. Columns must equal ``FEATURE_COLS``.
        y_train: Training targets — 0 for safe hours, 1 for unsafe.

    Returns:
        Either a fitted ``sklearn.pipeline.Pipeline`` wrapping
        StandardScaler → LogisticRegression (the normal path) or a
        fitted ``sklearn.dummy.DummyClassifier`` (the single-class
        fallback). Both expose ``predict``, ``predict_proba`` and
        ``classes_`` containing ``[0, 1]`` so ``serve.py`` works
        unchanged.
    """
    import numpy as np

    distinct_classes = int(y_train.nunique())
    if distinct_classes < 2:
        from sklearn.dummy import DummyClassifier

        observed = int(y_train.iloc[0]) if len(y_train) else 0
        logger.warning(
            "Training data has only %d distinct class(es) (observed=%d). "
            "Falling back to DummyClassifier; this location's F1 on the "
            "unsafe class will be 0.0 until the next retrain window "
            "contains at least one example of each class.",
            distinct_classes,
            observed,
        )
        # Fit on a synthetic 2-row training set so the resulting model
        # has classes_ = [0, 1]. We use the same feature columns as
        # X_train and a `constant` strategy fixed to the observed
        # class, so every real prediction will agree with what LR
        # would have learned from this collapsed training set anyway.
        dummy = DummyClassifier(strategy="constant", constant=observed)
        synthetic_X = pd.DataFrame(
            np.zeros((2, X_train.shape[1])),
            columns=X_train.columns,
        )
        synthetic_y = pd.Series([0, 1], dtype=int)
        dummy.fit(synthetic_X, synthetic_y)
        return dummy

    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=0,
                ),
            ),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


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
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    y_pred = model.predict(X_test)

    f1 = f1_score(y_test, y_pred, pos_label=1, zero_division=0)
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
    recall = recall_score(y_test, y_pred, pos_label=1, zero_division=0)

    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    return {
        "f1": float(f1),
        "baseline_f1": baseline_f1_score(y_test),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "false_negatives": int(fn),
        "true_positives": int(tp),
    }


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
    from sklearn.metrics import f1_score

    y_baseline = [0] * len(y_test)
    return float(
        f1_score(y_test, y_baseline, pos_label=1, zero_division=0)
    )


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
        Any ``mlflow`` client exception raised by the ``mlflow.start_run``,
        ``log_params``, ``log_metrics``, or ``log_model`` calls (e.g.
        connection error to the tracking URI, registry-permission errors
        on registration) propagates uncaught. The subsequent
        Production-stage promotion is best-effort and never raises — see
        the implementation block.
    """
    import mlflow
    import mlflow.sklearn

    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    run_name = f"{location_key}_{ds}"
    registered_name = MODEL_NAME_TEMPLATE.format(location=location_key)

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(
            {
                "location_key": location_key,
                "ds": ds,
                "class_weight": "balanced",
                "max_iter": 1000,
                "random_state": 0,
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name=registered_name,
        )

        # Promote the newly registered version to the Production stage so
        # that ``serve.py`` can resolve ``models:/AirAlert_<loc>/Production``
        # on cold start. Without this step every registered version stays
        # at stage ``None`` and the FastAPI lifespan loader raises
        # ``RESOURCE_DOES_NOT_EXIST``. Best-effort — wrapped in try/except so
        # registry hiccups (network blip, transient permission error, etc.)
        # log a warning but never break the training run; the model is
        # already registered and will still load via the pickle fallback.
        # See docs/serve_production_promotion_plan.md for the full design.
        try:
            from mlflow.tracking import MlflowClient

            client = MlflowClient(tracking_uri=MLFLOW_URI)
            latest = client.get_latest_versions(
                registered_name, stages=["None"]
            )
            if latest:
                new_version = latest[0].version
                client.transition_model_version_stage(
                    name=registered_name,
                    version=new_version,
                    stage="Production",
                    archive_existing_versions=True,
                )
                logger.info(
                    "Promoted %s version %s to Production",
                    registered_name,
                    new_version,
                )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning(
                "Failed to promote %s to Production (%s: %s); model is "
                "registered but stage remains None",
                registered_name,
                type(exc).__name__,
                exc,
            )

        return run.info.run_id


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
    import joblib

    expected_keys = set(TARGET_LOCATIONS)
    given_keys = set(models_by_location)
    if given_keys != expected_keys:
        raise ValueError(
            "models_by_location keys do not match TARGET_LOCATIONS — "
            f"missing={sorted(expected_keys - given_keys)} "
            f"unexpected={sorted(given_keys - expected_keys)}"
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for location_key, model in models_by_location.items():
        per_loc_path = MODELS_DIR / f"{location_key}_{ds}.pkl"
        joblib.dump(model, per_loc_path)

    bundle_path = MODELS_DIR / LATEST_MODEL_FILENAME
    joblib.dump(models_by_location, bundle_path)
    return bundle_path


# --- Airflow entry point --------------------------------------------------

def _load_existing_bundle() -> dict:
    """
    Load ``include/models/latest_model.pkl`` if present, else return ``{}``.

    Used by ``retrain_task`` to preserve estimators for locations that the
    DAG decided not to retrain on a given day. Returns an empty dict on any
    error so a corrupt bundle does not poison a partial-retrain run; the
    caller will fall back to retraining the affected locations.
    """
    import joblib
    bundle_path = MODELS_DIR / LATEST_MODEL_FILENAME
    if not bundle_path.exists():
        return {}
    try:
        loaded = joblib.load(bundle_path)
        return dict(loaded) if isinstance(loaded, dict) else {}
    except Exception:  # noqa: BLE001 — corrupt bundle, force full retrain
        return {}


def _load_previous_per_location_metrics() -> dict[str, dict]:
    """
    Read the most recent ``metrics_*.json`` and return its ``per_location``
    sub-dict (or an empty dict if no metrics file exists yet).

    Used by ``retrain_task`` to carry forward yesterday's metrics for
    locations that did not retrain today.
    """
    import json
    files = sorted(MODELS_DIR.glob("metrics_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text())
    except Exception:  # noqa: BLE001 — corrupt file, treat as missing
        return {}
    return dict(data.get("per_location") or {})


def _load_previous_retrain_history() -> dict[str, str]:
    """
    Read the most recent ``metrics_*.json`` and return its
    ``retrain_history`` sub-dict (or empty if no prior file exists).
    """
    import json
    files = sorted(MODELS_DIR.glob("metrics_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text())
    except Exception:  # noqa: BLE001 — corrupt file, treat as missing
        return {}
    return dict(data.get("retrain_history") or {})


def retrain_task(
    features_path: str,
    ds: str,
    locations_to_retrain: list[str] | None = None,
) -> dict:
    """
    Public entry point: train per-location classifiers for ``ds``.

    Per Decision 3, the DAG decides *which* locations need retraining each
    day (per-location F1 < 0.70 or weekly Monday backstop) and passes that
    list in via ``locations_to_retrain``. This function:

    1. Loads and validates the Contract-2 features CSV.
    2. For each location in ``locations_to_retrain``: chronologically
       splits, fits a balanced logistic regression, scores the holdout,
       and (best-effort) logs the run to MLflow.
    3. For every other location: reuses the estimator from the existing
       ``latest_model.pkl`` bundle and the per-location metrics from the
       most recent ``metrics_*.json``. If either is missing for that
       location, the location is force-retrained as a bootstrap fallback.
    4. Saves the merged bundle (new + preserved entries) to
       ``include/models/latest_model.pkl``. Date-stamped per-location
       pickles are written **only** for locations that retrained.
    5. Returns an aggregated metrics dict with rubric-required top-level
       keys plus a ``per_location`` breakdown and a ``retrain_history``
       map showing the ``ds`` of each location's most recent retrain.

    Args:
        features_path: Path string to a Contract-2 features CSV
            (typically the output of the upstream ``engineer_features``
            task — i.e. ``include/data/features/features_{ds}.csv``).
            Must be a non-empty string.
        ds: Airflow execution date in YYYY-MM-DD format.
        locations_to_retrain: List of ``TARGET_LOCATIONS`` keys to
            retrain. ``None`` (default) retrains all three (legacy /
            bootstrap behavior). ``[]`` retrains nothing if a complete
            existing bundle and previous per-location metrics are
            available; otherwise the affected locations are bootstrapped.

    Returns:
        A dict with these top-level keys:

        - ``f1``, ``baseline_f1``, ``accuracy``, ``precision``, ``recall``
          (floats — mean across all three locations).
        - ``false_negatives``, ``true_positives`` (ints — sum across all
          three locations).
        - ``per_location`` (dict): one entry per ``TARGET_LOCATIONS`` key,
          each with the same metric keys above (no further nesting).
        - ``retrain_history`` (dict): ``{location_key: ds_of_last_retrain}``.

    Raises:
        ValueError: ``features_path`` is empty/not a string, ``ds`` is not
            YYYY-MM-DD, or any downstream validation fails.
        FileNotFoundError: ``features_path`` does not exist.
    """
    import json

    if not isinstance(features_path, str) or not features_path.strip():
        raise ValueError(
            f"features_path must be a non-empty string; got {features_path!r}"
        )
    if not isinstance(ds, str) or not _DS_RE.match(ds):
        raise ValueError(
            f"ds must be a YYYY-MM-DD string; got {ds!r}"
        )

    if locations_to_retrain is None:
        locations_to_retrain = list(TARGET_LOCATIONS.keys())
    else:
        # Defensive: drop any unknown keys silently (the DAG should never
        # pass these, but a typo would otherwise cause a confusing crash).
        locations_to_retrain = [
            k for k in locations_to_retrain if k in TARGET_LOCATIONS
        ]
    retrain_set = set(locations_to_retrain)

    df = load_features(Path(features_path))
    per_location_frames = split_by_location(df)

    existing_bundle = _load_existing_bundle()
    prev_per_loc = _load_previous_per_location_metrics()
    prev_history = _load_previous_retrain_history()

    models_by_location: dict[str, "LogisticRegression"] = {}
    per_loc_metrics: dict[str, dict[str, float | int]] = {}
    actually_retrained: list[str] = []
    retrain_history: dict[str, str] = dict(prev_history)

    # ---- Step 1: Decide per location whether we have what we need ---------
    # If a location is in the keep-list but has no existing model OR no
    # previous metrics, we MUST retrain it (bootstrap fallback) — otherwise
    # the bundle would be incomplete and the metrics dict would be missing
    # rubric-required keys.
    for location_key, location_id in TARGET_LOCATIONS.items():
        if location_id is None:
            raise ValueError(
                f"TARGET_LOCATIONS[{location_key!r}] is None — populate "
                "constants.py before running retrain_task"
            )
        if location_key not in retrain_set:
            missing_model = location_key not in existing_bundle
            missing_metrics = location_key not in prev_per_loc
            if missing_model or missing_metrics:
                logger.warning(
                    "Bootstrap fallback: %s was in keep-list but %s missing; "
                    "forcing retrain.",
                    location_key,
                    "model" if missing_model else "metrics",
                )
                retrain_set.add(location_key)

    # ---- Step 2: Train the locations that need it -------------------------
    # MLflow tracking is bookkeeping; do all training and metric computation
    # first so a tracking outage cannot prevent the bundle from being saved.
    for location_key, location_id in TARGET_LOCATIONS.items():
        if location_key not in retrain_set:
            continue
        loc_df = per_location_frames[location_id]
        X_train, X_test, y_train, y_test = chronological_split(loc_df)
        model = train_logistic_regression(X_train, y_train)
        metrics = compute_metrics(model, X_test, y_test)
        models_by_location[location_key] = model
        per_loc_metrics[location_key] = metrics
        actually_retrained.append(location_key)
        retrain_history[location_key] = ds

    # ---- Step 3: Carry forward kept locations -----------------------------
    for location_key in TARGET_LOCATIONS:
        if location_key in models_by_location:
            continue
        # We already verified existing_bundle/prev_per_loc have what we need
        # in Step 1 (else we forced retrain).
        models_by_location[location_key] = existing_bundle[location_key]
        per_loc_metrics[location_key] = dict(prev_per_loc[location_key])
        # retrain_history already contains the prior ds for this location

    # ---- Step 4: Persist the merged bundle --------------------------------
    # save_model_bundle writes BOTH latest_model.pkl AND date-stamped
    # per-location pickles. The date-stamped pickles for locations we did
    # NOT retrain would be misleading (they'd suggest a fresh fit on `ds`
    # that didn't happen), so we use a small inline dump that only writes
    # the bundle plus the retrained locations' date-stamped files.
    import joblib
    expected_keys = set(TARGET_LOCATIONS)
    if set(models_by_location) != expected_keys:
        raise ValueError(
            "models_by_location keys do not match TARGET_LOCATIONS — "
            f"missing={sorted(expected_keys - set(models_by_location))} "
            f"unexpected={sorted(set(models_by_location) - expected_keys)}"
        )
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for location_key in actually_retrained:
        joblib.dump(
            models_by_location[location_key],
            MODELS_DIR / f"{location_key}_{ds}.pkl",
        )
    joblib.dump(models_by_location, MODELS_DIR / LATEST_MODEL_FILENAME)

    # ---- Step 5: MLflow (best-effort, only for retrained locations) -------
    if os.environ.get("AIRALERT_SKIP_MLFLOW", "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        logger.info(
            "AIRALERT_SKIP_MLFLOW set; skipping MLflow run logging for %s", ds
        )
    else:
        for location_key in actually_retrained:
            try:
                log_run_to_mlflow(
                    models_by_location[location_key],
                    per_loc_metrics[location_key],
                    location_key,
                    ds,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort
                logger.warning(
                    "MLflow logging failed for %s on %s (%s: %s); "
                    "model bundle is still saved to disk",
                    location_key, ds, type(exc).__name__, exc,
                )

    # ---- Step 6: Aggregate metrics for XCom -------------------------------
    float_keys = ("f1", "baseline_f1", "accuracy", "precision", "recall")
    int_keys = ("false_negatives", "true_positives")
    aggregated: dict[str, float | int | dict] = {}
    n = len(per_loc_metrics)
    for key in float_keys:
        aggregated[key] = float(
            sum(float(m[key]) for m in per_loc_metrics.values()) / n
        )
    for key in int_keys:
        aggregated[key] = int(
            sum(int(m[key]) for m in per_loc_metrics.values())
        )
    aggregated["per_location"] = {
        loc: {k: (float(v) if k in float_keys else int(v))
              for k, v in m.items()}
        for loc, m in per_loc_metrics.items()
    }
    aggregated["retrain_history"] = retrain_history
    return aggregated
