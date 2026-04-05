# total_stop_percentage.py
# ------------------------
# Υπολογίζει και σχεδιάζει το συνολικό ποσοστό χρόνου που
# το όχημα είναι Στάσιμο (speed ≤ stop_threshold_kmh) έναντι Κίνησης.

import os

import pandas as pd           # Excel → DataFrame
import matplotlib.pyplot as plt

from log_utils import find_latest_log, get_log_dir
from metrics import compute_total_stop_percentage


def show_total_stop_percentage(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    1.  Load the newest calculations log (or *log_excel_path* if given).
    2.  Collect **every** speed sample from all worksheets.
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
        Speeds ≤ this value count as "stop".
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    pct_stop, pct_move = compute_total_stop_percentage(sheets, stop_threshold_kmh)

    # (0.0, 0.0) means no speed data was found across all sheets
    if pct_stop + pct_move == 0.0:
        print("No speed data available — nothing to plot.")
        return

    # Plot pie chart
    labels   = ["Στάση (%)", "Κίνηση (%)"]
    sizes    = [pct_stop, pct_move]
    explode  = (0.10, 0)           # pop out the "Στάση" slice a bit

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
