# log_utils.py
# ------------
# Shared file-system helper used by all visualization modules.
# Replaces the copy-pasted _find_latest_log() that was in each module.

import glob
import os


def find_latest_log(log_dir: str) -> str:
    """Return the most recently modified calculations_log_*.xlsx in log_dir.

    Parameters
    ----------
    log_dir : str
        Folder that contains the log workbooks (absolute path required —
        the GUI calls os.chdir() so relative paths are unsafe).

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
