# representative_route.py
# -----------------------
# ➊ Open (by default) the newest *calculations_log_*.xlsx*
# ➋ Find the most representative sheet via metrics.find_representative_sheet
# ➌ Show a Matplotlib table comparing Overall vs Representative sheet

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from log_utils import find_latest_log, get_log_dir
from metrics import compute_session_metrics, similarity, find_representative_sheet


# ────────────────────────────────────────────────────────────────
# Main public function – API unchanged
# ────────────────────────────────────────────────────────────────
def show_representative_route(
    log_excel_path: str | None = None,
    stop_threshold_kmh: float = 2.0
) -> None:
    """
    Find the sheet whose metrics best resemble the **overall** averages.

    Metrics calculated (same as original):
      • Duration (sec)          – max of 'Διάρκεια (sec)'
      • Mean speed (km/h)       – mean of 'Ταχ m/s' * 3.6
      • Mean speed no stops     – same, but rows > *stop_threshold_kmh*
      • Number of stops         – rows ≤ *stop_threshold_kmh*
      • Stop %                  – (stops / total rows) * 100
      • Mean acceleration       – mean of 'Επιταχυνση'
      • Mean deceleration       – mean of 'Επιβραδυνση'
    A Matplotlib table then shows Overall vs Representative values plus a
    % similarity column.
    """
    if log_excel_path is None:
        log_excel_path = find_latest_log(get_log_dir())

    # Read every worksheet, skipping metadata sheets
    raw_sheets = pd.read_excel(log_excel_path, sheet_name=None)
    data_sheets = {
        name: df
        for name, df in raw_sheets.items()
        if name not in ("Σχέση Μετάδοσης από κατασκευαστή", "Log")
    }
    if not data_sheets:
        raise RuntimeError("No data sheets found in log.")

    best_sheet, _ = find_representative_sheet(data_sheets, stop_threshold_kmh)

    # Recompute per-sheet metrics for the table display
    per_sheet = {
        name: compute_session_metrics(df, stop_threshold_kmh)
        for name, df in data_sheets.items()
    }
    overall = {
        key: float(np.nanmean([m[key] for m in per_sheet.values()]))
        for key in per_sheet[next(iter(per_sheet))].keys()
    }
    representative = per_sheet[best_sheet]

    # Build table rows (label • overall • representative • similarity)
    rows = [
        ("Διάρκεια (sec)",                                        overall["duration"],    representative["duration"]),
        ("Μέση ωριαία ταχύτητα (km/h)",                          overall["mean_speed"],  representative["mean_speed"]),
        ("Μέση ωριαία ταχύτητα χωρίς στάσεις (km/h)",           overall["mean_ns"],     representative["mean_ns"]),
        ("Αριθμός Στάσεων",                                       overall["stops"],       representative["stops"]),
        ("% στάσης",                                              overall["stop_pct"],    representative["stop_pct"]),
        ("Μέση επιτάχυνση (m/s²)",                               overall["mean_acc"],    representative["mean_acc"]),
        ("Μέση επιβράδυνση (m/s²)",                              overall["mean_dec"],    representative["mean_dec"]),
    ]

    table_data = [
        [
            label,
            f"{ov:.2f}" if not np.isnan(ov) else "-",
            f"{rv:.2f}",
            f"{similarity(ov, rv):.0f} %"
        ]
        for label, ov, rv in rows
    ]

    # Display the comparison as a Matplotlib table
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis("off")

    ax.table(
        cellText=table_data,
        colLabels=[
            "Χαρακτηριστικά",
            "Μέσες τιμές Μετρήσεων",
            f"Αντιπροσωπευτική ({best_sheet})",
            "Ποσοστό ομοιότητας",
        ],
        loc="center",
    ).auto_set_font_size(False)

    plt.title(f"Αντιπροσωπευτική Διαδρομή: {best_sheet}", pad=20)
    plt.tight_layout()
    plt.show()


# Allow quick test with:  python representative_route.py
if __name__ == "__main__":
    show_representative_route()
