# metrics.py
# ----------
# Pure computation functions for eco-driving metrics.
# No I/O, no Matplotlib — only data in, numbers out.
#
# All functions take `sheets: dict[str, pd.DataFrame]` (the result of
# pd.read_excel(..., sheet_name=None)) and return plain Python dicts or
# tuples.  No GUI or chart dependencies.

from __future__ import annotations

import numpy as np
import pandas as pd

# ────────────────────────────────────────────────────────────────
# Internal helper
# ────────────────────────────────────────────────────────────────

def _split_sheet_name(sheet_name: str) -> tuple[str, str]:
    """Return (date_str, session) from 'YYYY-MM-DD_Morning' style names."""
    parts = (sheet_name.split("_", 1) + ["Unknown"])[:2]
    return parts[0], parts[1]


# ────────────────────────────────────────────────────────────────
# Speed metrics
# ────────────────────────────────────────────────────────────────

def compute_average_speed(sheets: dict) -> dict:
    """Mean speed (km/h) per date and session.

    Returns
    -------
    dict[date_str, dict[session, float]]
    """
    means: dict = {}
    for sheet_name, df in sheets.items():
        if "Ταχ m/s" not in df.columns:
            continue
        speed_ms = pd.to_numeric(df["Ταχ m/s"], errors="coerce").dropna()
        mean_kmh = float(speed_ms.mean() * 3.6) if not speed_ms.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_kmh
    return means


