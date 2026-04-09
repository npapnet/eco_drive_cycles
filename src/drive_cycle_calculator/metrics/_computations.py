# _computations.py
# ----------------
# Two sections:
#
# A. PRIVATE HELPERS — used internally by Trip and TripCollection.
#    Named with leading underscore.  Not part of the public API.
#

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# A.  PRIVATE HELPERS
# ────────────────────────────────────────────────────────────────────────────

_SEVEN_METRIC_KEYS = (
    "duration",
    "mean_speed",
    "mean_ns",
    "stops",
    "stop_pct",
    "mean_acc",
    "mean_dec",
)

_REQUIRED_RAW_COLS = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]


def gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Convert GPS Time column to elapsed seconds from the first valid record.

    This is a more general purpose for clean data (compared to the _schema.py)


    """
    numeric = pd.to_numeric(gps_series, errors="coerce")
    if numeric.notna().any():
        first_value = numeric.dropna().iloc[0]
        return numeric - first_value

    dt = pd.to_datetime(gps_series, errors="coerce", utc=True)
    if dt.notna().any():
        first_dt = dt.dropna().iloc[0]
        return (dt - first_dt).dt.total_seconds()

    return pd.Series([np.nan] * len(gps_series), index=gps_series.index)


def smooth_and_derive(speed_kmh: pd.Series) -> dict:
    """Apply rolling smoothing and derive acceleration columns."""
    smooth_speed = speed_kmh.rolling(window=4, center=True, min_periods=4).mean()
    speed_ms = smooth_speed / 3.6
    acceleration = speed_ms.diff()
    return dict(
        smooth_speed=smooth_speed,
        speed_ms=speed_ms,
        acceleration=acceleration,
        pos_acc=acceleration.where(acceleration > 0),
        neg_acc=acceleration.where(acceleration < 0),
    )


def process_raw_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Process a raw OBD xlsx DataFrame into the calculations-log format.

    Applies GPS-time → elapsed seconds, rolling smoothing, and acceleration
    derivation. Returns a DataFrame whose columns match the combined log format.

    Raises ValueError if any required source column is missing.
    """
    missing = [c for c in _REQUIRED_RAW_COLS if c not in df_raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    duration = gps_to_duration_seconds(df_raw["GPS Time"])
    speed_kmh = pd.to_numeric(df_raw["Speed (OBD)(km/h)"], errors="coerce")
    derived = smooth_and_derive(speed_kmh)

    # Torque exports non-numeric cells (e.g. sensor-off rows) as "-".
    # Coerce to float so pyarrow writes a clean float64 column, not object.
    def _to_float(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce")

    return pd.DataFrame(
        OrderedDict(
            [
                ("elapsed_s", duration),
                (
                    "CO\u2082 in g/km (Average)(g/km)",
                    _to_float(df_raw["CO\u2082 in g/km (Average)(g/km)"]),
                ),
                ("Engine Load(%)", _to_float(df_raw["Engine Load(%)"])),
                ("Fuel flow rate/hour(l/hr)", _to_float(df_raw["Fuel flow rate/hour(l/hr)"])),
                ("smooth_speed_kmh", derived["smooth_speed"]),
                ("speed_ms", derived["speed_ms"]),
                ("a(m/s2)", derived["acceleration"]),
                ("acceleration_ms2", derived["pos_acc"]),
                ("deceleration_ms2", derived["neg_acc"]),
            ]
        )
    )
