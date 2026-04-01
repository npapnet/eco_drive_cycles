# engine_load.py
# --------------
# Plot the average engine load (%) for each date and session
# (Morning, Evening, and Overall) based on the most-recent
# calculations log Excel workbook.

import os
import glob
from datetime import datetime

import numpy as np          # For simple maths
import pandas as pd         # For reading Excel
import matplotlib.pyplot as plt  # For plotting


# ------------------------------------------------------------------
# Helper function
# ------------------------------------------------------------------
def _find_latest_log(log_dir: str) -> str:
    """
    Search *log_dir* for files that look like
        calculations_log_YYYYMMDD_HHMMSS.xlsx
    and return the **most-recent** one.

    Parameters
    ----------
    log_dir : str
        Folder that contains the log workbooks.

    Returns
    -------
    str
        Full path of the newest log workbook.

    Raises
    ------
    FileNotFoundError
        If no workbook is found in *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    log_files = glob.glob(pattern)

    if not log_files:                       # Nothing found → stop early
        raise FileNotFoundError(
            f"No log files found in {log_dir}"
        )

    # `max` with *key=os.path.getmtime* gives the most-recent file
    latest_log = max(log_files, key=os.path.getmtime)
    return latest_log


# ------------------------------------------------------------------
# Main public function
# ------------------------------------------------------------------
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
    # ------------------------------------------------------------------
    # 1. Decide which workbook to use
    # ------------------------------------------------------------------
    if log_excel_path is None:
        # <this script>/INPUT/log
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # ------------------------------------------------------------------
    # 2. Read every worksheet into a dict of DataFrames
    # ------------------------------------------------------------------
    work_sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # Will end up like:
    # {
    #   '2025-05-14_Morning': 52.4,
    #   '2025-05-14_Evening': 48.1,
    #   ...
    # }
    mean_loads: dict[str, float] = {}

    for sheet_name, sheet_df in work_sheets.items():
        # Skip sheets that do not contain the required column
        if "Engine Load(%)" not in sheet_df.columns:
            continue

        # Convert the column to numbers (coerce errors to NaN) and drop NaNs
        col = pd.to_numeric(sheet_df["Engine Load(%)"],
                            errors="coerce").dropna()
        if col.empty:
            continue

        # Mean value for this sheet
        mean_loads[sheet_name] = float(col.mean())

    if not mean_loads:
        raise ValueError("No sheets contained an 'Engine Load(%)' column.")

    # ------------------------------------------------------------------
    # 3. Split keys into date + session and rearrange for plotting
    # ------------------------------------------------------------------
    # Build a dict like:
    # {
    #   '2025-05-14': {'Morning': 52.4, 'Evening': 48.1},
    #   ...
    # }
    loads_by_date: dict[str, dict[str, float]] = {}
    for sheet_key, value in mean_loads.items():
        if "_" in sheet_key:
            date_str, session = sheet_key.split("_", 1)
        else:                                # Fallback just in case
            date_str, session = sheet_key, "Unknown"

        loads_by_date.setdefault(date_str, {})[session] = value

    # Sort by calendar date
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
