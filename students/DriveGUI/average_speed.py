# average_speed.py
# ----------------
# Διαβάζει το νεότερο αρχείο Calculations Log, υπολογίζει τη μέση
# ταχύτητα (km/h) για ΠΡΩΙ • ΑΠΟΓΕΥΜΑ • ΣΥΝΟΛΟ ανά ημερομηνία
# και παράγει ομαδοποιημένο ραβδόγραμμα (grouped-bar chart).

import os
import pandas as pd          # Excel → DataFrame
import numpy as np           # small numeric helper
import matplotlib.pyplot as plt
from datetime import datetime

from log_utils import find_latest_log, get_log_dir
from metrics import compute_average_speed


# ────────────────────────────────────────────────────────────────
# Main public function – API unchanged
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
    # Decide which workbook to load
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    # Read every worksheet into a dict {sheet_name: DataFrame}
    sheets = pd.read_excel(log_excel_path, sheet_name=None)

    # Compute mean speed per date & session
    means = compute_average_speed(sheets)

    if not means:
        raise ValueError("No sheets contained a 'Ταχ m/s' column.")

    # Prepare arrays for plotting
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
