from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "include"))

from src.transform import build_features


def test_build_features_writes_expected_feature_file(tmp_path):
    # Use the checked-in sample raw file so this test stays fast and deterministic.
    raw_data_path = Path("include/data/raw/pm25_sample_loc_221401.csv")
    output_path = tmp_path / "features_sample_loc_221401.csv"

    result_path = build_features(raw_data_path, output_path)

    # The function should return the file path it wrote so Airflow can pass paths between tasks.
    assert result_path == str(output_path)
    assert output_path.exists()

    # Verify the output schema matches the feature contract in INTERFACE.md.
    features_df = pd.read_csv(output_path)
    assert list(features_df.columns) == [
        "timestamp",
        "location_id",
        "is_unsafe",
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

    # We should be producing real engineered rows, not an empty file.
    assert not features_df.empty
    assert set(features_df["is_weekend"].unique()).issubset({0, 1})