"""
Simple calculations helper for the Driving Cycles project.

It reads every ``.xlsx`` file in a folder, builds some extra columns
(such as smoothed speed and acceleration) and stores the result in a
new Excel workbook.  A plain‑text log with one line per file is also
created so the user can see what happened.

Functions
---------
gps_to_duration_seconds(gps_series)
    Convert a *GPS Time* column to seconds elapsed from the first valid
    record.

smooth_and_derive(speed_kmh)
    Apply rolling smoothing and derive acceleration columns from a raw
    speed series.

run_calculations(folder_path: str, log_folder: str = "log") -> tuple[str, str]
    Process all spreadsheets in *folder_path* and save an **Excel** log
    plus a **text** summary inside *log_folder*.
"""

from __future__ import annotations

import glob
import os
import re
from collections import OrderedDict
from datetime import datetime

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Return *GPS Time* expressed as seconds from start.

    The column coming from the logger is not always the same: sometimes
    it already contains seconds, other times it looks like normal
    time‑of‑day strings.  We try the easy numeric case first and fall
    back to *pandas*' datetime parser if that fails.  Elements that
    cannot be understood become *NaN* so later calculations do not
    crash.
    """

    # 1) Assume the values are already seconds -----------------------------
    numeric = pd.to_numeric(gps_series, errors="coerce")
    if numeric.notna().any():
        first_value = numeric.dropna().iloc[0]
        return numeric - first_value

    # 2) Parse as timestamps / time‑of‑day --------------------------------
    dt = pd.to_datetime(gps_series, errors="coerce", utc=True)
    if dt.notna().any():
        first_dt = dt.dropna().iloc[0]
        return (dt - first_dt).dt.total_seconds()

    # 3) Give up – return an all‑NaN column so the caller can go on -------
    return pd.Series([np.nan] * len(gps_series), index=gps_series.index)


def smooth_and_derive(speed_kmh: pd.Series) -> dict:
    """Apply rolling smoothing and derive acceleration columns.

    Parameters
    ----------
    speed_kmh : pd.Series
        Raw speed values in km/h.

    Returns
    -------
    dict with keys:
        "smooth_speed" – rolling mean (window=4, center=True, min_periods=4), km/h
        "speed_ms"     – smooth_speed / 3.6, m/s
        "acceleration" – speed_ms.diff(), m/s²
        "pos_acc"      – acceleration where > 0 (NaN elsewhere)
        "neg_acc"      – acceleration where < 0 (NaN elsewhere)
    """
    smooth_speed = speed_kmh.rolling(window=4, center=True, min_periods=4).mean()
    speed_ms = smooth_speed / 3.6
    acceleration = speed_ms.diff()
    pos_acc = acceleration.where(acceleration > 0)
    neg_acc = acceleration.where(acceleration < 0)
    return dict(
        smooth_speed=smooth_speed,
        speed_ms=speed_ms,
        acceleration=acceleration,
        pos_acc=pos_acc,
        neg_acc=neg_acc,
    )


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------

def run_calculations(folder_path: str, log_folder: str = "log") -> tuple[str, str]:
    """Create an Excel workbook *and* a text log from the original files.

    Parameters
    ----------
    folder_path : str
        Folder that contains the raw ``.xlsx`` spreadsheets produced by
        the data logger.
    log_folder : str, default "log"
        Where the two log files are saved.  The folder is created if it
        does not exist.

    Returns
    -------
    tuple[str, str]
        Paths to the text log and the Excel log, *in this order*.
    """

    # Make sure the output folder exists ----------------------------------
    os.makedirs(log_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_log = os.path.join(log_folder, f"calculations_log_{timestamp}.xlsx")
    text_log  = os.path.join(log_folder, f"calculations_log_{timestamp}.txt")

    text_lines: list[str] = []  # what we will eventually write to the txt
    wrote_at_least_one_sheet = False  # keep track for the Excel writer

    with pd.ExcelWriter(excel_log, engine="openpyxl") as writer:
        # Loop over every *.xlsx file in the chosen folder ---------------
        for file_path in glob.glob(os.path.join(folder_path, "*.xlsx")):
            file_name = os.path.basename(file_path)

            # Read the spreadsheet --------------------------------------
            try:
                df = pd.read_excel(file_path)
            except Exception as err:
                text_lines.append(f"{file_name}: ERROR reading file ({err})")
                continue  # go to next file

            # Build a sheet name like "YYYY‑MM‑DD_Morning" or "…_Evening" --
            raw_date = str(df.iloc[1, 0]).replace("GMT", "")
            raw_date = re.sub(r"(\+\d\d):(\d\d)", r"\1\2", raw_date).strip()
            try:
                dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            except Exception:
                # If the string is weird fall back to file modification time
                dt = datetime.fromtimestamp(os.path.getmtime(file_path))
            session = "Morning" if dt.hour < 12 else "Evening"
            sheet_name = f"{dt.date().isoformat()}_{session}"[:31]  # Excel max 31 chars

            # Make sure all required columns are present ------------------
            required = [
                "GPS Time",
                "Speed (OBD)(km/h)",
                "CO₂ in g/km (Average)(g/km)",
                "Engine Load(%)",
                "Fuel flow rate/hour(l/hr)",
            ]
            missing = [c for c in required if c not in df.columns]
            if missing:
                text_lines.append(f"{file_name}: missing columns {missing}")
                continue

            # ------------------------------------------------------------------
            # Calculations
            # ------------------------------------------------------------------
            duration = gps_to_duration_seconds(df["GPS Time"])
            speed_kmh = pd.to_numeric(df["Speed (OBD)(km/h)"], errors="coerce")

            derived = smooth_and_derive(speed_kmh)
            smooth_speed = derived["smooth_speed"]
            speed_ms = derived["speed_ms"]
            acceleration = derived["acceleration"]
            pos_acc = derived["pos_acc"]
            neg_acc = derived["neg_acc"]

            # Collect everything in a new DataFrame -----------------------
            processed = OrderedDict([
                ("Διάρκεια (sec)", duration),
                ("CO₂ in g/km (Average)(g/km)", df["CO₂ in g/km (Average)(g/km)"]),
                ("Engine Load(%)", df["Engine Load(%)"]),
                ("Fuel flow rate/hour(l/hr)", df["Fuel flow rate/hour(l/hr)"]),
                ("Εξομαλυνση", smooth_speed),
                ("Ταχ m/s", speed_ms),
                ("a(m/s2)", acceleration),
                ("Επιταχυνση", pos_acc),
                ("Επιβραδυνση", neg_acc),
            ])

            pd.DataFrame(processed).to_excel(writer, sheet_name=sheet_name, index=False)
            wrote_at_least_one_sheet = True

            # Write a short note for the text log -------------------------
            text_lines.append(
                f"{file_name}: {smooth_speed.count()} speed records -> {acceleration.count()} accel values"
            )

        # If nothing was written create a single sheet so the workbook is valid
        if not wrote_at_least_one_sheet:
            pd.DataFrame({"info": ["No valid data found"]}).to_excel(
                writer, sheet_name="Log", index=False
            )

    # Finally write the text log -------------------------------------------
    with open(text_log, "w", encoding="utf-8") as fp:
        fp.write("\n".join(text_lines))

    # Return the paths so the caller can show them -------------------------
    return text_log, excel_log


# ---------------------------------------------------------------------------
# Handy command‑line use
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    log_txt, log_xlsx = run_calculations(folder)
    print("Text log  :", log_txt)
    print("Excel log :", log_xlsx)
