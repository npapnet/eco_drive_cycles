"""speed_profile.py
------------------
Plot **one** diagram—Εξομαλυνση (smoothed speed) versus duration—in
**km/h vs seconds** for the sheet chosen as the
*αντιπροσωπευτική διαδρομή* (representative route).

Only the smoothed column is shown (blue).  The raw Ταχ m/s curve has
been removed per user request.

Public helper
-------------
>>> from speed_profile import show_representative_speed_profile
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import pandas as pd

from log_utils import find_latest_log, get_log_dir
from metrics import compute_speed_profile


def show_representative_speed_profile(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    data_sheets = {
        n: df for n, df in sheets.items()
        if n not in ("Σχέση Μετάδοσης από κατασκευαστή", "Log")
    }
    if not data_sheets:
        raise RuntimeError("No data sheets in workbook")

    rep_name, x, y_smooth = compute_speed_profile(data_sheets, stop_threshold_kmh)

    plt.figure(figsize=(11, 5))
    plt.plot(x, y_smooth, color="tab:blue", linewidth=1.4, label="Εξομαλυνση")

    plt.title("Διάγραμμα Ταχύτητας - Αντιπροσωπευτικής Διαδρομής\n" f"({rep_name})")
    plt.xlabel("Διάρκεια (sec)")
    plt.ylabel("Ταχύτητα (km/h)")
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.4)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    show_representative_speed_profile()
