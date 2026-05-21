ProcessingConfig
================

Pydantic ``BaseModel`` that controls smoothing and stop detection applied to raw OBD
data. Passed to :py:meth:`OBDFile.to_trip` and :py:meth:`TripCollection` constructors.

The ``config_hash`` property (first 8 hex chars of the MD5 of sorted JSON fields) is
stored alongside metrics in DuckDB so every row can be traced back to the exact
configuration that produced it.

.. autoclass:: drive_cycle_calculator.processing_config.ProcessingConfig
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource

.. autodata:: drive_cycle_calculator.processing_config.DEFAULT_CONFIG
