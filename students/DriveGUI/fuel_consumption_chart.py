# fuel_consumption_chart.py
# -------------------------
# Plot the mean *Fuel flow rate/hour (l/hr)* for each date and session
# (Morning • Evening • Overall) using the most-recent calculations log.

import os
from datetime import datetime

import pandas as pd           # Excel ⇄ DataFrame
import numpy as np            # Maths helper
import matplotlib.pyplot as plt  # Charts

from log_utils import find_latest_log
from metrics import compute_fuel_consumption


def show_fuel_consumption(log_excel_path: str | None = None) -> None:
    """
    Build a grouped-bar chart (Morning • Evening • Overall) showing the mean
    *Fuel flow rate/hour(l/hr)* for every date in the chosen calculations log.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → automatically select newest workbook in
          `<this script>/INPUT/log/`
        • otherwise → use the provided file path.
    """
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = find_latest_log(log_dir)

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    means = compute_fuel_consumption(sheets)

    if not means:
        raise ValueError("No sheets contained 'Fuel flow rate/hour(l/hr)'")

    # Prepare arrays for plotting
    dates = sorted(means.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [means[d].get("Morning", 0.0) for d in dates]
    evening = [means[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in means[d].values()])) for d in dates
    ]

    # 5️⃣ plot
    x = np.arange(len(dates))
    w = 0.25

    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")        # Morning
    plt.bar(x,     evening, width=w, label="ΑΠΟΓΕΥΜΑ")    # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")      # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Ροή Καυσίμου (L/hr)")
    plt.title("Διάγραμμα Ροής Καυσίμου")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Keep the original accidental alias so old scripts still run.
show_fuel_flow = show_fuel_consumption

if __name__ == "__main__":
    show_fuel_flow()
