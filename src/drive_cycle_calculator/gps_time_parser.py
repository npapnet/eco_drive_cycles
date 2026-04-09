import numpy as np
import pandas as pd
from dateutil import parser as _dateutil_parser

class GpsTimeParser:
    """Parses raw GPS time series into standardized Datetime or Duration Seconds.
    
    Handles both clean generic formats and specific exports (like Torque logs).
    """

    def to_datetime(self, gps_series: pd.Series) -> pd.Series:
        """Attempts to parse the series into a pandas Datetime series."""
        s = gps_series.copy()
        
        # Heuristic 1: Torque export format ("Mon Sep 22 10:30:00 +0300 2019")
        def _parse_torque_format(val: object) -> "pd.Timestamp | float":
            if pd.isna(val):
                return np.nan
            text = str(val).strip()
            # Normalise Torque's "+0300 YYYY" → "+0300" then strip trailing year noise
            text = text.replace("GMT", "").strip()
            try:
                return _dateutil_parser.parse(text)
            except Exception:
                return np.nan

        # Is it already a datetime string or torque export?
        if len(s) > 0 and isinstance(s.iloc[0], str):
            # Attempt Torque parse first 
            dt_torque = s.map(_parse_torque_format)
            if dt_torque.notna().any():
                return pd.to_datetime(dt_torque, errors="coerce", utc=True)
            
            # Fallback for pure generic string format
            pass
        
        # Heuristic 2: General purpose pd.to_datetime (for standard strings or already Timestamp)
        dt = pd.to_datetime(s, errors="coerce", utc=True)
        return dt

    def to_duration_seconds(self, gps_series: pd.Series) -> pd.Series:
        """Converts GPS Time column to elapsed seconds from the first valid record."""
        # 1. Check if the series is already purely numeric seconds
        numeric = pd.to_numeric(gps_series, errors="coerce")
        if numeric.notna().any():
            first_value = numeric.dropna().iloc[0]
            return numeric - first_value

        # 2. Not numeric duration, let's try computing duration from parsed datetimes
        dt = self.to_datetime(gps_series)
        
        if dt.notna().any():
            first_dt = dt.dropna().iloc[0]
            return (dt - first_dt).dt.total_seconds()

        # 3. Complete fallback for all unparseable
        return pd.Series([np.nan] * len(gps_series), index=gps_series.index)
