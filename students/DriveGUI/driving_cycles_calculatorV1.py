# driving_cycles_calculatorV1.py
# ------------------------------
# GUI for the Driving-Cycles toolkit – 2025-06 batch-export edition.

from __future__ import annotations

import glob
import os
import re
import sys
import tkinter as tk
from collections import OrderedDict
from datetime import datetime
from tkinter import filedialog, messagebox
from types import FunctionType
from typing import Dict

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from average_acceleration import show_average_acceleration
from average_deceleration import show_average_deceleration

# ────────────────────────────────────────────────────────────────
# 1.  Import chart / table generators
# ────────────────────────────────────────────────────────────────
from average_speed import show_average_speed
from average_speed_without_stops import show_average_speed_without_stops
from calculations import run_calculations
from log_utils import set_active_log_dir
from co2_chart import show_co2_emissions
from engine_load import show_engine_load
from fuel_consumption_chart import show_fuel_consumption
from maximum_speed import show_maximum_speed
from number_of_stops import show_number_of_stops
from representative_route import show_representative_route
from speed_profile import show_representative_speed_profile
from stop_percentage import show_stop_percentage
from total_stop_percentage import show_total_stop_percentage

# Folder selected by the user; set in process_files(), read in run_and_log()
# and plot_all_and_save().  Avoids os.chdir() side-effects.
_selected_folder: str | None = None

metrics_functions: Dict[str, FunctionType] = {
    "Average Speed": show_average_speed,
    "Average Speed Without Stops": show_average_speed_without_stops,
    "Maximum Speed": show_maximum_speed,
    "Average Acceleration": show_average_acceleration,
    "Average Deceleration": show_average_deceleration,
    "Stop Percentage": show_stop_percentage,
    "Number of Stops": show_number_of_stops,
    "Total Stop Percentage": show_total_stop_percentage,
    "Engine Load": show_engine_load,
    "Fuel Consumption": show_fuel_consumption,
    "CO₂ Chart": show_co2_emissions,
    "Αντιπροσωπευτική (table)": show_representative_route,
    "Speed Profile": show_representative_speed_profile,
}

# ────────────────────────────────────────────────────────────────
# 2.  Folder-scan helper
# ────────────────────────────────────────────────────────────────
class Day:
    def __init__(self, date: datetime.date):
        self.date = date
        self.morning: tuple[str, datetime] | None = None
        self.evening: tuple[str, datetime] | None = None

    def set_entry(self, fname: str, dt: datetime):
        target = "morning" if dt.hour < 12 else "evening"
        setattr(self, target, (fname, dt))

    def __str__(self) -> str:
        def f(entry): return f"{entry[0]} ({entry[1].strftime('%H:%M')})" if entry else "—"
        return f"{self.date} | Πρωί: {f(self.morning)} | Βράδυ: {f(self.evening)}"


# ────────────────────────────────────────────────────────────────
# 3.  Process user folder
# ────────────────────────────────────────────────────────────────
def process_files():
    global _selected_folder
    folder = filedialog.askdirectory(title="Select Folder with Excel Files")
    if not folder:
        return
    _selected_folder = folder
    terminal.insert(tk.END, f"Folder: {folder}\n")

    rows: list[tuple[str, datetime]] = []
    for fname in glob.glob(os.path.join(folder, "*.xlsx")):
        try:
            date_cell = str(pd.read_excel(fname, header=None).iloc[1, 0])
            date_clean = re.sub(r"GMT|\\s*\\+\\d\\d:\\d\\d", "", date_cell).strip()
            dt = datetime.strptime(date_clean, "%a %b %d %H:%M:%S %Y")
        except Exception:
            dt = datetime.fromtimestamp(os.path.getmtime(fname))
        rows.append((fname, dt))

    rows.sort(key=lambda x: x[1])
    grouped: OrderedDict[datetime.date, list[tuple[str, datetime]]] = OrderedDict()
    for fname, dt in rows:
        grouped.setdefault(dt.date(), []).append((fname, dt))

    for d, lst in grouped.items():
        for f, t in lst:
            terminal.insert(tk.END, f"{d} {t.strftime('%H:%M:%S')}  {f}\n")

    if rows:
        calc_btn["state"] = tk.NORMAL


