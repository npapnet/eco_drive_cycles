"""
> [!WARNING]
> OBSOLETE
> This script is obsolete. The logic has been integrated natively into `dcc gui`.
> Use `uv run dcc gui` instead. 
> This file remains for reference.

GUI example: folder picker → ingest to DuckDB catalog → display speed profile.

Three modes:
  1. "Import raw xlsx"        — reads raw OBD xlsx files, writes v2 archive Parquets,
                                then registers them in the DuckDB catalog.
  2. "Load existing archive"  — picks a folder of v2 archive Parquets and registers
                                them directly (no xlsx re-parsing).
  3. "Reload from catalog"    — reloads previously registered trips instantly.

Progress is streamed to a scrollable log pane and to stdout.
"""
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from drive_cycle_calculator.metrics import TripCollection

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
DATA_DIR = _HERE / "../../data"
ARCHIVE_DIR = DATA_DIR / "trips"
DB_PATH = DATA_DIR / "metadata.duckdb"


# ── Logging setup ─────────────────────────────────────────────────────────────

class _TkLogHandler(logging.Handler):
    """Append log records to a tkinter ScrolledText widget."""

    def __init__(self, widget: scrolledtext.ScrolledText) -> None:
        super().__init__()
        self._widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record) + "\n"
        self._widget.configure(state="normal")
        self._widget.insert(tk.END, msg)
        self._widget.see(tk.END)           # auto-scroll to bottom
        self._widget.configure(state="disabled")
        self._widget.update_idletasks()    # flush immediately (don't wait for mainloop)


def _setup_logging(log_widget: scrolledtext.ScrolledText) -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
    logger = logging.getLogger("drive_cycle_gui")
    logger.setLevel(logging.DEBUG)

    # GUI pane handler
    gui_handler = _TkLogHandler(log_widget)
    gui_handler.setFormatter(fmt)
    logger.addHandler(gui_handler)

    # stdout handler (visible in the terminal that launched the GUI)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


# ── Business logic ────────────────────────────────────────────────────────────

def ingest_from_xlsx(raw_dir: str) -> None:
    """Read raw .xlsx files → write v2 archive Parquets → register in catalog."""
    log.info("── Ingest from raw xlsx ──────────────────────────")
    status_var.set("Scanning for xlsx files…")
    try:
        raw_files = TripCollection.from_folder_raw(raw_dir)
        if not raw_files:
            log.warning("No valid .xlsx files found in: %s", raw_dir)
            messagebox.showwarning(
                "No trips",
                "No valid .xlsx files found in the selected folder.",
            )
            status_var.set("No xlsx files found.")
            return

        log.info("Found %d xlsx file(s) in %s", len(raw_files), raw_dir)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        for i, obd in enumerate(raw_files, 1):
            dest = ARCHIVE_DIR / f"{obd.name}.parquet"
            log.info("  [%d/%d] Writing archive: %s", i, len(raw_files), dest.name)
            status_var.set(f"Archiving {i}/{len(raw_files)}: {obd.name}…")
            obd.to_parquet(dest)

        log.info("All archives written to: %s", ARCHIVE_DIR)
        _register_and_display(ARCHIVE_DIR)

    except Exception as exc:
        log.exception("Ingest from xlsx failed: %s", exc)
        messagebox.showerror("Ingest error", str(exc))
        status_var.set("Ingest failed — see log.")


def ingest_from_archive(archive_dir: str) -> None:
    """Register an existing folder of v2 archive Parquets in the DuckDB catalog."""
    log.info("── Load existing archive ─────────────────────────")
    try:
        _register_and_display(Path(archive_dir))
    except Exception as exc:
        log.exception("Load archive failed: %s", exc)
        messagebox.showerror("Load archive error", str(exc))
        status_var.set("Load archive failed — see log.")


