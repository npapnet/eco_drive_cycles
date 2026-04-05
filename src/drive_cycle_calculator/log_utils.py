# log_utils.py
# ------------
# Transitional bridge module.  Re-exports from students/DriveGUI/log_utils.py.

from __future__ import annotations

import os
import sys

_DRIVEGUI = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "students", "DriveGUI")
)
if _DRIVEGUI not in sys.path:
    sys.path.insert(0, _DRIVEGUI)

from log_utils import find_latest_log  # noqa: E402

__all__ = ["find_latest_log"]
