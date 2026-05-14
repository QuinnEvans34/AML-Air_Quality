"""
AirAlert shared constants.

Single source of truth for values that appear in multiple modules. If a
constant changes here, it changes everywhere — never hardcode these
values inline. Cross-reference: INTERFACE.md "Shared Constants" table
and .github/copilot-instructions.md.
"""

from __future__ import annotations

import os

# PM2.5 unsafe threshold (μg/m³). EPA "unhealthy for sensitive groups" boundary.
UNSAFE_THRESHOLD: float = 35.4

# OpenAQ v3 — PM2.5 parameter id; needed to identify the right sensor at each
# location (locations expose multiple sensors: NO, NO2, O3, PM2.5, etc.).
OPENAQ_PM25_PARAMETER_ID: int = 2

# Canonical timestamp column name across Contracts 1 and 2.
DATETIME_COL: str = "timestamp"

# MLflow tracking — port 5001 to dodge macOS AirPlay on 5000.
# Honors MLFLOW_TRACKING_URI from the environment (set in airflow_settings.yaml
# or .env) so the same constants work in Astro and in local pytest. The default
# is a file-store inside the project so retraining works even when no MLflow
# server is running — the assignment only requires that latest_model.pkl loads
# with joblib, not that a tracking server is up.
MLFLOW_EXPERIMENT: str = "AirAlert"
MLFLOW_URI: str = os.environ.get(
    "MLFLOW_TRACKING_URI",
    "file:///usr/local/airflow/include/mlruns",
)

# Three per-location models (Decision 6) — one model registered per location_key.
# Format: MODEL_NAME_TEMPLATE.format(location="red_butte") -> "AirAlert_red_butte"
MODEL_NAME_TEMPLATE: str = "AirAlert_{location}"

# Decision 3 — retraining trigger.
# Retrain a per-location model when its rolling F1 on the unsafe class drops
# below this floor. Below 0.70, recall typically falls under 0.50, meaning
# we miss more than half of the unsafe hours; at that point a sensitive-group
# resident (asthma, COPD, elderly, young children) is better off ignoring
# our dashboard than trusting it, and the model has stopped serving its
# public-health purpose.
F1_RETRAIN_THRESHOLD: float = 0.70

# Weekly retrain backstop: Python ``datetime.weekday()`` index for Monday.
# A weekly unconditional retrain catches gradual drift even when each day's
# F1 stays just above the threshold.
WEEKLY_RETRAIN_WEEKDAY: int = 0

# Decision 3 — drift detection (W7A1).
# Per-location absolute mean-shift sigma above this threshold trips the
# drift verdict, which is the third retrain trigger alongside the Monday
# backstop and the F1 < F1_RETRAIN_THRESHOLD floor. 2.0 is the leading-
# indicator partner to the 0.70 F1 lagging-indicator floor: 2σ catches the
# upstream covariate shift before downstream F1 has collapsed, while F1 <
# 0.70 catches outcome degradation that drift alone might not surface
# (e.g. distribution stable but label boundary mis-calibrated). The two
# triggers overlap deliberately. See INTERFACE.md Decision 3 reasoning
# and docs/drift_implementation_plan.md.
DRIFT_SIGMA_THRESHOLD: float = 2.0

# Number of prior days of raw PM2.5 data that form the reference
# distribution for the drift check. 7 matches the rolling window
# ``transform.py`` uses to build features (``_HISTORY_DAYS = 7``), so
# drift compares against the same span of raw data the model was
# actually trained on.
DRIFT_REFERENCE_DAYS: int = 7

# Number of days of raw PM2.5 data that form the recent window. 1 = just
# today; aligns with the daily DAG cadence and gives the drift task a
# ~24-row recent window per location.
DRIFT_RECENT_DAYS: int = 1

# Target locations — OpenAQ location_id values to be filled in once we
# query /v3/locations to identify the three named Utah sites. None
# placeholders let downstream code import this dict; any function that
# tries to use a None id will fail loudly.
TARGET_LOCATIONS: dict[str, int | None] = {
    "red_butte":  3318370,   # Salt Lake County
    "smithfield": 305,       # Cache Valley
    "ledges":     6158842,   # near Snow Canyon, St. George
}
