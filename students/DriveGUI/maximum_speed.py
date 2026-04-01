# maximum_speed.py
# ----------------
# Draw a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows the
# maximum vehicle speed (km/h) for every logged date.

import os
import glob
from datetime import datetime

import pandas as pd          # Excel → DataFrame
import numpy as np           # Numeric helper
import matplotlib.pyplot as plt  # Plotting


# ──────────────────────────────────────────────────────────────────
# Helper – find the newest “calculations_log_*.xlsx” in a folder
# ──────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return the **most recently modified** Excel workbook that matches
        calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no matching files exist.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    matches = glob.glob(pattern)

    if not matches:                       # empty list → nothing found
        raise FileNotFoundError(f"No log files found in {log_dir}")

    # `max` with *key=os.path.getmtime* selects the newest file
    return max(matches, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────
# Main public function
# ──────────────────────────────────────────────────────────────────
def show_maximum_speed(log_excel_path: str | None = None) -> None:
    """
    Read the latest (or user-chosen) calculations log, pick the column
    **'Ταχ m/s'** from every sheet, convert m/s → km/h, keep the *biggest*
    value, and display results as a grouped-bar chart.

    Parameters
    ----------
    log_excel_path : str | None, optional
        • **None** → auto-select the newest workbook in
          `<script folder>/INPUT/log/`
        • otherwise → use the given file path.
    """
    # 1️⃣ Decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣ Load every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 3️⃣ Extract max speed per date + session
    #     Will become → { '2025-05-14': {'Morning': 82.3, 'Evening': 77.1}, ... }
    maxima: dict[str, dict[str, float]] = {}
    target_col = "Ταχ m/s"        # Greek header: “Speed (m/s)”

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # Skip if the sheet doesn’t have speed data

        speeds_ms = pd.to_numeric(df[target_col], errors="coerce").dropna()
        max_kmh = float((speeds_ms * 3.6).max()) if not speeds_ms.empty else 0.0

        # Sheet names look like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        maxima.setdefault(date_str, {})[session] = max_kmh

    if not maxima:
        raise ValueError(f"No sheets contained a '{target_col}' column")

    # 4️⃣ Prepare arrays for plotting
    dates = sorted(maxima.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [maxima[d].get("Morning", 0.0) for d in dates]
    evening = [maxima[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in maxima[d].values()])) for d in dates
    ]

    # 5️⃣ Plot the bars
    x = np.arange(len(dates))
    w = 0.25
    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")      # Morning
    plt.bar(x,       evening, width=w, label="ΑΠΟΓΕΥΜΑ")  # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")    # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Μέγιστη Ταχύτητα (km/h)")
    plt.title("Διάγραμμα Μέγιστης Ταχύτητας")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Run the chart if the file is executed directly:
if __name__ == "__main__":
    show_maximum_speed()
