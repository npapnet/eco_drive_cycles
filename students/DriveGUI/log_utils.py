# log_utils.py (DriveGUI)
# -----------------------
# Re-exports find_latest_log from the drive_cycle_calculator package and adds
# GUI-level log-directory state so visualization modules do not need to
# hardcode the INPUT/log path.
#
# The GUI calls set_active_log_dir() after running calculations.
# Visualization modules call get_log_dir() instead of constructing a path.

from __future__ import annotations

import os

from drive_cycle_calculator.log_utils import find_latest_log

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
    user (set via set_active_log_dir).  When a visualization module is run
    standalone (e.g. ``python average_speed.py``) this falls back to the
    legacy INPUT/log path relative to the DriveGUI directory.
    """
    if _active_log_dir is not None:
        return _active_log_dir
    # Fallback for standalone execution
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "INPUT", "log")


__all__ = ["find_latest_log", "get_log_dir", "set_active_log_dir"]
