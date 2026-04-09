import numpy as np
import pandas as pd
from dateutil import parser as _dateutil_parser


def parse_gps_time_torque(gps_series: pd.Series) -> pd.Series:
    """Parse GPS Time series from Torque export format."""
    s = gps_series.copy()

    def _parse(val: object) -> "pd.Timestamp | float":
        if pd.isna(val):
            return np.nan
        text = str(val).strip()
        # Normalise Torque's "+0300 YYYY" → "+0300" then strip trailing year noise
        text = text.replace("GMT", "").strip()
        # "Mon Sep 22 10:30:00 +0300 2019" → try dateutil
        try:
            return _dateutil_parser.parse(text)
        except Exception:
            return np.nan

    dt = s.map(_parse)
    dt = pd.to_datetime(dt, errors="coerce", utc=True)

    return dt


def _gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Convert a GPS Time series to elapsed seconds from the first valid timestamp.

    This is more specific to the Torque export Format

    Handles the Torque export format: timestamps like
    'Mon Sep 22 10:30:00 +0300 2019', with an optional stray A2 header row.

    Returns a float64 Series of elapsed seconds (first valid sample = 0.0).
    Returns all-NaN if no parseable timestamps found.
    """
    # Drop the A2 header row if present (iloc[1] is a timestamp string used as
    # sheet name, not data).  The heuristic: skip the first row if it cannot be
    # parsed as a datetime after stripping "GMT" suffix.
    s = gps_series.copy()

    def _parse(val: object) -> "pd.Timestamp | float":
        if pd.isna(val):
            return np.nan
        text = str(val).strip()
        # Normalise Torque's "+0300 YYYY" → "+0300" then strip trailing year noise
        text = text.replace("GMT", "").strip()
        # "Mon Sep 22 10:30:00 +0300 2019" → try dateutil
        try:
            return _dateutil_parser.parse(text)
        except Exception:
            return np.nan

    # TODO add unit test coverage.
    if isinstance(s.iloc[0], pd.Timestamp):
        dt = s
    elif isinstance(s.iloc[0], str):
        dt = s.map(_parse)
        dt = pd.to_datetime(dt, errors="coerce", utc=True)
    else:
        raise ValueError("GPS Time series is not a pandas Timestamp or string")

    if dt.notna().any():
        first_dt = dt.dropna().iloc[0]
        return (dt - first_dt).dt.total_seconds()

    return pd.Series([np.nan] * len(gps_series), index=gps_series.index)
