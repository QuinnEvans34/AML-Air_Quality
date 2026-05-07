"""
AirAlert shared constants.

Single source of truth for values that appear in multiple modules. If a
constant changes here, it changes everywhere — never hardcode these
values inline. Cross-reference: INTERFACE.md "Shared Constants" table
and .github/copilot-instructions.md.
"""

from __future__ import annotations

# PM2.5 unsafe threshold (μg/m³). EPA "unhealthy for sensitive groups" boundary.
UNSAFE_THRESHOLD: float = 35.4

# OpenAQ v3 — PM2.5 parameter id; needed to identify the right sensor at each
# location (locations expose multiple sensors: NO, NO2, O3, PM2.5, etc.).
OPENAQ_PM25_PARAMETER_ID: int = 2

# Canonical timestamp column name across Contracts 1 and 2.
DATETIME_COL: str = "timestamp"

# MLflow tracking — port 5001 to dodge macOS AirPlay on 5000.
MLFLOW_EXPERIMENT: str = "AirAlert"
MLFLOW_URI: str = "http://localhost:5001"

# Three per-location models (Decision 6) — one model registered per location_key.
# Format: MODEL_NAME_TEMPLATE.format(location="red_butte") -> "AirAlert_red_butte"
MODEL_NAME_TEMPLATE: str = "AirAlert_{location}"

# Target locations — OpenAQ location_id values to be filled in once we
# query /v3/locations to identify the three named Utah sites. None
# placeholders let downstream code import this dict; any function that
# tries to use a None id will fail loudly.
TARGET_LOCATIONS: dict[str, int | None] = {
    "red_butte":  3318370,   # Salt Lake County
    "smithfield": 305,       # Cache Valley
    "ledges":     6158842,   # near Snow Canyon, St. George
}
