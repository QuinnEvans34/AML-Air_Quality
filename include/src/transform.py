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






def validation_helper(Dataframe df)
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


def lag_feature(Dataframe df)
    """
        Takes the validated DataFrame and find lags based on hour
    
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing 1 hour, 3 hour, and 24 hour lag
        
        Raises: 
            ValueError: If validated DataFrame is not sorted by location_id and/or timestamp
    """


def rolling_feature(Dataframe df)
    """
        Takes the validated DataFrame and find rolling mean and STD for pm25
    
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing rolling mean and STD for the pm25

        Raises: 
            ValueError: If validated DataFrame is not sorted by location_id and/or timestamp
    """


def date_feature(Dataframe df)
    """
        Creates temporal features from the timestamp column
     
        Args:
            df: Validation_helper returned DataFrame
            
        Returns:
            DataFrame containing date features: Day of week, Hour of Day, Month of Year, is weekend
        
        Raises:
            None
    """






def build_features(raw_data_path: Path, output_path: Path):
    """
        Builds hourly air-quality features for raw PM2.5 data
        
        Args: 
            raw_data_path: Path to the raw ingest CSV file.
            output_path: Path where the transformed feature CSV will be written
            
        Returns:
            DataFrame containing Contract 2 feature columns
            
        Raises: 
            ValueError: if the input data is empty, missing required columns or cannot be transformed
    
    """
