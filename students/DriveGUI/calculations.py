"""
Core processing functions for the DriveGUI tool.

This file is self-contained — it does NOT import from the drive_cycle_calculator
package. DriveGUI is a frozen historical reference; package API changes must not
break it. Any logic shared with the package was inlined here intentionally.
"""
from __future__ import annotations

import glob
import os
import re
from collections import OrderedDict
from datetime import datetime

import numpy as np
import pandas as pd


# ── Internal helpers ────────────────────────────────────────────────────────

def gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Convert a GPS Time column to seconds elapsed from the first valid record.

    Tries numeric parsing first (values already in seconds), then falls back to
    datetime parsing. Returns an all-NaN Series if neither succeeds.
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
    """Apply rolling smoothing and derive acceleration columns.

    Returns a dict with keys:
        "smooth_speed" – rolling mean (window=4, center=True, min_periods=4), km/h
        "speed_ms"     – smooth_speed / 3.6, m/s
        "acceleration" – speed_ms.diff(), m/s²
        "pos_acc"      – acceleration where > 0 (NaN elsewhere)
        "neg_acc"      – acceleration where < 0 (NaN elsewhere)
    """
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


def run_calculations(folder_path: str, log_folder: str = "log") -> tuple[str, str]:
    """Process all .xlsx files in folder_path and write an Excel + text log.

    The output Excel workbook uses Greek column names (Διάρκεια, Εξομαλυνση, etc.)
    as expected by the DriveGUI visualization modules.

    Parameters
    ----------
    folder_path : str
        Folder containing raw OBD-II .xlsx files.
    log_folder : str, default "log"
        Destination for log files. Created if it does not exist.

    Returns
    -------
    tuple[str, str]
        (text_log_path, excel_log_path)
    """
    os.makedirs(log_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_log = os.path.join(log_folder, f"calculations_log_{timestamp}.xlsx")
    text_log = os.path.join(log_folder, f"calculations_log_{timestamp}.txt")

    text_lines: list[str] = []
    wrote_at_least_one_sheet = False

    with pd.ExcelWriter(excel_log, engine="openpyxl") as writer:
        for file_path in glob.glob(os.path.join(folder_path, "*.xlsx")):
            file_name = os.path.basename(file_path)
            try:
                df = pd.read_excel(file_path)
            except Exception as err:
                text_lines.append(f"{file_name}: ERROR reading file ({err})")
                continue

            # Build sheet name like "YYYY-MM-DD_Morning" / "…_Evening"
            raw_date = str(df.iloc[1, 0]).replace("GMT", "")
            raw_date = re.sub(r"(\+\d\d):(\d\d)", r"\1\2", raw_date).strip()
            try:
                dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            except Exception:
                dt = datetime.fromtimestamp(os.path.getmtime(file_path))
            session = "Morning" if dt.hour < 12 else "Evening"
            sheet_name = f"{dt.date().isoformat()}_{session}"[:31]

            required = [
                "GPS Time",
                "Speed (OBD)(km/h)",
                "CO\u2082 in g/km (Average)(g/km)",
                "Engine Load(%)",
                "Fuel flow rate/hour(l/hr)",
            ]
            missing = [c for c in required if c not in df.columns]
            if missing:
                text_lines.append(f"{file_name}: missing columns {missing}")
                continue

            duration = gps_to_duration_seconds(df["GPS Time"])
            speed_kmh = pd.to_numeric(df["Speed (OBD)(km/h)"], errors="coerce")
            derived = smooth_and_derive(speed_kmh)

            processed = OrderedDict([
                ("Διάρκεια (sec)", duration),
                ("CO\u2082 in g/km (Average)(g/km)", df["CO\u2082 in g/km (Average)(g/km)"]),
                ("Engine Load(%)", df["Engine Load(%)"]),
                ("Fuel flow rate/hour(l/hr)", df["Fuel flow rate/hour(l/hr)"]),
                ("Εξομαλυνση", derived["smooth_speed"]),
                ("Ταχ m/s", derived["speed_ms"]),
                ("a(m/s2)", derived["acceleration"]),
                ("Επιταχυνση", derived["pos_acc"]),
                ("Επιβραδυνση", derived["neg_acc"]),
            ])
            pd.DataFrame(processed).to_excel(writer, sheet_name=sheet_name, index=False)
            wrote_at_least_one_sheet = True
            text_lines.append(
                f"{file_name}: {derived['smooth_speed'].count()} speed records"
                f" -> {derived['acceleration'].count()} accel values"
            )

        if not wrote_at_least_one_sheet:
            pd.DataFrame({"info": ["No valid data found"]}).to_excel(
                writer, sheet_name="Log", index=False
            )

    with open(text_log, "w", encoding="utf-8") as fp:
        fp.write("\n".join(text_lines))

    return text_log, excel_log


__all__ = ["gps_to_duration_seconds", "smooth_and_derive", "run_calculations"]