def _register_and_display(archive_dir: Path) -> None:
    """Build TripCollection from archive Parquets, upsert catalog, refresh plot."""
    log.info("Reading archive Parquets from: %s", archive_dir)
    status_var.set(f"Reading parquets from {archive_dir.name}…")

    tc = TripCollection.from_archive_parquets(archive_dir)
    if len(tc) == 0:
        log.warning("No valid v2 archive Parquets found in: %s", archive_dir)
        messagebox.showwarning("No trips", "No valid v2 archive Parquets found.")
        status_var.set("No trips found.")
        return

    log.info("Loaded %d trip(s) from archive.", len(tc))
    for t in tc:
        log.debug("  trip: %s", t.name)

    log.info("Registering in DuckDB catalog: %s", DB_PATH)
    status_var.set("Writing DuckDB catalog…")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tc.to_duckdb_catalog(DB_PATH)
    log.info("Catalog updated.")

    status_var.set(f"Registered {len(tc)} trip(s). Loading display…")
    load_from_db()


def load_from_db() -> None:
    """Load stored trips from DuckDB catalog (no raw file reprocessing)."""
    log.info("── Reload from catalog ───────────────────────────")
    if not DB_PATH.exists():
        log.warning("Catalog not found: %s", DB_PATH)
        status_var.set("No catalog yet — import raw xlsx or load archive first.")
        return
    try:
        log.info("Reading catalog: %s", DB_PATH)
        status_var.set("Loading catalog…")
        tc = TripCollection.from_duckdb_catalog(DB_PATH)

        if len(tc) == 0:
            log.warning("Catalog is empty.")
            status_var.set("Catalog is empty.")
            return

        log.info("Loaded %d trip(s) from catalog.", len(tc))
        log.info("Computing similarity scores…")
        status_var.set("Computing representative trip…")
        rep = tc.find_representative()
        log.info("Representative trip: %s", rep.name)

        x, y = rep.speed_profile
        ax.clear()
        ax.plot(x, y, label=rep.name)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Speed (km/h)")
        ax.set_title("Representative trip speed profile")
        ax.legend()
        canvas.draw()
        status_var.set(f"Loaded {len(tc)} trips.  Representative: {rep.name}")
        log.info("Plot updated.")

    except Exception as exc:
        log.exception("Load from catalog failed: %s", exc)
        messagebox.showerror("Load error", str(exc))
        status_var.set("Load failed — see log.")


# ── UI ────────────────────────────────────────────────────────────────────────

def _pick_xlsx_folder():
    d = filedialog.askdirectory(title="Select folder with raw OBD .xlsx files")
    if d:
        ingest_from_xlsx(d)


def _pick_archive_folder():
    d = filedialog.askdirectory(title="Select folder with v2 archive .parquet files")
    if d:
        ingest_from_archive(d)


root = tk.Tk()
root.title("Drive Cycle Analyzer")
root.minsize(700, 600)

# Status bar
status_var = tk.StringVar(value="Ready.")
tk.Label(root, textvariable=status_var, anchor="w", relief="sunken").pack(
    fill=tk.X, padx=4, pady=(4, 0)
)

# Buttons row
btn_frame = tk.Frame(root)
btn_frame.pack(fill=tk.X, padx=8, pady=4)
tk.Button(btn_frame, text="Import raw xlsx → write archive", command=_pick_xlsx_folder).pack(
    side=tk.LEFT, padx=4
)
tk.Button(btn_frame, text="Load existing archive parquets", command=_pick_archive_folder).pack(
    side=tk.LEFT, padx=4
)
tk.Button(btn_frame, text="Reload from catalog", command=load_from_db).pack(
    side=tk.LEFT, padx=4
)

# Plot
fig, ax = plt.subplots(figsize=(7, 3))
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4)

# Log pane
tk.Label(root, text="Log output", anchor="w").pack(fill=tk.X, padx=4)
log_text = scrolledtext.ScrolledText(root, height=10, state="disabled", font=("Courier", 9))
log_text.pack(fill=tk.BOTH, expand=False, padx=4, pady=(0, 4))

# Wire up logging AFTER the widget exists
log = _setup_logging(log_text)
log.info("Drive Cycle Analyzer started.")
log.info("Archive dir : %s", ARCHIVE_DIR.resolve())
log.info("Catalog     : %s", DB_PATH.resolve())

root.mainloop()
