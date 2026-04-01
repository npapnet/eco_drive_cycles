# average_deceleration.py
# -----------------------
# Read the newest Calculations log workbook, pull the column
# 'Επιβραδυνση' (deceleration), keep *only* the negative values,
# and draw a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows
# the mean deceleration (m/s²) for each logged date.

import os
import glob
from datetime import datetime

import pandas as pd          # Excel → DataFrame
import numpy as np           # Small numeric helper
import matplotlib.pyplot as plt


# ────────────────────────────────────────────────────────────────
# Helper – find newest “calculations_log_*.xlsx” in a folder
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Inside *log_dir* look for files called

        calculations_log_YYYYMMDD_HHMMSS.xlsx

    and return **the most-recently modified** one.

    Raises
    ------
    FileNotFoundError
        If the folder contains no matching files.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                       # Nothing found → bail out
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# Main public function – API unchanged
# ────────────────────────────────────────────────────────────────
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
    # 1️⃣ decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ load every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ compute mean *negative* deceleration per date & session
    #     will end up like {'2025-05-14': {'Morning': -0.38, 'Evening': -0.42}, …}
    means: dict[str, dict[str, float]] = {}
    target_col = "Επιβραδυνση"          # Greek header: “Deceleration”

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # skip irrelevant sheets

        # clean numeric column, drop NaNs
        decel = pd.to_numeric(df[target_col], errors="coerce").dropna()
        # keep only the negative values (actual braking)
        braking = decel[decel < 0]
        mean_val = float(braking.mean()) if not braking.empty else 0.0

        # split sheet name like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        means.setdefault(date_str, {})[session] = mean_val

    if not means:
        raise ValueError(f"No sheets contained an '{target_col}' column.")

    # 4️⃣ prepare arrays for plotting
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
