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


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
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


def _compute_session_metrics(df: pd.DataFrame, stop_threshold_kmh: float = 2.0) -> dict:
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


def _similarity(overall_val: float, rep_val: float) -> float:
    """% similarity between a representative value and the overall mean.

    Returns a value in [0, 100]. Perfect match returns 100.0.
    """
    if np.isnan(overall_val):
        return 0.0
    if overall_val == 0:
        return 100.0 if rep_val == 0 else 0.0
    return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)


def _gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
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


def _smooth_and_derive(speed_kmh: pd.Series) -> dict:
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


def _process_raw_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Process a raw OBD xlsx DataFrame into the calculations-log format.

    Applies GPS-time → elapsed seconds, rolling smoothing, and acceleration
    derivation. Returns a DataFrame whose columns match the combined log format
    produced by calculations.run_calculations().

    Raises ValueError if any required source column is missing.
    """
    missing = [c for c in _REQUIRED_RAW_COLS if c not in df_raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    duration = _gps_to_duration_seconds(df_raw["GPS Time"])
    speed_kmh = pd.to_numeric(df_raw["Speed (OBD)(km/h)"], errors="coerce")
    derived = _smooth_and_derive(speed_kmh)

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


def _infer_sheet_name(df_raw: pd.DataFrame, xlsx_path: Path) -> str:
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


# ────────────────────────────────────────────────────────────────────────────
# B.  PUBLIC FLAT FUNCTIONS  (backward-compat re-implementations)
#     Identical logic to students/DriveGUI/metrics.py.
#     Exported via metrics/__init__.py so existing tests keep working.
# ────────────────────────────────────────────────────────────────────────────


def _split_sheet_name(sheet_name: str) -> tuple[str, str]:
    parts = (sheet_name.split("_", 1) + ["Unknown"])[:2]
    return parts[0], parts[1]


def compute_average_speed(sheets: dict) -> dict:
    """Mean speed (km/h) per date and session."""
    means: dict = {}
    for sheet_name, df in sheets.items():
        if "Ταχ m/s" not in df.columns:
            continue
        speed_ms = pd.to_numeric(df["Ταχ m/s"], errors="coerce").dropna()
        mean_kmh = float(speed_ms.mean() * 3.6) if not speed_ms.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_kmh
    return means


def compute_average_speed_without_stops(sheets: dict, stop_threshold_kmh: float = 2.0) -> dict:
    """Mean speed (km/h) excluding stop samples, per date and session."""
    means: dict = {}
    for sheet_name, df in sheets.items():
        if "Ταχ m/s" not in df.columns:
            continue
        speed_ms = pd.to_numeric(df["Ταχ m/s"], errors="coerce").dropna()
        if speed_ms.empty:
            mean_kmh = 0.0
        else:
            speed_kmh = speed_ms * 3.6
            moving = speed_kmh[speed_kmh > stop_threshold_kmh]
            mean_kmh = float(moving.mean()) if not moving.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_kmh
    return means


def compute_maximum_speed(sheets: dict) -> dict:
    """Maximum speed (km/h) per date and session."""
    maxima: dict = {}
    for sheet_name, df in sheets.items():
        if "Ταχ m/s" not in df.columns:
            continue
        speeds_ms = pd.to_numeric(df["Ταχ m/s"], errors="coerce").dropna()
        max_kmh = float((speeds_ms * 3.6).max()) if not speeds_ms.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        maxima.setdefault(date_str, {})[session] = max_kmh
    return maxima


def compute_average_acceleration(sheets: dict) -> dict:
    """Mean positive acceleration (m/s²) per date and session."""
    means: dict = {}
    for sheet_name, df in sheets.items():
        if "Επιταχυνση" not in df.columns:
            continue
        accel = pd.to_numeric(df["Επιταχυνση"], errors="coerce").dropna()
        mean_val = float(accel.mean()) if not accel.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_val
    return means


def compute_average_deceleration(sheets: dict) -> dict:
    """Mean negative deceleration (m/s²) per date and session."""
    means: dict = {}
    for sheet_name, df in sheets.items():
        if "Επιβραδυνση" not in df.columns:
            continue
        decel = pd.to_numeric(df["Επιβραδυνση"], errors="coerce").dropna()
        braking = decel[decel < 0]
        mean_val = float(braking.mean()) if not braking.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_val
    return means


def compute_stop_percentage(sheets: dict, stop_threshold_kmh: float = 2.0) -> dict:
    """Stop percentage per date and session.

    NOTE: Contains a pre-existing unit-detection heuristic — see TODOS.md.
    """
    percentages: dict = {}
    for sheet_name, df in sheets.items():
        col = df["Εξομαλυνση"] if "Εξομαλυνση" in df.columns else df.iloc[:, 1]
        speeds = pd.to_numeric(col, errors="coerce").dropna()
        if not speeds.empty and speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6
        pct_stop = (
            (speeds.le(stop_threshold_kmh).sum() / len(speeds)) * 100 if not speeds.empty else 0.0
        )
        date_str, session = _split_sheet_name(sheet_name)
        percentages.setdefault(date_str, {})[session] = pct_stop
    return percentages


def compute_number_of_stops(sheets: dict, stop_threshold_kmh: float = 2.0) -> dict:
    """Number of stop events (moving→stopped transitions) per date and session."""
    stop_counts: dict = {}
    smoothed_col = "Εξομαλυνση"
    for sheet_name, df in sheets.items():
        speeds = df[smoothed_col] if smoothed_col in df.columns else df.iloc[:, 1]
        speeds = pd.to_numeric(speeds, errors="coerce").dropna()
        was_moving = False
        events = 0
        for v in speeds:
            if v > stop_threshold_kmh:
                was_moving = True
            elif v <= stop_threshold_kmh and was_moving:
                events += 1
                was_moving = False
        date_str, session = _split_sheet_name(sheet_name)
        stop_counts.setdefault(date_str, {})[session] = events
    return stop_counts


def compute_total_stop_percentage(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> tuple[float, float]:
    """Overall stop/move split across ALL sheets combined.

    NOTE: Same pre-existing unit-detection heuristic as compute_stop_percentage.
    Returns (pct_stop, pct_move).
    """
    total_samples = 0
    stop_samples = 0
    for df in sheets.values():
        speeds = (df["Εξομαλυνση"] if "Εξομαλυνση" in df.columns else df.iloc[:, 1]).dropna()
        if speeds.empty:
            continue
        if speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6
        total_samples += len(speeds)
        stop_samples += int((speeds <= stop_threshold_kmh).sum())
    if total_samples == 0:
        return (0.0, 0.0)
    pct_stop = (stop_samples / total_samples) * 100
    return (pct_stop, 100.0 - pct_stop)


def compute_engine_load(sheets: dict) -> dict:
    """Mean engine load (%) per date and session."""
    loads: dict = {}
    for sheet_name, df in sheets.items():
        if "Engine Load(%)" not in df.columns:
            continue
        col = pd.to_numeric(df["Engine Load(%)"], errors="coerce").dropna()
        if col.empty:
            continue
        date_str, session = _split_sheet_name(sheet_name)
        loads.setdefault(date_str, {})[session] = float(col.mean())
    return loads


def compute_fuel_consumption(sheets: dict) -> dict:
    """Mean fuel flow rate (l/hr) per date and session."""
    means: dict = {}
    target_col = "Fuel flow rate/hour(l/hr)"
    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue
        flow = pd.to_numeric(df[target_col], errors="coerce").dropna()
        if flow.empty:
            continue
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = float(flow.mean())
    return means


def compute_co2_emissions(sheets: dict) -> dict:
    """Mean CO2 emissions (g/km) per date and session."""
    means: dict = {}
    target_col = "CO\u2082 in g/km (Average)(g/km)"
    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue
        co2 = pd.to_numeric(df[target_col], errors="coerce").dropna()
        mean_val = float(co2.mean()) if not co2.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_val
    return means


def compute_speed_profile(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> tuple[str, pd.Series, pd.Series]:
    """Return the representative sheet name and its speed profile data.

    Uses 2-metric selection (mean speed + stop %) — deduplication with
    find_representative_sheet is tracked in TODOS.md.

    Returns (sheet_name, duration_sec, smoothed_speed_kmh).
    Raises RuntimeError if no suitable data is found.
    """

    def _metrics(df: pd.DataFrame) -> dict:
        col = df.get("Ταχ m/s")
        if col is None:
            return dict(mean=np.nan, stop_pct=np.nan)
        speed_kmh = pd.to_numeric(col, errors="coerce").dropna() * 3.6
        return dict(
            mean=float(speed_kmh.mean()),
            stop_pct=float(speed_kmh.le(stop_threshold_kmh).mean()),
        )

    def _sim(a: float, b: float) -> float:
        if np.isnan(a) or np.isnan(b):
            return 0.0
        if a == 0:
            return 100.0 if b == 0 else 0.0
        return 100.0 - abs(a - b) / abs(a) * 100

    per = {n: _metrics(df) for n, df in sheets.items()}
    keys = list(per[next(iter(per))].keys())
    overall = {k: float(np.nanmean([m[k] for m in per.values()])) for k in keys}

    best, score = None, -1.0
    for n, m in per.items():
        s = float(np.nanmean([_sim(overall[k], v) for k, v in m.items()]))
        if s > score:
            best, score = n, s

    if best is None:
        raise RuntimeError("Unable to choose representative sheet")

    df = sheets[best]
    smooth_candidates = ["Εξομαλυνση", "Εξομάλυνση"]
    smooth_col = next((c for c in smooth_candidates if c in df.columns), None)
    if smooth_col is None:
        raise RuntimeError(f"Smoothed speed column not found in sheet {best!r}")

    x = pd.to_numeric(df["Διάρκεια (sec)"], errors="coerce").dropna()
    y = pd.to_numeric(df[smooth_col], errors="coerce").dropna()
    n = min(len(x), len(y))
    if n == 0:
        raise RuntimeError("Not enough data in representative sheet")

    return best, x.iloc[:n], y.iloc[:n]


def compute_session_metrics(df: pd.DataFrame, stop_threshold_kmh: float = 2.0) -> dict:
    """Public alias for _compute_session_metrics. See that function for details."""
    return _compute_session_metrics(df, stop_threshold_kmh)


def similarity(overall_val: float, rep_val: float) -> float:
    """Public alias for _similarity. See that function for details."""
    return _similarity(overall_val, rep_val)


def find_representative_sheet(sheets: dict, stop_threshold_kmh: float = 2.0) -> tuple[str, float]:
    """Return (best_sheet_name, mean_similarity_score).

    Raises ValueError if sheets is empty.
    """
    if not sheets:
        raise ValueError("No data sheets to compare")

    per_sheet = {
        name: _compute_session_metrics(df, stop_threshold_kmh) for name, df in sheets.items()
    }

    first_keys = list(per_sheet[next(iter(per_sheet))].keys())
    overall = {key: float(np.nanmean([m[key] for m in per_sheet.values()])) for key in first_keys}

    best_sheet, best_score = None, -1.0
    for name, metrics in per_sheet.items():
        sims = [_similarity(overall[k], v) for k, v in metrics.items()]
        avg_sim = float(np.nanmean(sims))
        if avg_sim > best_score:
            best_sheet, best_score = name, avg_sim

    return best_sheet, best_score
