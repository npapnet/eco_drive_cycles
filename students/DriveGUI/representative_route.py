# representative_route.py
# -----------------------
# ➊ Open (by default) the newest *calculations_log_*.xlsx*
# ➋ Compute “overall” metrics across **all** sheets
# ➌ Compute the same metrics per sheet
# ➍ Pick the sheet whose metrics are *closest* (simple % similarity)
# ➎ Show a Matplotlib table comparing Overall vs Representative sheet

import os
import glob
from datetime import datetime

import pandas as pd            # Excel → DataFrame
import numpy as np             # Simple numeric helper
import matplotlib.pyplot as plt


# ────────────────────────────────────────────────────────────────
# 1. Helper – find newest calculations_log_*.xlsx in a folder
# ────────────────────────────────────────────────────────────────
def _find_latest_log(log_dir: str) -> str:
    """
    Return **the most-recently modified** Excel workbook whose name matches
        calculations_log_YYYYMMDD_HHMMSS.xlsx
    inside *log_dir*.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No log files found in {log_dir!r}")
    return max(files, key=os.path.getmtime)


# ────────────────────────────────────────────────────────────────
# 2. Main public function – API unchanged
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
    # 2️⃣.1 Decide which workbook to open
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(here, "INPUT", "log")
        log_excel_path = _find_latest_log(log_dir)

    # 2️⃣.2 Read every worksheet, skipping metadata sheets
    raw_sheets = pd.read_excel(log_excel_path, sheet_name=None)
    data_sheets = {
        name: df
        for name, df in raw_sheets.items()
        if name not in ("Σχέση Μετάδοσης από κατασκευαστή", "Log")
    }
    if not data_sheets:
        raise RuntimeError("No data sheets found in log.")

    # ────────────────────────────────────────────────────────────
    # 3. Helper – compute the 7 metrics for one DataFrame
    # ────────────────────────────────────────────────────────────
    def metrics_for(df: pd.DataFrame) -> dict[str, float]:
        # duration (sec) – we take the **max** of column
        duration = (
            float(df["Διάρκεια (sec)"].dropna().max())
            if "Διάρκεια (sec)" in df.columns
            else np.nan
        )

        # speeds → km/h
        speed_ms = df["Ταχ m/s"].dropna()
        speed_kmh = speed_ms * 3.6
        mean_speed = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0

        moving = speed_kmh[speed_kmh > stop_threshold_kmh]
        mean_ns = float(moving.mean()) if not moving.empty else 0.0

        total_rows = len(speed_kmh)
        stops = int((speed_kmh <= stop_threshold_kmh).sum())
        stop_pct = (stops / total_rows * 100) if total_rows else 0.0

        # acceleration & deceleration (can be missing)
        mean_acc = float(df["Επιταχυνση"].mean()) if "Επιταχυνση" in df.columns else np.nan
        mean_dec = float(df["Επιβραδυνση"].mean()) if "Επιβραδυνση" in df.columns else np.nan

        return dict(
            duration=duration,
            mean_speed=mean_speed,
            mean_ns=mean_ns,
            stops=stops,
            stop_pct=stop_pct,
            mean_acc=mean_acc,
            mean_dec=mean_dec,
        )

    # 3️⃣.1 Compute metrics for each sheet and for the overall set
    per_sheet = {name: metrics_for(df) for name, df in data_sheets.items()}

    # Overall metrics → mean of each numeric field across **all** sheets
    overall = {
        key: float(np.nanmean([m[key] for m in per_sheet.values()]))
        for key in per_sheet[next(iter(per_sheet))].keys()
    }

    # 3️⃣.2 Simple similarity: 100 – |rep – overall| / overall * 100 (%)
    def similarity(overall_val: float, rep_val: float) -> float:
        if np.isnan(overall_val):
            return 0.0
        if overall_val == 0:                       # avoid division by zero
            return 100.0 if rep_val == 0 else 0.0
        return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)

    # 3️⃣.3 Pick the sheet with **highest mean similarity** across metrics
    best_sheet, best_score = None, -1.0
    for name, metrics in per_sheet.items():
        sims = [similarity(overall[k], v) for k, v in metrics.items()]
        avg_sim = float(np.nanmean(sims))
        if avg_sim > best_score:
            best_sheet, best_score = name, avg_sim

    representative = per_sheet[best_sheet]

    # ────────────────────────────────────────────────────────────
    # 4. Build table rows (label • overall • representative • similarity)
    # ────────────────────────────────────────────────────────────
    rows = [
        ("Διάρκεια (sec)",                       overall["duration"],  representative["duration"]),
        ("Μέση ωριαία ταχύτητα (km/h)",          overall["mean_speed"], representative["mean_speed"]),
        ("Μέση ωριαία ταχύτητα χωρίς στάσεις (km/h)",
                                                overall["mean_ns"],    representative["mean_ns"]),
        ("Αριθμός Στάσεων",                      overall["stops"],      representative["stops"]),
        ("% στάσης",                             overall["stop_pct"],   representative["stop_pct"]),
        ("Μέση επιτάχυνση (m/s²)",               overall["mean_acc"],   representative["mean_acc"]),
        ("Μέση επιβράδυνση (m/s²)",              overall["mean_dec"],   representative["mean_dec"]),
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

    # ────────────────────────────────────────────────────────────
    # 5. Display the comparison as a Matplotlib table
    # ────────────────────────────────────────────────────────────
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
