"""
Thin stub — real implementation lives in the drive_cycle_calculator package.

All visualization modules in this folder import from here using the flat name
``from calculations import ...``.  The actual logic is in:
    src/drive_cycle_calculator/calculations.py
"""

from drive_cycle_calculator.calculations import (
    gps_to_duration_seconds,
    run_calculations,
    smooth_and_derive,
)

__all__ = ["gps_to_duration_seconds", "smooth_and_derive", "run_calculations"]
