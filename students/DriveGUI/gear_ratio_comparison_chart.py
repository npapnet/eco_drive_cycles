# gear_ratio_comparison_chart.py
# ------------------------------
# Plot, for every gear (1η-5η), the percentage of samples recorded in
# the Morning versus the Evening, reading data from the newest
# calculations log Excel workbook.

import os
import glob
from datetime import datetime

import pandas as pd          # Excel ↔ DataFrame
import matplotlib.pyplot as plt
import numpy as np


# ──────────────────────────────────────────────────────────────────
# Helper – locate the newest log workbook
# ──────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return the full path of the **most-recently modified**
    `calculations_log_YYYYMMDD_HHMMSS.xlsx` found inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no such file exists in *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                            # nothing found
        raise FileNotFoundError(f"No log files in {log_dir}")
    return max(files, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────
# Main public function
# ──────────────────────────────────────────────────────────────────
def show_gear_ratio_comparison(log_excel_path: str | None = None) -> None:
    """
    1. Pick the newest calculations log (or use *log_excel_path* if given)
    2. From every sheet pull the column **'Ταχύτητες στο κιβώτιο'**
       (integer gears 1-5).
    3. Count how many rows fall into each gear for **Morning** and **Evening**.
    4. Convert counts → percentages and draw a grouped bar chart.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → search `<script folder>/INPUT/log` for the newest file  
        • otherwise → use the provided workbook path
    """
    # 1️⃣ decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ accumulate gear counts per session (Morning, Evening)
    counts: dict[str, pd.Series] = {
        "Morning": pd.Series(dtype=int),
        "Evening": pd.Series(dtype=int)
    }
    target_col = "Ταχύτητες στο κιβώτιο"      # "Gears in gearbox"

    for sheet_name, df in sheets.items():
        # Extract session from sheet name: 'YYYY-MM-DD_Morning'
        if "_" not in sheet_name:
            continue
        _, session = sheet_name.split("_", 1)
        if session not in counts:
            continue

        # Skip sheets without the column
        if target_col not in df.columns:
            continue

        # Clean column → int gears, drop NaNs
        gears = pd.to_numeric(df[target_col], errors="coerce").dropna().astype(int)
        gear_counts = gears.value_counts().reindex(range(1, 6), fill_value=0)
        # Add to running total
        counts[session] = counts[session].add(gear_counts, fill_value=0)

    # 4️⃣ convert counts → percentages
    pct: dict[str, pd.Series] = {}
    for session, series in counts.items():
        total = series.sum()
        if total == 0:
            pct[session] = pd.Series([0] * 5, index=range(1, 6))
        else:
            pct[session] = (series / total * 100).reindex(range(1, 6))

    # 5️⃣ plot grouped bars (five small bars per session)
    sessions = ["Morning", "Evening"]
    session_labels = ["ΠΡΩΙ", "ΑΠΟΓΕΥΜΑ"]
    gear_labels = ["1η", "2η", "3η", "4η", "5η"]

    x_base = np.arange(len(sessions))
    bar_w = 0.15                       # narrow bars so five fit per group

    plt.figure(figsize=(9, 6))
    for i, gear in enumerate(range(1, 6)):
        heights = [pct[s].loc[gear] for s in sessions]
        plt.bar(x_base + (i - 2) * bar_w, heights,
                width=bar_w, label=f"{gear}η")  # e.g. "1η"

    plt.xticks(x_base, session_labels)
    plt.ylabel("Ποσοστό (%)")
    plt.title("Διάγραμμα Σύγκρισης Σχέσεων Μετάδοσης (1η-5η)")
    plt.legend(title="Ταχύτητα")
    plt.tight_layout()
    plt.show()


# Convenience – run the chart if this file is executed directly
if __name__ == "__main__":
    show_gear_ratio_comparison()
