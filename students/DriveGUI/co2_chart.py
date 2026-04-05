# co2_chart.py
# ------------
# Read the newest Calculations-log workbook and draw a grouped-bar chart
# showing the mean CO₂ emissions (g/km) for ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ
# on each logged date.

import os
from datetime import datetime

import pandas as pd        # Excel → DataFrame
import numpy as np         # Tiny numeric helper
import matplotlib.pyplot as plt

from log_utils import find_latest_log, get_log_dir
from metrics import compute_co2_emissions


def show_co2_emissions(log_excel_path: str | None = None) -> None:
    """
    Build a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows, for
    every logged date, the mean value of column
        'CO₂ in g/km (Average)(g/km)'.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → automatically open the newest workbook found in
          `<script folder>/INPUT/log/`
        • otherwise → use the provided file path.
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    means = compute_co2_emissions(sheets)

    if not means:
        raise ValueError("No sheets contained a 'CO₂ in g/km (Average)(g/km)' column.")

    # Prepare arrays for plotting
    dates = sorted(means.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [means[d].get("Morning", 0.0) for d in dates]
    evening = [means[d].get("Evening", 0.0) for d in dates]
    overall = [float(np.mean(list(means[d].values()))) for d in dates]

    # 2️⃣.5 Draw grouped bars
    import numpy as _np
    x = _np.arange(len(dates))
    w = 0.25

    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")       # Morning
    plt.bar(x,       evening, width=w, label="ΑΠΟΓΕΥΜΑ")   # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")     # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Εκπομπές CO₂ (g/km)")
    plt.title("Διάγραμμα Εκπομπών CO₂")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow quick test with:  python co2_chart.py
if __name__ == "__main__":
    show_co2_emissions()
