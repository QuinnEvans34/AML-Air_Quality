"""
serve.py — FastAPI serving layer for AirAlert.

This module will expose the dashboard-facing API for the project. It
will load the Production models at startup, keep them cached in memory
for low-latency prediction requests, and provide the health and
prediction endpoints defined by the serving contract.

Planned libraries:
- fastapi for the HTTP API
- pydantic for request and response schemas
- pandas for building the model feature frame
- pathlib for filesystem paths and cache checks
- typing for explicit location and model types
- mlflow for loading the registered Production models
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from include.src.constants import (
    MLFLOW_EXPERIMENT,
    MLFLOW_URI,
    MODEL_NAME_TEMPLATE,
    TARGET_LOCATIONS,
    UNSAFE_THRESHOLD,
)


class PredictionRequest(BaseModel):
    """
    Request body for the prediction endpoint.

    This schema will validate the exact Contract 3 feature fields plus
    the location selector used to choose the correct per-location
    model. The dashboard will use this shape to send one prediction
    request per selected location.
    """

    # The user chooses which location-specific model should answer this request.
    # We restrict this to the known Utah locations so the dashboard cannot ask
    # for a model that was never trained or registered.
    location: Literal["red_butte", "smithfield", "ledges"] = Field(
        description="Location key used to select the correct Production model."
    )

    # The nine engineered features must arrive in the exact Contract 3 shape.
    # These values are computed upstream so the serving layer stays thin and
    # only validates and predicts.
    pm25_lag_1h: float = Field(
        description="PM2.5 reading from one hour earlier.",
    )
    pm25_lag_3h: float = Field(
        description="PM2.5 reading from three hours earlier.",
    )
    pm25_lag_24h: float = Field(
        description="PM2.5 reading from twenty-four hours earlier.",
    )
    pm25_rolling_mean_3h: float = Field(
        description="Mean PM2.5 over the prior three hours.",
    )
    pm25_rolling_std_3h: float = Field(
        description="Standard deviation of PM2.5 over the prior three hours.",
    )
    hour_of_day: int = Field(
        description="Hour extracted from the timestamp.",
    )
    day_of_week: int = Field(
        description="Day of week extracted from the timestamp.",
    )
    month_of_year: int = Field(
        description="Month extracted from the timestamp.",
    )
    is_weekend: int = Field(
        description="Weekend flag derived from the day of week.",
    )


class PredictionResponse(BaseModel):
    """
    Response body for the prediction endpoint.

    This schema will carry the binary unsafe prediction, the unsafe
    probability from the model, and the threshold used by the project.
    The dashboard will read this response directly to show both the
    prediction and the certainty score.
    """

    # The binary label is what the dashboard uses for the simple safe/unsafe
    # decision, so the API returns it directly instead of forcing the frontend
    # to re-implement the threshold logic.
    is_unsafe: int = Field(
        description="Binary unsafe prediction produced by the model.",
    )

    # The probability gives the dashboard a confidence-style value that can be
    # shown to users alongside the label.
    unsafe_probability: float = Field(
        description="Model probability that the air is unsafe.",
    )

    # We return the threshold explicitly so the dashboard can explain where the
    # binary label came from and keep the decision rule visible.
    threshold_used: float = Field(
        description="Unsafe PM2.5 threshold used to interpret the prediction.",
    )


class HealthResponse(BaseModel):
    """
    Response body for the health endpoint.

    This schema will report the service status and the currently loaded
    model information. The health check will use this shape so callers
    can confirm which registry models are active.
    """

    # The status flag lets a caller quickly confirm that the serving layer is
    # alive and ready without needing to inspect model details first.
    status: str = Field(
        description="Service status indicator for readiness checks.",
    )

    # The model name summary makes it obvious which registry models were loaded
    # so operators can verify the serving layer is pointing at the expected
    # Production models.
    model_name: str = Field(
        description="Readable summary of the loaded MLflow model names.",
    )

    # The stage is returned because the assignment wants the service to load
    # from Production, and exposing it here makes that choice visible.
    stage: str = Field(
        description="MLflow registry stage loaded by the service.",
    )


class LoadedModelState:
    """
    In-memory cache for the loaded serving models.

    This class will hold the model objects and the cache metadata used
    to decide when the registered model bundle needs to be refreshed.
    """

    def __init__(self) -> None:
        """
        Initialize an empty in-memory model cache.

        The cache starts empty and will be populated when the serving
        app loads the registered Production models from MLflow.
        """

        # We keep the loaded models in a simple dictionary so the serving
        # layer can look up the correct per-location model quickly.
        self.models: dict[str, Any] = {}

        # This cache marker will later let us detect whether the on-disk
        # training bundle changed and needs to be reloaded.
        self.bundle_mtime: float | None = None

    @property
    def model_name_summary(self) -> str:
        """
        Summarize the registered model names currently held in cache.

        This will later provide a readable health-check value that tells
        us which per-location Production models are loaded.
        """

        # If nothing has been loaded yet, the health check should say so
        # clearly instead of returning an empty string.
        if not self.models:
            return "unloaded"

        # We format the cached keys back into the registered model names
        # so the health response mirrors how the models were stored in MLflow.
        model_names = [
            MODEL_NAME_TEMPLATE.format(location=location_key)
            for location_key in sorted(self.models)
        ]
        return ", ".join(model_names)


# --- Module-level constants -----------------------------------------------

# These feature column names must match Contract 3 exactly so the model
# receives input in the expected order and shape.
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

# The MLflow Production stage is the canonical serving stage for the project.
# We load from "Production" because the assignment specifies this stage for
# serving models, ensuring we skip experimental or staging-area models.
MODEL_STAGE: str = "Production"

# The path to the trained models directory so we can check file modification
# times and decide when to refresh the cached models.
MODELS_DIR: Path = Path("include/models")
LATEST_MODEL_BUNDLE: Path = MODELS_DIR / "latest_model.pkl"

# Global cache state that persists across requests. This holds the loaded
# models in memory so we don't reload from MLflow on every prediction.
_STATE = LoadedModelState()


# --- Helper functions-----------------------------------------------------

def _current_bundle_mtime() -> float | None:
    """
    Check the modification time of the latest training bundle on disk.

    This function looks up the bundle file created by train.py to see
    if it has changed since we last loaded the models.

    Args:
        None.

    Returns:
        The file modification time (mtime) as a float, or None if the
        bundle file does not exist yet.

    Raises:
        None.
    """

    # If the bundle doesn't exist yet, the app has never trained anything
    # or we are in a fresh environment, so we return None to signal that.
    if not LATEST_MODEL_BUNDLE.exists():
        return None

    # We read the filesystem's internal modification time so we can later
    # compare it to the cached value and decide whether to reload.
    return LATEST_MODEL_BUNDLE.stat().st_mtime


def _load_registry_models() -> dict[str, Any]:
    """
    Load the Production models for all locations from the MLflow registry.

    This function pulls each per-location model (red_butte, smithfield,
    ledges) from the MLflow artifact store using the Production stage
    so the serving layer stays synchronized with the latest trained models.

    Args:
        None.

    Returns:
        A dictionary mapping each location key to its sklearn estimator
        loaded from the MLflow registry.

    Raises:
        RuntimeError: If any of the three registry models cannot be loaded,
            which would indicate a misconfiguration or training failure.
    """

    import mlflow
    import mlflow.sklearn

    # We configure the tracking URI and select the AirAlert experiment so
    # MLflow knows where to find the production models.
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    loaded_models: dict[str, Any] = {}
    for location_key in TARGET_LOCATIONS:
        # We build the registry model URI using the template and stage so
        # MLflow can fetch the right artifact from Production.
        model_name = MODEL_NAME_TEMPLATE.format(location=location_key)
        model_uri = f"models:/{model_name}/{MODEL_STAGE}"

        try:
            # We load the sklearn estimator so it's ready to call predict
            # and predict_proba when a request arrives.
            loaded_models[location_key] = mlflow.sklearn.load_model(model_uri)
        except Exception as exc:
            # If loading fails, we fail loudly so operators know something
            # is wrong rather than silently serving stale models.
            raise RuntimeError(
                f"Failed to load registry model {model_uri}"
            ) from exc

    return loaded_models


def refresh_model_cache(force: bool = False) -> None:
    """
    Reload the cached models if the training bundle changed on disk.

    This function implements the mtime-based refresh strategy from Decision 8.
    It checks whether the bundle file's modification time has changed since
    the app last loaded models, and only reloads if so.

    Args:
        force: If True, reload the models unconditionally without checking
            mtime. Used during app startup to ensure models are loaded.

    Returns:
        None.

    Raises:
        RuntimeError: If the registry models cannot be loaded.
    """

    # When forced, we skip the mtime check and reload immediately. This is
    # necessary during lifespan startup so models are ready for requests.
    if force:
        _STATE.models = _load_registry_models()
        _STATE.bundle_mtime = _current_bundle_mtime()
        return

    # On non-forced calls, we check whether the bundle has changed since we
    # last loaded it. If not, we skip reloading to keep latency low.
    current_mtime = _current_bundle_mtime()
    if (
        _STATE.models
        and _STATE.bundle_mtime == current_mtime
    ):
        # The cache is current, so we skip the reload cost.
        return

    # The bundle changed (or this is the first load), so we refresh the cache
    # by loading the latest models from the registry.
    _STATE.models = _load_registry_models()
    _STATE.bundle_mtime = current_mtime


def _feature_frame(payload: PredictionRequest) -> pd.DataFrame:
    """
    Convert a request payload into the model's expected feature shape.

    This function takes the validated request body and builds a one-row
    DataFrame with the exact feature columns and ordering the trained
    models expect. This ensures the model receives input in the correct shape.

    Args:
        payload: The validated PredictionRequest body from the dashboard.

    Returns:
        A one-row pandas DataFrame containing the Contract 3 features in
        the exact order expected by the trained models.

    Raises:
        None.
    """

    # We extract the feature values from the request, excluding location
    # because location is used to select the model, not as a feature.
    feature_values = payload.model_dump(exclude={"location"})

    # We build the frame by extracting values in the exact feature order
    # so the model receives a correctly shaped input.
    return pd.DataFrame(
        [[feature_values[column] for column in FEATURE_COLS]],
        columns=FEATURE_COLS,
    )


def _unsafe_probability(model: Any, feature_frame: pd.DataFrame) -> float:
    """
    Extract the model's probability that the air is unsafe.

    This function calls the model's predict_proba method and pulls out
    the probability assigned to class 1 (unsafe). The probability is
    returned as a float for inclusion in the response.

    Args:
        model: The fitted sklearn estimator loaded from the MLflow registry.
        feature_frame: A one-row DataFrame returned by _feature_frame.

    Returns:
        The probability (as a float between 0 and 1) that the input
        represents unsafe air quality.

    Raises:
        HTTPException: If the model does not have predict_proba or does not
            contain class 1 in its fitted classes.
    """

    # We check that the model supports probabilistic predictions, which
    # logistic regression does, but some other classifiers might not.
    if not hasattr(model, "predict_proba"):
        raise HTTPException(
            status_code=503,
            detail="Loaded model does not expose predict_proba.",
        )

    # We find the index of class 1 in the model's class list so we can
    # extract the right probability column from the predict_proba output.
    classes = list(getattr(model, "classes_", []))
    if 1 not in classes:
        raise HTTPException(
            status_code=503,
            detail="Loaded model does not contain class 1.",
        )

    class_index = classes.index(1)

    # We call the model to get probabilities for all classes and extract
    # the one corresponding to class 1 (unsafe).
    probabilities = model.predict_proba(feature_frame)
    return float(probabilities[0][class_index])


def _predict_for_location(payload: PredictionRequest) -> PredictionResponse:
    """
    Generate a prediction for one location-specific model.

    This function coordinates the prediction pipeline: it refreshes the
    cache if needed, selects the correct per-location model, builds the
    feature frame, calls the model, and formats the response.

    Args:
        payload: The validated PredictionRequest body from the dashboard.

    Returns:
        A PredictionResponse containing the unsafe label, the unsafe
        probability, and the threshold used.

    Raises:
        HTTPException: If the requested location has not been loaded,
            or if the model cannot produce a prediction.
    """

    # We refresh the cache to ensure we're using the latest trained models.
    # This check is cheap if nothing changed, but catches training updates.
    refresh_model_cache()

    # We look up the location-specific model from the cache.
    model = _STATE.models.get(payload.location)
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"No cached model is loaded for location '{payload.location}'.",
        )

    # We convert the request payload into a feature DataFrame in the exact
    # order the model expects.
    feature_frame = _feature_frame(payload)

    # We extract the model's probability for the unsafe class so the
    # dashboard can show a certainty score.
    unsafe_probability = _unsafe_probability(model, feature_frame)

    # Decision 7: logistic regression probabilities are returned directly
    # as the dashboard certainty score; no additional calibration is applied.
    # The binary label is also the model's direct prediction.
    is_unsafe = int(model.predict(feature_frame)[0])

    return PredictionResponse(
        is_unsafe=is_unsafe,
        unsafe_probability=unsafe_probability,
        threshold_used=UNSAFE_THRESHOLD,
    )


# --- FastAPI lifespan and app initialization ------------------------------

async def lifespan(app: FastAPI):
    """
    Run the startup sequence before the app begins serving requests.

    This async context manager is called by FastAPI during startup. Its
    job is to load the trained models from the MLflow registry into the
    global cache so they are ready for prediction requests.

    Args:
        app: The FastAPI application instance.

    Returns:
        An async context manager that keeps the app alive. Yields control
        back to FastAPI once startup is complete.

    Raises:
        RuntimeError: If the registry models cannot be loaded.
    """

    # We force a model refresh on startup to ensure the cache is populated.
    # Users will see errors if the models are not available, which is better
    # than silently serving with an empty cache.
    refresh_model_cache(force=True)

    # After setup, we yield to FastAPI so it can start the server.
    yield

    # On shutdown, we could clean up the cache here if needed, but for now
    # we just let the app terminate cleanly.


# The FastAPI application instance that serves all prediction requests.
# We use the lifespan context manager so models are loaded before any
# requests arrive, and we give the app a descriptive title and version.
app = FastAPI(
    title="AirAlert Serving API",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Endpoints ------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Health check endpoint that confirms the service is ready.

    This endpoint allows the dashboard and monitoring systems to verify
    that the serving layer is alive and the trained models are loaded.

    Args:
        None.

    Returns:
        A HealthResponse containing the service status, the names of the
        loaded models, and the MLflow stage in use.

    Raises:
        HTTPException: If the model cache is empty, indicating that the
            models were never loaded during startup.
    """

    # If the cache is empty, something went wrong during startup and we
    # should tell callers that the service is not ready.
    if not _STATE.models:
        raise HTTPException(
            status_code=503,
            detail="Model cache is empty.",
        )

    # We return the status along with a readable summary of which models
    # are loaded so operators can verify the service is configured correctly.
    return HealthResponse(
        status="ok",
        model_name=_STATE.model_name_summary,
        stage=MODEL_STAGE,
    )


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    """
    Generate a prediction for the requested location and features.

    This endpoint accepts a validated feature payload, selects the
    appropriate per-location model, and returns the unsafe prediction
    and probabilities for the dashboard.

    Args:
        payload: The validated PredictionRequest body containing the
            location key and the nine engineered features.

    Returns:
        A PredictionResponse containing the unsafe binary label, the
        unsafe probability, and the threshold used.

    Raises:
        HTTPException: If the location is not found, the models are not
            loaded, or the model cannot produce a prediction.
    """

    # We delegate to the prediction helper which coordinates the full pipeline.
    return _predict_for_location(payload)


# Export the app so uvicorn can find it.
__all__ = ["app"]
