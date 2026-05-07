from pathlib import Path

import pandas as pd

"""
    Transform raw PM2.5 into engineered features for model training
        
    This module reads hourly PM2.5 data from ingest.py, validates the data,
    creates temporal and lag-based features for the machine learning pipeline
        
    Input (Contract 1):
        include/data/raw/pm25_{YYYY-MM-DD}.csv:
        - timestamp (datetime64[ns, UTC])
        - location_id (int64)
        - pm25 (float64)
            
    Output (Contract 2):
        include/data/features/features_{YYYY-MM-DD}.csv:
        - timestamp, location_id
        - is_unsafe
        - pm25_lag_1h, pm25_lag_3h, pm25_lag_24h
        - pm25_rolling_mean_3h, pm25_rolling_std_3h
        - hour_of_day, day_of_week, month_of_year, is_weekend
            
    Key assumptions:
        - All timestamps are stored in UTC
        - Lag and rolling features are computed separately per location_id
        - Rolling aggregations exclude the current hour to prevent target leakage
"""




def validation_helper(df: pd.DataFrame) -> pd.DataFrame:
    """
        Takes the df and validates the required columns, especially the timestamp format and UTC
    
        Args:
            df: raw DataFrame 
            
        Returns:
            DataFrame that has been validated
        
        Raises: 
            ValueError: if required columns are missing
            ValueError: if the timestamp column is invalid
    """
    # Define the required columns that must be present in the raw data (from Contract 1)
    required_columns = ['timestamp', 'location_id', 'pm25']
    
    # Check if all required columns exist in the DataFrame
    # This ensures the ingest.py output matches our expected schema
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    # Validate and convert timestamp to UTC-aware datetime
    # The timestamp must be in datetime64[ns, UTC] format as specified in Contract 1
    # This ensures all timestamps are timezone-aware and in UTC for consistency
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    except Exception as e:
        raise ValueError(f"Failed to parse 'timestamp' column as UTC datetime: {e}")
    
    # Verify that timestamp is timezone-aware and set to UTC
    # This is critical for lag features which depend on time-based row ordering
    if df['timestamp'].dt.tz is None or str(df['timestamp'].dt.tz) != 'UTC':
        raise ValueError("Timestamp column must be UTC-aware (datetime64[ns, UTC])")
    
    # Return the validated DataFrame with confirmed schema
    return df


def lag_feature(df: pd.DataFrame) -> pd.DataFrame:
    """
        Takes the validated DataFrame and find lags based on hour
    
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing 1 hour, 3 hour, and 24 hour lag
        
        Raises: 
            ValueError: If validated DataFrame is not sorted by location_id and/or timestamp
    """
    # Make sure rows are ordered within each location before shifting values.
    expected_order = df.sort_values(['location_id', 'timestamp']).index
    if not df.index.equals(expected_order):
        raise ValueError("DataFrame must be sorted by location_id and timestamp before creating lag features")

    # Group by location so each site's history stays isolated from the others.
    location_groups = df.groupby('location_id', sort=False)

    # Shift the PM2.5 readings to create time-lagged predictors for the model.
    df['pm25_lag_1h'] = location_groups['pm25'].shift(1)
    df['pm25_lag_3h'] = location_groups['pm25'].shift(3)
    df['pm25_lag_24h'] = location_groups['pm25'].shift(24)

    return df


def rolling_feature(df: pd.DataFrame) -> pd.DataFrame:
    """
        Takes the validated DataFrame and find rolling mean and STD for pm25
    
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing rolling mean and STD for the pm25

        Raises: 
            ValueError: If validated DataFrame is not sorted by location_id and/or timestamp
    """
    # Rolling features must be computed on data that is already ordered by location and time.
    expected_order = df.sort_values(['location_id', 'timestamp']).index
    if not df.index.equals(expected_order):
        raise ValueError("DataFrame must be sorted by location_id and timestamp before creating rolling features")

    # Keep each location separate so one site's history never leaks into another site's features.
    location_groups = df.groupby('location_id', sort=False)

    # Exclude the current hour by shifting first, then compute the 3-hour summary stats.
    shifted_pm25 = location_groups['pm25'].shift(1)
    df['pm25_rolling_mean_3h'] = shifted_pm25.groupby(df['location_id']).rolling(window=3, min_periods=3).mean().reset_index(level=0, drop=True)
    df['pm25_rolling_std_3h'] = shifted_pm25.groupby(df['location_id']).rolling(window=3, min_periods=3).std().reset_index(level=0, drop=True)

    return df


def date_feature(df: pd.DataFrame) -> pd.DataFrame:
    """
        Creates temporal features from the timestamp column
     
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing date features: Day of week, Hour of Day, Month of Year, is weekend
        
        Raises:
            None
    """
    # Pull calendar values from the timestamp so the model can learn daily and seasonal patterns.
    df['hour_of_day'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month_of_year'] = df['timestamp'].dt.month

    # Mark weekends explicitly because air quality behavior often differs on Saturdays and Sundays.
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    return df


def build_features(raw_data_path: Path, output_path: Path) -> str:
    """
        Builds hourly air-quality features for raw PM2.5 data
        
        Args: 
            raw_data_path: Path to the raw ingest CSV file.
            output_path: Path where the transformed feature CSV will be written
            
        Returns:
            String path to the output file in include/data/features/features_{YYYY-MM-DD}.csv
            
        Raises: 
            ValueError: if the input data is empty, missing required columns or cannot be transformed
    
    """
    # Load the raw ingest output from disk so this task stays file-based for Airflow XComs.
    raw_data_df = pd.read_csv(raw_data_path)
    if raw_data_df.empty:
        raise ValueError(f"Raw data file is empty: {raw_data_path}")

    # Validate the input schema and normalize the timestamp column before feature engineering starts.
    validated_df = validation_helper(raw_data_df)

    # Sort once here so the lag and rolling helpers can safely work on ordered per-location history.
    validated_df = validated_df.sort_values(['location_id', 'timestamp']).reset_index(drop=True)

    # Build the feature groups in a clear order: lag features, rolling features, then calendar features.
    features_df = lag_feature(validated_df)
    features_df = rolling_feature(features_df)
    features_df = date_feature(features_df)

    # Create the binary target label used by the classifier.
    features_df['is_unsafe'] = (features_df['pm25'] > 35.4).astype(int)

    # Early rows for each location do not have enough history for lag/rolling features, so remove them.
    features_df = features_df.dropna().reset_index(drop=True)

    # Keep only the contract columns and write them to the requested output file.
    feature_columns = [
        'timestamp',
        'location_id',
        'is_unsafe',
        'pm25_lag_1h',
        'pm25_lag_3h',
        'pm25_lag_24h',
        'pm25_rolling_mean_3h',
        'pm25_rolling_std_3h',
        'hour_of_day',
        'day_of_week',
        'month_of_year',
        'is_weekend',
    ]
    features_df = features_df[feature_columns]

    # Make sure the destination folder exists before saving the transformed dataset.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_csv(output_path, index=False)

    return str(output_path)
