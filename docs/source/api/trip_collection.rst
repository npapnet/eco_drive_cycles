TripCollection
==============

Groups multiple :py:class:`~drive_cycle_calculator.Trip` objects loaded from a common
source (folder, archive Parquets, or DuckDB catalog). Provides similarity scoring and
representative trip identification.

**Constructors:**

- ``from_folder`` — raw OBD xlsx/csv files via the ``OBDFile`` pipeline
- ``from_archive_parquets`` — v2 archive Parquets (recommended)
- ``from_folder_raw`` — raw ``OBDFile`` objects only (for QA, no processing)

**Similarity measures** (from :py:mod:`drive_cycle_calculator.similarity`):

- :py:func:`~drive_cycle_calculator.similarity.pct_deviation` (default)
- :py:func:`~drive_cycle_calculator.similarity.cosine_similarity`
- :py:func:`~drive_cycle_calculator.similarity.z_score_distance`

.. autoclass:: drive_cycle_calculator.TripCollection
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource
