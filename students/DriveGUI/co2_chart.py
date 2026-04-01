# co2_chart.py
# ------------
# Read the newest Calculations-log workbook and draw a grouped-bar chart
# showing the mean CO₂ emissions (g/km) for ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ
# on each logged date.

import os
import glob
from datetime import datetime

import pandas as pd        # Excel → DataFrame
import numpy as np         # Tiny numeric helper
import matplotlib.pyplot as plt


# ────────────────────────────────────────────────────────────────
# 1. Helper – locate the newest calculations_log_*.xlsx
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return the **most-recently modified** Excel workbook whose filename
        matches  calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If *log_dir* does not contain any matching file.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                          # nothing found → bail out
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# 2. Main public function – API unchanged
# ────────────────────────────────────────────────────────────────
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
    # 2️⃣.1 Decide which workbook to load
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣.2 Read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 2️⃣.3 Compute mean CO₂ per date & session
    #       Result → { '2025-05-14': {'Morning': 131.2, 'Evening': 127.8}, … }
    means: dict[str, dict[str, float]] = {}
    target_col = "CO₂ in g/km (Average)(g/km)"

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # skip irrelevant sheets

        co2 = pd.to_numeric(df[target_col], errors="coerce").dropna()
        mean_val = float(co2.mean()) if not co2.empty else 0.0

        # Sheet names look like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        means.setdefault(date_str, {})[session] = mean_val

    if not means:
        raise ValueError(f"No sheets contained a '{target_col}' column.")

    # 2️⃣.4 Prepare arrays for plotting
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
