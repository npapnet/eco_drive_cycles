# number_of_stops.py
# ------------------
# Read the newest Calculations log (an Excel workbook),
# count how many times the speed drops to—or below—a chosen
# “stop” threshold for each session (Morning vs Evening),
# and draw a grouped-bar chart.

import os
import glob
from datetime import datetime

import pandas as pd          # Excel ↔ DataFrame
import numpy as np           # Small numeric helper
import matplotlib.pyplot as plt


# ──────────────────────────────────────────────────────────────────
# Helper – locate the newest log workbook inside a folder
# ──────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return the **most recently modified** file that matches
        calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no such file exists in *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    matches = glob.glob(pattern)
    if not matches:                      # nothing found
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(matches, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────
# Main public function (unchanged signature)
# ──────────────────────────────────────────────────────────────────
def show_number_of_stops(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    Build a grouped-bar chart that shows, for each date, how many
    **stop events** occurred in the Morning vs the Evening.

    A *stop event* is defined as a transition from “moving”
    (speed > *stop_threshold_kmh*) to “stopped”
    (speed ≤ *stop_threshold_kmh*).

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → automatically open the newest workbook found in
          `<script folder>/INPUT/log/`
        • otherwise → use the path given by the caller.

    stop_threshold_kmh : float, default=2.0
        Speed (in km/h) ≤ this value counts as a stop.
    """
    # 1️⃣ Decide which workbook to load
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ Read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ For every sheet, count stop-events
    #     result → { '2025-05-14': {'Morning': 17, 'Evening': 12}, ... }
    stop_counts: dict[str, dict[str, int]] = {}
    smoothed_col = "Εξομαλυνση"          # Greek: “Smoothing”

    for sheet_name, df in sheets.items():
        # ➡️ 3a. Pick the speed column (smoothed speed if present,
        #        otherwise the 2nd column as a fallback)
        if smoothed_col in df.columns:
            speeds = df[smoothed_col]
        else:
            speeds = df.iloc[:, 1]
        speeds = pd.to_numeric(speeds, errors="coerce").dropna()

        # ➡️ 3b. Count transitions “moving → stopped”
        was_moving = False   # state flag
        events = 0
        for v in speeds:
            if v > stop_threshold_kmh:
                was_moving = True
            elif v <= stop_threshold_kmh and was_moving:
                events += 1
                was_moving = False

        # ➡️ 3c. Extract date + session from sheet name 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        stop_counts.setdefault(date_str, {})[session] = events

    if not stop_counts:
        raise RuntimeError("No speed data found in any sheet.")

    # 4️⃣ Prepare arrays for plotting
    dates = sorted(stop_counts.keys(), key=lambda d: datetime.fromisoformat(d))
    morning_vals = [stop_counts[d].get("Morning", 0) for d in dates]
    evening_vals = [stop_counts[d].get("Evening", 0) for d in dates]

    # 5️⃣ Draw grouped bars
    x = np.arange(len(dates))
    bar_w = 0.35

    plt.figure(figsize=(9, 6))
    plt.bar(x - bar_w / 2, morning_vals, width=bar_w, label="ΠΡΩΙ")      # Morning
    plt.bar(x + bar_w / 2, evening_vals, width=bar_w, label="ΑΠΟΓΕΥΜΑ")  # Evening

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Αριθμός Στάσεων")
    plt.title("Διάγραμμα Αριθμού Στάσεων ανά Ημερομηνία")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow running the chart with `pytho
