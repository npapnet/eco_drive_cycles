# log_utils.py
# ------------
# File-system helper: locate the most recent calculations log workbook.

from __future__ import annotations

import glob
import os


def find_latest_log(log_dir: str) -> str:
    """Return the most recently modified calculations_log_*.xlsx in log_dir.

    Parameters
    ----------
    log_dir : str
        Folder that contains the log workbooks.

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


__all__ = ["find_latest_log"]
