# log_utils.py (DriveGUI)
# -----------------------
# File-system helper and GUI log-directory state.
#
# This file is self-contained — it does NOT import from the drive_cycle_calculator
# package. DriveGUI is a frozen historical reference; package API changes must not
# break it.
#
# The GUI calls set_active_log_dir() after running calculations.
# Visualization modules call get_log_dir() instead of constructing a path.

from __future__ import annotations

import glob
import os


def find_latest_log(log_dir: str) -> str:
    """Return the most recently modified calculations_log_*.xlsx in log_dir.

    Raises
    ------
    FileNotFoundError
        If no matching file exists in log_dir.
    """
    pattern = os.path.join(log_dir, "calculations_log_*.xlsx")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No log files found in {log_dir}")
    return max(files, key=os.path.getmtime)


# Set by the GUI (driving_cycles_calculatorV1.py) after run_calculations().
# None until the GUI sets it, which means get_log_dir() returns the
# legacy default so standalone execution of individual modules still works.
_active_log_dir: str | None = None


def set_active_log_dir(path: str) -> None:
    """Record the log directory used by the most recent run_calculations() call."""
    global _active_log_dir
    _active_log_dir = path


def get_log_dir() -> str:
    """Return the active log directory.

    When called from the GUI context this returns the folder chosen by the
    user (set via set_active_log_dir). When a visualization module is run
    standalone (e.g. ``python average_speed.py``) this falls back to the
    legacy INPUT/log path relative to the DriveGUI directory.
    """
    if _active_log_dir is not None:
        return _active_log_dir
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "INPUT", "log")


__all__ = ["find_latest_log", "get_log_dir", "set_active_log_dir"]
