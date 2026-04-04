# tests/conftest.py
# -----------------
# sys.path shim so tests import from drive_cycle_calculator.* namespace today
# (flat layout) and survive unchanged when the repo moves to src/drive_cycle_calculator/.
#
# DELETE THIS FILE when src/drive_cycle_calculator/metrics/__init__.py
# imports real code (not just `pass`/empty).  At that point, install the
# package with `uv sync` and the tests will import against the real package.
# Keeping this file after that migration will silently test the old flat
# layout instead of the installed package.

import os
import sys
import types

# conftest.py lives inside tests/ — go up one level to reach repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DRIVEGUI = os.path.join(_ROOT, "students", "DriveGUI")
sys.path.insert(0, _DRIVEGUI)

import calculations as _calc
import metrics as _m
import log_utils as _lu

_pkg = types.ModuleType("drive_cycle_calculator")
_pkg.calculations = _calc
_pkg.metrics = _m
_pkg.log_utils = _lu
sys.modules["drive_cycle_calculator"] = _pkg
sys.modules["drive_cycle_calculator.calculations"] = _calc
sys.modules["drive_cycle_calculator.metrics"] = _m
sys.modules["drive_cycle_calculator.log_utils"] = _lu
