# average_speed_without_stops.py
# ------------------------------
# Read the newest Calculations log workbook, calculate the mean
# speed **excluding** stop samples (speed ≤ threshold) for
# ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ on every logged date, and draw a
# grouped-bar chart.

import os
import glob
from datetime import datetime

import pandas as pd           # Excel → DataFrame
import numpy as np            # Small numeric helper
import matplotlib.pyplot as plt


# ────────────────────────────────────────────────────────────────
# 1. Helper – return newest “calculations_log_*.xlsx” in a folder
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Inside *log_dir* look for filenames like

        calculations_log_YYYYMMDD_HHMMSS.xlsx

    and return **the most-recently modified** one.

    Raises
    ------
    FileNotFoundError
        If no matching file exists.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                      # nothing found → stop early
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# 2. Main public function – API unchanged
# ────────────────────────────────────────────────────────────────
def show_average_speed_without_stops(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    Build a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows, for
    each logged date, the **mean speed in km/h while moving** (i.e. rows
    whose speed is > *stop_threshold_kmh*).

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → automatically open the newest workbook in
          `<script folder>/INPUT/log/`
        • otherwise → use the supplied file path.

    stop_threshold_kmh : float, default=2.0
        Speeds ≤ this value count as “stop” and are **excluded** from
        the mean.
    """
    # 2️⃣.1 Decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣.2 Load every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 2️⃣.3 Compute mean-moving-speed per date & session
    #       Result → { '2025-05-14': {'Morning': 33.1, 'Evening': 30.9}, … }
    means: dict[str, dict[str, float]] = {}
    target_col = "Ταχ m/s"            # Greek header: “Speed (m/s)”

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # skip sheets without speed data

        # ➡️ Clean numeric column & drop NaNs
        speed_ms = pd.to_numeric(df[target_col], errors="coerce").dropna()
        if speed_ms.empty:
            mean_kmh = 0.0
        else:
            #   1. convert to km/h
            speed_kmh = speed_ms * 3.6
            #   2. keep only rows > threshold
            moving = speed_kmh[speed_kmh > stop_threshold_kmh]
            mean_kmh = float(moving.mean()) if not moving.empty else 0.0

        # ➡️ Split sheet name like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        means.setdefault(date_str, {})[session] = mean_kmh

    if not means:
        raise ValueError(f"No sheets contained a '{target_col}' column.")

    # 2️⃣.4 Prepare arrays for plotting
    dates = sorted(means.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [means[d].get("Morning", 0.0) for d in dates]
    evening = [means[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in means[d].values()])) for d in dates
    ]

    # 2️⃣.5 Draw grouped bars
    x = np.arange(len(dates))
    w = 0.25

    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")        # Morning
    plt.bar(x,     evening, width=w, label="ΑΠΟΓΕΥΜΑ")    # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")      # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Μέση Ταχύτητα χωρίς Στάσεις (km/h)")
    plt.title("Διάγραμμα Μέσης Ταχύτητας Χωρίς Στάσεις")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow quick test with:  python average_speed_without_stops.py
if __name__ == "__main__":
    show_average_speed_without_stops()
