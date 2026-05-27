Schema & Metadata Models
========================

All Pydantic models and OBD column constants live in ``schema.py``.

Models are grouped by who populates them:

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Model
     - Populated by
     - Key fields
   * - ``UserMetadata``
     - User (YAML)
     - ``user``, ``vehicle_make``, ``vehicle_model``, ``engine_size_cc``, ``year``, ``fuel_type``, ``vehicle_category``
   * - ``IngestProvenance``
     - Ingest process
     - ``ingest_timestamp``, ``source_filename``
   * - ``ComputedTripStats``
     - GPS signal
     - ``start_time``, ``end_time``, ``gps_lat_mean``, ``gps_lon_mean``
   * - ``ParquetMetadata``
     - Root container
     - ``schema_version``, ``software_version``, ``parquet_id`` + three sub-models

``ParquetMetadata`` is embedded in every archive Parquet under the PyArrow custom
metadata key ``"dcc_metadata"`` as a JSON string.

OBD Column Constants
--------------------

.. autodata:: drive_cycle_calculator.schema.OBD_COLUMN_MAP

.. autodata:: drive_cycle_calculator.schema.CURATED_COLS

Pydantic Models
---------------

.. autoclass:: drive_cycle_calculator.schema.UserMetadata
   :members:

.. autoclass:: drive_cycle_calculator.schema.IngestProvenance
   :members:

.. autoclass:: drive_cycle_calculator.schema.ComputedTripStats
   :members:

.. autoclass:: drive_cycle_calculator.schema.ParquetMetadata
   :members:

.. autoclass:: drive_cycle_calculator.schema.SegmentationConfig
   :members:
