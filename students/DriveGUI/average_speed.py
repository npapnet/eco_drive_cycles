# average_speed.py
# ----------------
# Διαβάζει το νεότερο αρχείο Calculations Log, υπολογίζει τη μέση
# ταχύτητα (km/h) για ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ ανά ημερομηνία
# και παράγει ομαδοποιημένο ραβδόγραμμα (grouped-bar chart).

import os
import glob
import pandas as pd          # Excel → DataFrame
import numpy as np           # small numeric helper
import matplotlib.pyplot as plt
from datetime import datetime

# ────────────────────────────────────────────────────────────────
# 1. Helper – locate the newest calculations_log_*.xlsx
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return the **most recently modified** Excel workbook whose filename
        matches  calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.

    Raises
    ------
    FileNotFoundError
        If no such log exists in *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:                       # nothing found → bail out
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# 2. Main public function – API unchanged
# ────────────────────────────────────────────────────────────────
def show_average_speed(log_excel_path: str | None = None) -> None:
    """
    Build a grouped-bar chart (ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ) that shows,
    for every logged date, the mean speed taken from column 'Ταχ m/s'.

    • Speeds are stored in **metres per second** (m/s) – so we multiply
      every mean by 3.6 to convert to km/h.
    • If *log_excel_path* is **None**, the newest workbook found in
      `<script folder>/INPUT/log/` is opened automatically.
    """
    # 2️⃣.1 Decide which workbook to load
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣.2 Read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # 2️⃣.3 Compute mean speed per date & session
    #       Result → { '2025-05-14': {'Morning': 34.2, 'Evening': 31.8}, … }
    means: dict[str, dict[str, float]] = {}
    target_col = "Ταχ m/s"             # Greek header: “Speed (m/s)”

    for sheet_name, df in sheets.items():
        if target_col not in df.columns:
            continue  # skip irrelevant sheets

        # ➡️ Clean numeric column, drop NaNs
        speed_ms = pd.to_numeric(df[target_col], errors="coerce").dropna()
        mean_kmh = float(speed_ms.mean() * 3.6) if not speed_ms.empty else 0.0

        # ➡️ Sheet names look like 'YYYY-MM-DD_Morning'
        date_str, session = (sheet_name.split("_", 1) + ["Unknown"])[:2]
        means.setdefault(date_str, {})[session] = mean_kmh

    if not means:
        raise ValueError(f"No sheets contained a '{target_col}' column.")

    # 2️⃣.4 Prepare arrays for plotting
    dates = sorted(means.keys(), key=lambda d: datetime.fromisoformat(d))
    morning = [means[d].get("Morning", 0.0) for d in dates]
    evening = [means[d].get("Evening", 0.0) for d in dates]
    overall = [
        float(np.mean([v for v in means[d].values()])) for d in dates
    ]

    # 2️⃣.5 Draw grouped bars
    x = np.arange(len(dates))
    w = 0.25

    plt.figure(figsize=(9, 6))
    plt.bar(x - w, morning, width=w, label="ΠΡΩΙ")          # Morning
    plt.bar(x,     evening, width=w, label="ΑΠΟΓΕΥΜΑ")      # Evening
    plt.bar(x + w, overall,  width=w, label="ΣΥΝΟΛΟ")        # Overall

    plt.xticks(x, dates, rotation=45)
    plt.xlabel("Ημερομηνίες")
    plt.ylabel("Μέση Ταχύτητα (km/h)")
    plt.title("Διάγραμμα Μέσης Ταχύτητας")
    plt.legend()
    plt.tight_layout()
    plt.show()


# Allow quick test with:  python average_speed.py
if __name__ == "__main__":
    show_average_speed()
