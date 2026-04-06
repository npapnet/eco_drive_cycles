"""
GUI example: folder picker → ingest to Parquet + DuckDB → display speed profile.

Different from DriveGUI: data is stored on first ingest; subsequent opens load
from DuckDB instantly without reprocessing raw files.

To migrate to PyQt6/PySide6: replace tk.* with QWidget equivalents.
TripCollection API calls are identical.
"""
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from drive_cycle_calculator.metrics.trip import TripCollection

DATA_DIR = Path("./data")
TRIPS_DIR = DATA_DIR / "trips"
DB_PATH = DATA_DIR / "metadata.duckdb"

# All business logic lives in TripCollection — GUI only calls the API.


def ingest(raw_dir: str) -> None:
    """Read raw .xlsx files, write Parquet + DuckDB catalog."""
    try:
        tc = TripCollection.from_folder(raw_dir)
        if len(tc) == 0:
            messagebox.showwarning("No trips", "No valid .xlsx files found in the selected folder.")
            return
        TRIPS_DIR.mkdir(parents=True, exist_ok=True)
        tc.to_parquet(TRIPS_DIR)
        tc.to_duckdb_catalog(DB_PATH)
        status_var.set(f"Ingested {len(tc)} trips.")
        load_from_db()
    except Exception as exc:
        messagebox.showerror("Ingest error", str(exc))


def load_from_db() -> None:
    """Load stored trips from DuckDB catalog (no raw file reprocessing)."""
    if not DB_PATH.exists():
        status_var.set("No catalog yet — use 'Select folder' to ingest.")
        return
    try:
        tc = TripCollection.from_duckdb_catalog(DB_PATH)
        if len(tc) == 0:
            status_var.set("Catalog is empty.")
            return
        rep = tc.find_representative()
        x, y = rep.speed_profile
        ax.clear()
        ax.plot(x, y, label=rep.name)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Speed (km/h)")
        ax.set_title("Representative trip speed profile")
        ax.legend()
        canvas.draw()
        status_var.set(f"Loaded {len(tc)} trips. Representative: {rep.name}")
    except Exception as exc:
        messagebox.showerror("Load error", str(exc))


root = tk.Tk()
root.title("Drive Cycle Analyzer")

status_var = tk.StringVar(value="Ready.")
tk.Label(root, textvariable=status_var).pack(pady=4)


def _pick_folder():
    d = filedialog.askdirectory(title="Select raw OBD xlsx folder")
    if d:
        ingest(d)


tk.Button(root, text="Select raw folder & ingest", command=_pick_folder).pack(pady=4)
tk.Button(root, text="Load from catalog", command=load_from_db).pack(pady=4)

fig, ax = plt.subplots(figsize=(7, 4))
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

load_from_db()   # pre-load if catalog already exists
root.mainloop()
