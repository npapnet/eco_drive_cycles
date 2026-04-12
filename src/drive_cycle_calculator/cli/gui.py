import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

import matplotlib
import typer

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.trip_collection import TripCollection

app = typer.Typer(help="Launch the Drive Cycle Analyzer GUI.")

@app.callback(invoke_without_command=True)
def run_gui(
    data_dir: Path = typer.Option(
        "./data",
        help="Default data directory for the GUI.",
        file_okay=False,
    )
):
    archive_dir = data_dir / "trips"
    db_path = data_dir / "metadata.duckdb"

    class _TkLogHandler(logging.Handler):
        def __init__(self, widget: scrolledtext.ScrolledText) -> None:
            super().__init__()
            self._widget = widget

        def emit(self, record: logging.LogRecord) -> None:
            msg = self.format(record) + "\n"
            self._widget.configure(state="normal")
            self._widget.insert(tk.END, msg)
            self._widget.see(tk.END)
            self._widget.configure(state="disabled")
            self._widget.update_idletasks()

    def _setup_logging(log_widget: scrolledtext.ScrolledText) -> logging.Logger:
        fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
        logger = logging.getLogger("drive_cycle_gui_cli")
        logger.setLevel(logging.DEBUG)

        gui_handler = _TkLogHandler(log_widget)
        gui_handler.setFormatter(fmt)
        logger.addHandler(gui_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

        return logger

    def ingest_from_files(raw_dir: str) -> None:
        log.info("── Ingest from raw files ─────────────────────────")
        status_var.set("Scanning for raw files…")
        try:
            raw_path = Path(raw_dir)
            files = (
                list(raw_path.glob("*.xlsx"))
                + list(raw_path.glob("*.xls"))
                + list(raw_path.glob("*.csv"))
            )
            
            if not files:
                log.warning("No valid raw files found in: %s", raw_dir)
                messagebox.showwarning(
                    "No trips",
                    "No valid Excel or CSV files found in the selected folder.",
                )
                status_var.set("No files found.")
                return

            log.info("Found %d file(s) in %s", len(files), raw_dir)
            archive_dir.mkdir(parents=True, exist_ok=True)

            for i, f in enumerate(sorted(files), 1):
                status_var.set(f"Archiving {i}/{len(files)}: {f.name}…")
                try:
                    obd = OBDFile.from_file(f)
                    dest = archive_dir / f"{obd.name}.parquet"
                    log.info("  [%d/%d] Writing archive: %s", i, len(files), dest.name)
                    obd.to_parquet(dest)
                except Exception as e:
                    log.error("  [%d/%d] Failed %s: %s", i, len(files), f.name, e)

            log.info("All archives written to: %s", archive_dir)
            _register_and_display(archive_dir)

        except Exception as exc:
            log.exception("Ingest failed: %s", exc)
            messagebox.showerror("Ingest error", str(exc))
            status_var.set("Ingest failed — see log.")

    def ingest_from_archive(arch_dir: str) -> None:
        log.info("── Load existing archive ─────────────────────────")
        try:
            _register_and_display(Path(arch_dir))
        except Exception as exc:
            log.exception("Load archive failed: %s", exc)
            messagebox.showerror("Load archive error", str(exc))
            status_var.set("Load archive failed — see log.")

    def _register_and_display(arch_dir: Path) -> None:
        log.info("Reading archive Parquets from: %s", arch_dir)
        status_var.set(f"Reading parquets from {arch_dir.name}…")

        tc = TripCollection.from_archive_parquets(arch_dir)
        if len(tc) == 0:
            log.warning("No valid v2 archive Parquets found in: %s", arch_dir)
            messagebox.showwarning("No trips", "No valid v2 archive Parquets found.")
            status_var.set("No trips found.")
            return

        log.info("Loaded %d trip(s) from archive.", len(tc))
        log.info("Registering in DuckDB catalog: %s", db_path)
        status_var.set("Writing DuckDB catalog…")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tc.to_duckdb_catalog(db_path)
        log.info("Catalog updated.")

        status_var.set(f"Registered {len(tc)} trip(s). Loading display…")
        load_from_db()

    def load_from_db() -> None:
        log.info("── Reload from catalog ───────────────────────────")
        if not db_path.exists():
            log.warning("Catalog not found: %s", db_path)
            status_var.set("No catalog yet — import raw files or load archive first.")
            return
        try:
            log.info("Reading catalog: %s", db_path)
            status_var.set("Loading catalog…")
            tc = TripCollection.from_duckdb_catalog(db_path)

            if len(tc) == 0:
                log.warning("Catalog is empty.")
                status_var.set("Catalog is empty.")
                return

            log.info("Loaded %d trip(s) from catalog.", len(tc))
            log.info("Computing representative trip…")
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

    def _pick_raw_folder():
        d = filedialog.askdirectory(title="Select folder with raw OBD files (.xlsx, .csv)")
        if d:
            ingest_from_files(d)

    def _pick_archive_folder():
        d = filedialog.askdirectory(title="Select folder with v2 archive .parquet files")
        if d:
            ingest_from_archive(d)

    root = tk.Tk()
    root.title("Drive Cycle Analyzer (DCC)")
    root.minsize(700, 600)

    status_var = tk.StringVar(value="Ready.")
    tk.Label(root, textvariable=status_var, anchor="w", relief="sunken").pack(
        fill=tk.X, padx=4, pady=(4, 0)
    )

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=8, pady=4)
    tk.Button(btn_frame, text="Import raw files → write archive", command=_pick_raw_folder).pack(
        side=tk.LEFT, padx=4
    )
    tk.Button(btn_frame, text="Load existing archive parquets", command=_pick_archive_folder).pack(
        side=tk.LEFT, padx=4
    )
    tk.Button(btn_frame, text="Reload from catalog", command=load_from_db).pack(
        side=tk.LEFT, padx=4
    )

    fig, ax = plt.subplots(figsize=(7, 3))
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4)

    tk.Label(root, text="Log output", anchor="w").pack(fill=tk.X, padx=4)
    log_text = scrolledtext.ScrolledText(root, height=10, state="disabled", font=("Courier", 9))
    log_text.pack(fill=tk.BOTH, expand=False, padx=4, pady=(0, 4))

    log = _setup_logging(log_text)
    log.info("Drive Cycle Analyzer started.")
    log.info("Archive dir : %s", archive_dir.resolve())
    log.info("Catalog     : %s", db_path.resolve())

    root.mainloop()
