# calculations.py
# ---------------
# Transitional bridge module.  Re-exports functions from students/DriveGUI/calculations.py
# so that `from drive_cycle_calculator.calculations import run_calculations` works
# after tests/conftest.py is deleted.
#
# When the calc/presentation separation is complete and DriveGUI imports from this
# package, this file will be replaced by a proper implementation.

from __future__ import annotations

import os
import sys

_DRIVEGUI = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "students", "DriveGUI")
)
if _DRIVEGUI not in sys.path:
    sys.path.insert(0, _DRIVEGUI)

from calculations import gps_to_duration_seconds, run_calculations, smooth_and_derive  # noqa: E402

__all__ = ["gps_to_duration_seconds", "smooth_and_derive", "run_calculations"]