def compute_average_speed_without_stops(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> dict:
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


# ────────────────────────────────────────────────────────────────
# Acceleration / deceleration metrics
# ────────────────────────────────────────────────────────────────

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
    """Mean negative deceleration (m/s²) per date and session.

    Only rows where deceleration < 0 (actual braking) contribute to the mean.
    """
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


# ────────────────────────────────────────────────────────────────
# Stop metrics
# ────────────────────────────────────────────────────────────────

def compute_stop_percentage(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> dict:
    """Stop percentage per date and session.

    NOTE: Contains a pre-existing unit-detection heuristic:
        if speeds.max() < stop_threshold_kmh: speeds *= 3.6
    This silently gives wrong results for all-stop sessions (all legitimate
    km/h values below 2.0 get multiplied by 3.6).  Preserved faithfully;
    fix is tracked in TODOS.md.
    """
    percentages: dict = {}
    for sheet_name, df in sheets.items():
        col = df["Εξομαλυνση"] if "Εξομαλυνση" in df.columns else df.iloc[:, 1]
        speeds = pd.to_numeric(col, errors="coerce").dropna()

        # Pre-existing unit heuristic (see NOTE above)
        if not speeds.empty and speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6

        if speeds.empty:
            pct_stop = 0.0
        else:
            pct_stop = (speeds.le(stop_threshold_kmh).sum() / len(speeds)) * 100

        date_str, session = _split_sheet_name(sheet_name)
        percentages.setdefault(date_str, {})[session] = pct_stop
    return percentages


def compute_number_of_stops(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> dict:
    """Number of stop events per date and session.

    NOTE: Uses a state machine to count moving→stopped transitions, NOT row
    counting.  Cannot be replaced with (speeds <= threshold).sum().
    """
    stop_counts: dict = {}
    smoothed_col = "Εξομαλυνση"

    for sheet_name, df in sheets.items():
        if smoothed_col in df.columns:
            speeds = df[smoothed_col]
        else:
            speeds = df.iloc[:, 1]
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
    """Overall stop/move split across ALL sheets combined (for pie chart).

    NOTE: Same pre-existing unit-detection heuristic as compute_stop_percentage.

    Returns
    -------
    tuple[float, float]
        (pct_stop, pct_move).  Both are 0.0 if there is no speed data.
    """
    total_samples = 0
    stop_samples = 0

    for df in sheets.values():
        speeds = (
            df["Εξομαλυνση"]
            if "Εξομαλυνση" in df.columns
            else df.iloc[:, 1]
        ).dropna()

        if speeds.empty:
            continue

        # Pre-existing unit heuristic (see NOTE above)
        if speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6

        total_samples += len(speeds)
        stop_samples += int((speeds <= stop_threshold_kmh).sum())

    if total_samples == 0:
        return (0.0, 0.0)

    pct_stop = (stop_samples / total_samples) * 100
    pct_move = 100.0 - pct_stop
    return (pct_stop, pct_move)


# ────────────────────────────────────────────────────────────────
# OBD channel metrics
# ────────────────────────────────────────────────────────────────

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
    """Mean CO₂ emissions (g/km) per date and session."""
    means: dict = {}
    target_col = "CO₂ in g/km (Average)(g/km)"
    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue
        co2 = pd.to_numeric(df[target_col], errors="coerce").dropna()
        mean_val = float(co2.mean()) if not co2.empty else 0.0
        date_str, session = _split_sheet_name(sheet_name)
        means.setdefault(date_str, {})[session] = mean_val
    return means


# ────────────────────────────────────────────────────────────────
# Speed profile
# ────────────────────────────────────────────────────────────────

def compute_speed_profile(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> tuple[str, pd.Series, pd.Series]:
    """Return the representative sheet name and its speed profile data.

    Uses a condensed 2-metric selection (mean speed + stop %) independently
    of find_representative_sheet.  Deduplication is tracked in TODOS.md.

    NOTE: The smoothed-speed column has an accent variant.  Both
    "Εξομαλυνση" and "Εξομάλυνση" are tried.

    Returns
    -------
    tuple[str, pd.Series, pd.Series]
        (sheet_name, duration_sec, smoothed_speed_kmh)

    Raises
    ------
    RuntimeError
        If no suitable data is found.
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


# ────────────────────────────────────────────────────────────────
# Representative route
# ────────────────────────────────────────────────────────────────

def compute_session_metrics(
    df: pd.DataFrame, stop_threshold_kmh: float = 2.0
) -> dict:
    """Compute the 7 representative-route metrics for a single DataFrame.

    Returns
    -------
    dict with keys: duration, mean_speed, mean_ns, stops, stop_pct,
                     mean_acc, mean_dec
    """
    duration = (
        float(df["Διάρκεια (sec)"].dropna().max())
        if "Διάρκεια (sec)" in df.columns
        else np.nan
    )

    if "Ταχ m/s" in df.columns:
        speed_ms = pd.to_numeric(df["Ταχ m/s"], errors="coerce").dropna()
    else:
        speed_ms = pd.Series(dtype=float)
    speed_kmh = speed_ms * 3.6
    mean_speed = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0

    moving = speed_kmh[speed_kmh > stop_threshold_kmh]
    mean_ns = float(moving.mean()) if not moving.empty else 0.0

    total_rows = len(speed_kmh)
    stops = int((speed_kmh <= stop_threshold_kmh).sum())
    stop_pct = (stops / total_rows * 100) if total_rows else 0.0

    mean_acc = float(df["Επιταχυνση"].mean()) if "Επιταχυνση" in df.columns else np.nan
    mean_dec = float(df["Επιβραδυνση"].mean()) if "Επιβραδυνση" in df.columns else np.nan

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
    """Compute % similarity between a representative value and the overall mean.

    Returns a value in [0, 100].  A perfect match returns 100.0.
    """
    if np.isnan(overall_val):
        return 0.0
    if overall_val == 0:
        return 100.0 if rep_val == 0 else 0.0
    return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)


def find_representative_sheet(
    sheets: dict, stop_threshold_kmh: float = 2.0
) -> tuple[str, float]:
    """Return (best_sheet_name, mean_similarity_score).

    Parameters
    ----------
    sheets : dict[str, pd.DataFrame]
        Data-only sheets.  The caller must exclude metadata sheets (e.g.
        "Σχέση Μετάδοσης από κατασκευαστή", "Log") before calling.

    Raises
    ------
    ValueError
        If sheets is empty.

    Returns
    -------
    tuple[str, float]
        (sheet_name, mean_similarity_score in [0, 100])
    """
    if not sheets:
        raise ValueError("No data sheets to compare")

    per_sheet = {
        name: compute_session_metrics(df, stop_threshold_kmh)
        for name, df in sheets.items()
    }

    first_keys = list(per_sheet[next(iter(per_sheet))].keys())
    overall = {
        key: float(np.nanmean([m[key] for m in per_sheet.values()]))
        for key in first_keys
    }

    best_sheet, best_score = None, -1.0
    for name, metrics in per_sheet.items():
        sims = [similarity(overall[k], v) for k, v in metrics.items()]
        avg_sim = float(np.nanmean(sims))
        if avg_sim > best_score:
            best_sheet, best_score = name, avg_sim

    return best_sheet, best_score
