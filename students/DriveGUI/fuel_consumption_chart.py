# fuel_consumption_chart.py
# -------------------------
# Plot the mean *Fuel flow rate/hour (l/hr)* for each date and session
# (Morning • Evening • Overall) using the most-recent calculations log.

import os
import glob
from datetime import datetime

import pandas as pd           # Excel ⇄ DataFrame
import numpy as np            # Maths helper
import matplotlib.pyplot as plt  # Charts


# ──────────────────────────────────────────────────────────────────
# Helper – find newest log workbook
# ──────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Look inside *log_dir* for files called
        calculations_log_YYYYMMDD_HHMMSS.xlsx
    and return the **newest one** (by modified-time).

    Raises
    ------
    FileNotFoundError
        If the folder is empty / no matching files.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                       # none found ⇒ bail out
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────
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
    # 1️⃣ pick workbook
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ read every worksheet into a dict
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ compute mean flow per date+session
    #     result → { "2025-05-14": {"Morning": 3.2, "Evening": 2.9}, ... }
    means: dict[str, dict[str, float]] = {}
    target_col = "Fuel flow rate/hour(l/hr)"

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # skip irrelevant sheets

        # clean numeric column
        flow = pd.to_numeric(df[target_col], errors="coerce").dropna()
        if flow.empty:
            continue
        mean_val = float(flow.mean())

        # split sheet name like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        means.setdefault(date_str, {})[session] = mean_val

    if not means:
        raise ValueError(f"No sheets contained '{target_col}'")

    # 4️⃣ prepare arrays for plotting
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
