# tests/conftest.py
# -----------------
# sys.path shim so tests import from eco_drive_cycles.* namespace today
# (flat layout) and survive unchanged when the repo moves to src/eco_drive_cycles/.
#
# When the src/ restructure lands, delete this file and the tests will
# continue to work against the installed package.

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

_pkg = types.ModuleType("eco_drive_cycles")
_pkg.calculations = _calc
_pkg.metrics = _m
_pkg.log_utils = _lu
sys.modules["eco_drive_cycles"] = _pkg
sys.modules["eco_drive_cycles.calculations"] = _calc
sys.modules["eco_drive_cycles.metrics"] = _m
sys.modules["eco_drive_cycles.log_utils"] = _lu
