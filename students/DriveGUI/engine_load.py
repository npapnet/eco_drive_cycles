# engine_load.py
# --------------
# Plot the average engine load (%) for each date and session
# (Morning, Evening, and Overall) based on the most-recent
# calculations log Excel workbook.

import os
from datetime import datetime

import numpy as np          # For simple maths
import pandas as pd         # For reading Excel
import matplotlib.pyplot as plt  # For plotting

from log_utils import find_latest_log
from metrics import compute_engine_load


def show_engine_load(log_excel_path: str | None = None) -> None:
    """
    Read the chosen (or latest) calculations log workbook, calculate the
    mean *Engine Load (%)* for every date/session sheet, and display the
    results as a grouped-bar chart.

    Parameters
    ----------
    log_excel_path : str | None, optional
        Full path of the workbook to use.
        • If **None** (default) the newest workbook inside
          `<this script>/INPUT/log/` is selected automatically.
    """
    if log_excel_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "INPUT", "log")
        log_excel_path = find_latest_log(log_dir)

    work_sheets = pd.read_excel(log_excel_path, sheet_name=None)
    loads_by_date = compute_engine_load(work_sheets)

    if not loads_by_date:
        raise ValueError("No sheets contained an 'Engine Load(%)' column.")

    sorted_dates = sorted(
        loads_by_date.keys(),
        key=lambda d: datetime.fromisoformat(d)
    )

    # Build three parallel lists for the bars
    morning_vals = [loads_by_date[d].get("Morning", 0.0)
                    for d in sorted_dates]
    evening_vals = [loads_by_date[d].get("Evening", 0.0)
                    for d in sorted_dates]
    # Overall average (simply the mean of Morning & Evening if both exist)
    total_vals = [
        np.mean([v for sess, v in loads_by_date[d].items()
                 if sess in ("Morning", "Evening")])
        for d in sorted_dates
    ]

    # ------------------------------------------------------------------
    # 4. Plot
    # ------------------------------------------------------------------
    x_pos = np.arange(len(sorted_dates))
    bar_width = 0.25

    plt.bar(x_pos - bar_width, morning_vals,
            width=bar_width, label="ΠΡΩΙ")
    plt.bar(x_pos,             evening_vals,
            width=bar_width, label="ΑΠΟΓΕΥΜΑ")
    plt.bar(x_pos + bar_width, total_vals,
            width=bar_width, label="ΣΥΝΟΛΟ")

    plt.xticks(x_pos, sorted_dates, rotation=45)
    plt.xlabel("Ημερομηνίες")        # Dates
    plt.ylabel("Φορτίο Μηχανής (%)")  # Engine load
    plt.title("Διάγραμμα Φορτίου Μηχανής")
    plt.legend()
    plt.tight_layout()
    plt.show()


# When run directly (e.g. `python engine_load.py`) run the chart
if __name__ == "__main__":
    show_engine_load()