# ────────────────────────────────────────────────────────────────
# 4.  Batch export
# ────────────────────────────────────────────────────────────────
def _open_folder(path: str):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform.startswith("darwin"):
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')


def plot_all_and_save():
    out_dir = os.path.join(_selected_folder or os.getcwd(), "PLOT")
    os.makedirs(out_dir, exist_ok=True)
    terminal.insert(tk.END, f"[PLOT ALL] Export → {out_dir}\n")

    # Progress window
    prog = tk.Toplevel(root)
    prog.title("Exporting…")
    tk.Label(prog, text="Exporting charts, please wait…").pack(padx=25, pady=20)
    prog.update()

    # Switch to non-GUI backend and disable plt.show
    orig_backend = matplotlib.get_backend()
    matplotlib.use("Agg", force=True)
    orig_show = plt.show
    plt.show = lambda *a, **k: None

    for label, func in metrics_functions.items():
        figs_before = set(plt.get_fignums())
        try:
            func()
            new_nums = [n for n in plt.get_fignums() if n not in figs_before]
            if not new_nums:
                terminal.insert(tk.END, f"[PLOT ALL] {label}: (no figure)\n")
            for idx, num in enumerate(new_nums, 1):
                fig = plt.figure(num)
                safe = (
                    label.lower()
                    .replace(" ", "_")
                    .replace("(", "")
                    .replace(")", "")
                    .replace(" ", "_")  # NBSP
                )
                if len(new_nums) > 1:
                    safe = f"{safe}_{idx}"
                fig.savefig(os.path.join(out_dir, f"{safe}.png"), dpi=150)
            plt.close("all")
            terminal.insert(tk.END, f"[PLOT ALL] {label}: OK ({len(new_nums)} fig)\n")
        except Exception as err:
            terminal.insert(tk.END, f"[PLOT ALL] {label}: ERROR – {err}\n")

    # Restore backend & show
    plt.show = orig_show
    matplotlib.use(orig_backend, force=True)

    prog.destroy()
    terminal.insert(tk.END, "[PLOT ALL] Finished.\n")

    if messagebox.askyesno("PLOT ALL", "Export complete.\nOpen PLOT folder?"):
        _open_folder(out_dir)


# ────────────────────────────────────────────────────────────────
# 5.  Charts window
# ────────────────────────────────────────────────────────────────
def open_charts_window():
    win = tk.Toplevel(root)
    win.title("ΔΙΑΓΡΑΜΜΑΤΑ")

    for lbl, fn in metrics_functions.items():
        tk.Button(win, text=lbl, width=42, command=fn).pack(pady=2)

    tk.Button(
        win,
        text="PLOT ALL (save PNGs)",
        width=42,
        bg="#dcdcdc",
        command=plot_all_and_save,
    ).pack(pady=(10, 2))


# ────────────────────────────────────────────────────────────────
# 6.  Main GUI
# ────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("Driving-Cycles GUI")
root.geometry("900x550")

terminal = tk.Text(root, wrap="word", height=20, width=80)
terminal.pack(side=tk.LEFT, padx=10, pady=10)

side = tk.Frame(root)
side.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

tk.Button(
    side,
    text="Select Folder and Process Files",
    width=40,
    command=process_files,
).pack(pady=(0, 10))


def run_and_log():
    folder = _selected_folder or os.getcwd()
    log_dir = os.path.join(folder, "log")
    set_active_log_dir(log_dir)
    txt, xlsx = run_calculations(folder, log_folder=log_dir)
    terminal.insert(tk.END, f"Text log : {txt}\nExcel log: {xlsx}\n")
    charts_btn["state"] = tk.NORMAL


calc_btn = tk.Button(
    side,
    text="ΕΞΟΜΑΛΥΝΣΗ ΚΑΙ ΥΠΟΛΟΓΙΣΜΟΙ",
    width=40,
    state=tk.DISABLED,
    command=run_and_log,
)
calc_btn.pack(pady=(0, 10))

charts_btn = tk.Button(
    side,
    text="ΔΙΑΓΡΑΜΜΑΤΑ",
    width=40,
    state=tk.DISABLED,
    command=open_charts_window,
)
charts_btn.pack(pady=(0, 10))

root.mainloop()
