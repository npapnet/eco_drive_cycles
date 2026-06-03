OBDFile
=======

Entry point for raw OBD recordings. Wraps a single raw OBD export file, validates
the required columns, and provides format-specific constructors.

**Strict mode** (default, always used by the CLI): missing curated columns raise
``ValueError``.

**Permissive mode** (``strict=False``, library/debug use): missing columns are
injected as NaN.

.. autoclass:: drive_cycle_calculator.OBDFile
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource
