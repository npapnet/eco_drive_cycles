# _schema.py
# ----------
# Dependency-free schema constants for the OBD data pipeline.
# Imported by both obd_file.py and processing_config.py — lives at package root
# to avoid circular imports.

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil import parser as _dateutil_parser

# Maps raw OBD column names (as exported by Torque) to short English names
# used in the processed DataFrame produced by ProcessingConfig.apply().
# Note: "GPS Time" is NOT here — it is consumed to produce elapsed_s, not renamed.
OBD_COLUMN_MAP: dict[str, str] = {
    "Speed (OBD)(km/h)": "speed_kmh",
    "CO\u2082 in g/km (Average)(g/km)": "co2_g_per_km",
    "Engine Load(%)": "engine_load_pct",
    "Fuel flow rate/hour(l/hr)": "fuel_flow_lph",
}

# The minimum set of OBD columns required for analysis.
# OBDFile.curated_df returns only these columns.
# OBDFile.to_trip() raises ValueError if any are absent.
CURATED_COLS: list[str] = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]


def _gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Convert a GPS Time series to elapsed seconds from the first valid timestamp.

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

    dt = s.map(_parse)
    dt = pd.to_datetime(dt, errors="coerce", utc=True)

    if dt.notna().any():
        first_dt = dt.dropna().iloc[0]
        return (dt - first_dt).dt.total_seconds()

    return pd.Series([np.nan] * len(gps_series), index=gps_series.index)
