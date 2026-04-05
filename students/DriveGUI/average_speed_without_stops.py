# average_speed_without_stops.py
# ------------------------------
# Read the newest Calculations log workbook, calculate the mean
# speed **excluding** stop samples (speed ≤ threshold) for
# ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ on every logged date, and draw a
# grouped-bar chart.

import os
from datetime import datetime

import pandas as pd           # Excel → DataFrame
import numpy as np            # Small numeric helper
import matplotlib.pyplot as plt

from log_utils import find_latest_log, get_log_dir
from metrics import compute_average_speed_without_stops


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
        Speeds ≤ this value count as "stop" and are **excluded** from
        the mean.
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    means = compute_average_speed_without_stops(sheets, stop_threshold_kmh)

    if not means:
        raise ValueError("No sheets contained a 'Ταχ m/s' column.")

    # Prepare arrays for plotting
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
