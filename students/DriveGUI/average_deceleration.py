# average_deceleration.py
# -----------------------
# Read the newest Calculations log workbook, pull the column
# 'Επιβραδυνση' (deceleration), keep *only* the negative values,
# and draw a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows
# the mean deceleration (m/s²) for each logged date.

import os
from datetime import datetime

import pandas as pd          # Excel → DataFrame
import numpy as np           # Small numeric helper
import matplotlib.pyplot as plt

from log_utils import find_latest_log, get_log_dir
from metrics import compute_average_deceleration


def show_average_deceleration(log_excel_path: str | None = None) -> None:
    """
    Build a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows, for
    each logged date, the **mean negative deceleration** values in column
    'Επιβραδυνση'.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → automatically pick the newest workbook found in
          `<script folder>/INPUT/log/`
        • otherwise → use the file path supplied by the caller.
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    means = compute_average_deceleration(sheets)

    if not means:
        raise ValueError("No sheets contained an 'Επιβραδυνση' column.")

    # Prepare arrays for plotting
    dates = sorted(means.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [means[d].get("Morning", 0.0) for d in dates]
    evening = [means[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in means[d].values()])) for d in dates
    ]

    # 5️⃣ draw grouped bars
    x = np.arange(len(dates))
    w = 0.25

    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")        # Morning
    plt.bar(x,     evening, width=w, label="ΑΠΟΓΕΥΜΑ")    # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")      # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Μέση Επιβράδυνση (m/s²)")
    plt.title("Διάγραμμα Μέσης Επιβράδυνσης")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow quick test with:  python average_deceleration.py
if __name__ == "__main__":
    show_average_deceleration()
