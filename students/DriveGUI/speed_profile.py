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

import glob
import os
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────
# Helper – newest calculations_log_*.xlsx in <script>/INPUT/log
# ──────────────────────────────────────────────────────────────────

def _find_latest_log(log_dir: str) -> str:
    files = glob.glob(os.path.join(log_dir, "calculations_log_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No log files in {log_dir!r}")
    return max(files, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────
# Representative-sheet picker (condensed version)
# ──────────────────────────────────────────────────────────────────

def _choose_representative_sheet(sheets: Dict[str, pd.DataFrame], stop_thr: float) -> str:
    def metrics(df: pd.DataFrame) -> Dict[str, float]:
        speed_kmh = df["Ταχ m/s"].dropna() * 3.6
        return dict(mean=speed_kmh.mean(), stop_pct=speed_kmh.le(stop_thr).mean())

    per = {n: metrics(df) for n, df in sheets.items()}
    overall = {k: float(np.nanmean([m[k] for m in per.values()])) for k in per[next(iter(per))]}

    def sim(a, b):
        if np.isnan(a) or np.isnan(b):
            return 0.0
        if a == 0:
            return 100.0 if b == 0 else 0.0
        return 100.0 - abs(a - b) / abs(a) * 100

    best, score = None, -1.0
    for n, m in per.items():
        s = np.nanmean([sim(overall[k], v) for k, v in m.items()])
        if s > score:
            best, score = n, s
    if best is None:
        raise RuntimeError("Unable to choose representative sheet")
    return best


# ──────────────────────────────────────────────────────────────────
# Column helper – first name that exists
# ──────────────────────────────────────────────────────────────────

def _first_existing(df: pd.DataFrame, names: List[str]) -> str:
    for n in names:
        if n in df.columns:
            return n
    raise KeyError(f"None of {names!r} found in sheet")


# ──────────────────────────────────────────────────────────────────
# Public helper
# ──────────────────────────────────────────────────────────────────

def show_representative_speed_profile(log_excel_path: str | None = None, stop_threshold_kmh: float = 2.0) -> None:
    # Workbook ------------------------------------------------------------
    if log_excel_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        log_excel_path = _find_latest_log(os.path.join(here, "INPUT", "log"))

    sheets = pd.read_excel(log_excel_path, sheet_name=None)
    data_sheets = {n: df for n, df in sheets.items() if n not in ("Σχέση Μετάδοσης από κατασκευαστή", "Log")}
    if not data_sheets:
        raise RuntimeError("No data sheets in workbook")

    rep_name = _choose_representative_sheet(data_sheets, stop_threshold_kmh)
    df = data_sheets[rep_name]

    # Columns -------------------------------------------------------------
    dur_col = "Διάρκεια (sec)"
    smooth_col = _first_existing(df, ["Εξομαλυνση", "Εξομάλυνση"])

    x = pd.to_numeric(df[dur_col], errors="coerce").dropna()
    y_smooth = pd.to_numeric(df[smooth_col], errors="coerce").dropna()

    n = min(len(x), len(y_smooth))
    if n == 0:
        raise RuntimeError("Not enough data to plot")

    x, y_smooth = x.iloc[:n], y_smooth.iloc[:n]

    # Plot ----------------------------------------------------------------
    plt.figure(figsize=(11, 5))
    plt.plot(x, y_smooth, color="tab:blue", linewidth=1.4, label=smooth_col)

    plt.title("Διάγραμμα Ταχύτητας - Αντιπροσωπευτικής Διαδρομής\n" f"({rep_name})")
    plt.xlabel("Διάρκεια (sec)")
    plt.ylabel("Ταχύτητα (km/h)")
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.4)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    show_representative_speed_profile()
