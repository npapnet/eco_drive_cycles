# stop_percentage.py
# ------------------
# Plot (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ) the % of samples where the vehicle
# is "stopped" (speed ≤ stop_threshold_kmh) for every logged date.

import os
import pandas as pd          # Excel → DataFrame
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

from log_utils import find_latest_log
from metrics import compute_stop_percentage


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
        Speeds ≤ this value count as "stop".
    """
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = find_latest_log(log_dir)

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    percentages = compute_stop_percentage(sheets, stop_threshold_kmh)

    if not percentages:
        raise RuntimeError("No usable speed data found in any sheet.")

    # Prepare arrays for plotting
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
