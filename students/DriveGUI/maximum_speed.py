# maximum_speed.py
# ----------------
# Draw a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows the
# maximum vehicle speed (km/h) for every logged date.

import os
from datetime import datetime

import pandas as pd          # Excel → DataFrame
import numpy as np           # Numeric helper
import matplotlib.pyplot as plt  # Plotting

from log_utils import find_latest_log, get_log_dir
from metrics import compute_maximum_speed


def show_maximum_speed(log_excel_path: str | None = None) -> None:
    """
    Read the latest (or user-chosen) calculations log, pick the column
    **’Ταχ m/s’** from every sheet, convert m/s → km/h, keep the *biggest*
    value, and display results as a grouped-bar chart.

    Parameters
    ----------
    log_excel_path : str | None, optional
        • **None** → auto-select the newest workbook in
          `<script folder>/INPUT/log/`
        • otherwise → use the given file path.
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    maxima = compute_maximum_speed(sheets)

    if not maxima:
        raise ValueError("No sheets contained a ‘Ταχ m/s’ column")

    # Prepare arrays for plotting
    dates = sorted(maxima.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [maxima[d].get("Morning", 0.0) for d in dates]
    evening = [maxima[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in maxima[d].values()])) for d in dates
    ]

    # 5️⃣ Plot the bars
    x = np.arange(len(dates))
    w = 0.25
    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")      # Morning
    plt.bar(x,       evening, width=w, label="ΑΠΟΓΕΥΜΑ")  # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")    # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Μέγιστη Ταχύτητα (km/h)")
    plt.title("Διάγραμμα Μέγιστης Ταχύτητας")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Run the chart if the file is executed directly:
if __name__ == "__main__":
    show_maximum_speed()
