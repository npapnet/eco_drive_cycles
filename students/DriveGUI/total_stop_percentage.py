# total_stop_percentage.py
# ------------------------
# Υπολογίζει και σχεδιάζει το συνολικό ποσοστό χρόνου που
# το όχημα είναι Στάσιμο (speed ≤ stop_threshold_kmh) έναντι Κίνησης.

import os
import glob
from datetime import datetime

import pandas as pd           # Excel → DataFrame
import matplotlib.pyplot as plt
import numpy as np            # Numeric helper (only for NaN checks)

# ────────────────────────────────────────────────────────────────
# Helper – find the newest calculations log workbook
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return **the most-recently modified** Excel workbook whose filename
        matches  calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no matching files exist in *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:  # empty list → nothing found
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# Main public function (API unchanged)
# ────────────────────────────────────────────────────────────────
def show_total_stop_percentage(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    1.  Load the newest calculations log (or *log_excel_path* if given).
    2.  Collect **every** speed sample from all worksheets
        –  prefer the smoothed column 'Εξομαλυνση', else column B.
    3.  Classify each sample as  Στάση  (speed ≤ *stop_threshold_kmh*)
        or  Κίνηση  (speed  > *stop_threshold_kmh*).
    4.  Draw a simple pie chart showing the overall percentages.

    Parameters
    ----------
    log_excel_path : str | None, default=None
        • **None** → look inside `<script folder>/INPUT/log/` for the
          newest *calculations_log_*.xlsx* file.  
        • Otherwise → use the given workbook path.

    stop_threshold_kmh : float, default=2.0
        Speeds ≤ this value count as “stop”.
    """
    # 1️⃣ Decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ Read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ Scan all rows – accumulate total & stop samples
    total_samples = 0
    stop_samples = 0

    for df in sheets.values():
        # Prefer 'Εξομαλυνση' (smoothed speed); otherwise 2nd column
        speeds = (
            df["Εξομαλυνση"]
            if "Εξομαλυνση" in df.columns
            else df.iloc[:, 1]
        ).dropna()

        if speeds.empty:           # no data → skip
            continue

        # Convert units if values look like m/s
        if speeds.max() < stop_threshold_kmh:
            speeds = speeds * 3.6  # m/s → km/h

        total_samples += len(speeds)
        stop_samples  += int((speeds <= stop_threshold_kmh).sum())

    if total_samples == 0:
        print("No speed data available — nothing to plot.")
        return

    # 4️⃣ Compute percentages
    pct_stop = (stop_samples / total_samples) * 100
    pct_move = 100 - pct_stop

    # 5️⃣ Plot pie chart
    labels   = ["Στάση (%)", "Κίνηση (%)"]
    sizes    = [pct_stop, pct_move]
    explode  = (0.10, 0)           # pop out the “Στάση” slice a bit

    plt.figure(figsize=(6, 6))
    plt.pie(
        sizes,
        labels=labels,
        explode=explode,
        autopct=lambda p: f"{p:.2f} %",
        startangle=90,
        shadow=True
    )
    plt.title("Συνολικό Ποσοστό Στάσης")
    plt.axis("equal")  # keep the pie perfectly round
    plt.tight_layout()
    plt.show()


# Run the pie chart if someone types:  python total_stop_percentage.py
if __name__ == "__main__":
    show_total_stop_percentage()
