# number_of_stops.py
# ------------------
# Read the newest Calculations log (an Excel workbook),
# count how many times the speed drops to—or below—a chosen
# "stop" threshold for each session (Morning vs Evening),
# and draw a grouped-bar chart.

import os
from datetime import datetime

import pandas as pd          # Excel ↔ DataFrame
import numpy as np           # Small numeric helper
import matplotlib.pyplot as plt

from log_utils import find_latest_log
from metrics import compute_number_of_stops


def show_number_of_stops(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    Build a grouped-bar chart that shows, for each date, how many
    **stop events** occurred in the Morning vs the Evening.

    A *stop event* is defined as a transition from "moving"
    (speed > *stop_threshold_kmh*) to "stopped"
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
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = find_latest_log(log_dir)

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    stop_counts = compute_number_of_stops(sheets, stop_threshold_kmh)

    if not stop_counts:
        raise RuntimeError("No speed data found in any sheet.")

    # Prepare arrays for plotting
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
