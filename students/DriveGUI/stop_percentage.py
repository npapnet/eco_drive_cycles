# stop_percentage.py
# ------------------
# Plot (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ) the % of samples where the vehicle
# is “stopped” (speed ≤ stop_threshold_kmh) for every logged date.

import os
import glob
import pandas as pd          # Excel → DataFrame
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime


# ────────────────────────────────────────────────────────────────
# Helper – return newest calculations_log_YYYYMMDD_HHMMSS.xlsx
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Find the **most-recently modified** calculations_log_*.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no such file exists.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# Main entry point (API stays exactly the same)
# ────────────────────────────────────────────────────────────────
def show_stop_percentage(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    Build a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ) that shows, for each
    date, what percentage of *speed* samples are ≤ *stop_threshold_kmh*.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → auto-select newest workbook in `<script>/INPUT/log/`
        • otherwise → use the provided file path.

    stop_threshold_kmh : float, default=2.0
        Speeds ≤ this value count as “stop”.
    """
    # 1️⃣ choose workbook
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ load every worksheet
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ compute stop % for each date & session
    #     result → { '2025-05-14': {'Morning': 12.3, 'Evening': 15.7}, … }
    percentages: dict[str, dict[str, float]] = {}
    for sheet_name, df in sheets.items():
        # a) pick speed column: prefer smoothed ('Εξομαλυνση'), else 2nd col
        col = df["Εξομαλυνση"] if "Εξομαλυνση" in df.columns else df.iloc[:, 1]
        speeds = pd.to_numeric(col, errors="coerce").dropna()

        # b) convert m/s → km/h if evident (all values tiny)
        if speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6

        if speeds.empty:
            pct_stop = 0.0
        else:
            pct_stop = (speeds.le(stop_threshold_kmh).sum() / len(speeds)) * 100

        # c) split sheet name 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        percentages.setdefault(date_str, {})[session] = pct_stop

    if not percentages:
        raise RuntimeError("No usable speed data found in any sheet.")

    # 4️⃣ prepare arrays for plotting
    dates = sorted(percentages.keys(), key=lambda d: datetime.fromisoformat(d))
    morning_vals = [percentages[d].get("Morning", 0.0) for d in dates]
    evening_vals = [percentages[d].get("Evening", 0.0) for d in dates]

    # 5️⃣ draw grouped bars
    x = np.arange(len(dates))
    bar_w = 0.35

    plt.figure(figsize=(9, 6))
    plt.bar(x - bar_w / 2, morning_vals, width=bar_w, label="ΠΡΩΙ")
    plt.bar(x + bar_w / 2, evening_vals, width=bar_w, label="ΑΠΟΓΕΥΜΑ")

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Ποσοστό Στάσης (%)")
    plt.title("Ποσοστό Στάσης ανά Ημερομηνία")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow running the chart via `python stop_percentage.py`
if __name__ == "__main__":
    show_stop_percentage()
