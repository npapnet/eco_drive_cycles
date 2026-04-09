# _computations.py
# ----------------
# Two sections:
#
# A. PRIVATE HELPERS — used internally by Trip and TripCollection.
#    Named with leading underscore.  Not part of the public API.
#
# B. PUBLIC FLAT FUNCTIONS — duplicated from students/DriveGUI/metrics.py
#    for backward compatibility.  Re-exported by metrics/__init__.py so that
#    existing tests and callers keep working after conftest.py is deleted.
#
#    Transitional: once students/DriveGUI migrates to import from this package,
#    these copies can be removed and the flat layout updated to re-export from here.

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

# Maps Greek DriveGUI column names (from calculations-log xlsx) to English package names.
# Applied at both entry points: _process_raw_df() and TripCollection.from_excel().
# NOTE: "Speed (OBD)(km/h)" → "speed_kmh" belongs to OBD_COLUMN_MAP in _schema.py, NOT here.
GREEK_COLUMN_MAP = {
    "Διάρκεια (sec)": "elapsed_s",
    "Ταχ m/s": "speed_ms",
    "Εξομαλυνση": "smooth_speed_kmh",
    "Εξομάλυνση": "smooth_speed_kmh",  # accent variant
    "Επιταχυνση": "acceleration_ms2",
    "Επιβραδυνση": "deceleration_ms2",
}

# Backward-compat alias — callers that imported COLUMN_MAP keep working.
COLUMN_MAP = GREEK_COLUMN_MAP


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Greek column names to English at the package boundary.

    Safe to call multiple times — idempotent. Unknown columns pass through unchanged.
    """
    return df.rename(columns=COLUMN_MAP)


_REQUIRED_RAW_COLS = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]


def compute_session_metrics(df: pd.DataFrame, stop_threshold_kmh: float = 2.0) -> dict:
    """Compute the 7 representative-route metrics for a single processed DataFrame.

    Returns a dict with keys: duration, mean_speed, mean_ns, stops, stop_pct,
    mean_acc, mean_dec.

    Missing columns return NaN rather than raising.
    """
    duration = float(df["elapsed_s"].dropna().max()) if "elapsed_s" in df.columns else np.nan

    # Speed: prefer smooth_speed_kmh (new pipeline); fall back to speed_ms (old pipeline).
    if "smooth_speed_kmh" in df.columns:
        speed_kmh = pd.to_numeric(df["smooth_speed_kmh"], errors="coerce").dropna()
    elif "speed_ms" in df.columns:
        speed_kmh = pd.to_numeric(df["speed_ms"], errors="coerce").dropna() * 3.6
    else:
        speed_kmh = pd.Series(dtype=float)
    mean_speed = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0

    moving = speed_kmh[speed_kmh > stop_threshold_kmh]
    mean_ns = float(moving.mean()) if not moving.empty else 0.0

    total_rows = len(speed_kmh)
    stops = int((speed_kmh <= stop_threshold_kmh).sum())
    stop_pct = (stops / total_rows * 100) if total_rows else 0.0

    # Acceleration: prefer acc_ms2 (new pipeline); fall back to split columns (old pipeline).
    if "acc_ms2" in df.columns:
        acc = pd.to_numeric(df["acc_ms2"], errors="coerce")
        mean_acc = float(acc.where(acc > 0).mean())
        mean_dec = float(acc.where(acc < 0).mean())
    else:
        mean_acc = (
            float(pd.to_numeric(df["acceleration_ms2"], errors="coerce").mean())
            if "acceleration_ms2" in df.columns
            else np.nan
        )
        mean_dec = (
            float(pd.to_numeric(df["deceleration_ms2"], errors="coerce").mean())
            if "deceleration_ms2" in df.columns
            else np.nan
        )

    return dict(
        duration=duration,
        mean_speed=mean_speed,
        mean_ns=mean_ns,
        stops=stops,
        stop_pct=stop_pct,
        mean_acc=mean_acc,
        mean_dec=mean_dec,
    )


def similarity(overall_val: float, rep_val: float) -> float:
    """% similarity between a representative value and the overall mean.

    Returns a value in [0, 100]. Perfect match returns 100.0.
    """
    if np.isnan(overall_val):
        return 0.0
    if overall_val == 0:
        return 100.0 if rep_val == 0 else 0.0
    return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)


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


def infer_sheet_name(df_raw: pd.DataFrame, xlsx_path: Path) -> str:
    """Infer a sheet name like '2025-05-14_Morning' from a raw OBD DataFrame.

    1. Reads cell A2 (iloc[1, 0]) for the recording timestamp.
    2. Strips 'GMT' and normalises timezone offset ('+03:00' → '+0300').
    3. Parses with strptime('%a %b %d %H:%M:%S %z %Y').
    4. Falls back to file mtime if parsing fails.
    5. Returns 'YYYY-MM-DD_Morning' or 'YYYY-MM-DD_Evening' (max 31 chars).
    """
    dt: datetime | None = None

    try:
        raw = str(df_raw.iloc[1, 0])
        raw = raw.replace("GMT", "")
        raw = re.sub(r"(\+\d\d):(\d\d)", r"\1\2", raw).strip()
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, IndexError):
        pass

    if dt is None:
        try:
            dt = datetime.fromtimestamp(xlsx_path.stat().st_mtime)
        except OSError:
            dt = datetime.now()

    session = "Morning" if dt.hour < 12 else "Evening"
    return f"{dt.date().isoformat()}_{session}"[:31]


def load_raw_df(path: str | Path) -> pd.DataFrame:
    """Load a raw OBD xlsx file exactly as Torque exported it — no processing.

    Returns the unmodified DataFrame so callers can inspect column names, dtypes,
    missing values, and raw sensor readings before any smoothing or derivation.

    Typical use: auditing a file, exploring data quality, comparing with the
    processed form returned by _process_raw_df().

    Parameters
    ----------
    path : str | Path
        Path to an OBD xlsx file produced by the Torque app.

    Returns
    -------
    pd.DataFrame
        Raw DataFrame, one row per GPS sample. All columns as exported by Torque
        (dtype object for sensor-off cells like '-').

    Raises
    ------
    FileNotFoundError
        If the path does not exist or is a directory, not a file.
    Exception
        If pandas/openpyxl cannot parse the file as a valid xlsx workbook
        (e.g. corrupt file, wrong format).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found or not a file: {path}")
    return pd.read_excel(path)


