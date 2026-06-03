Microtrip Segmentation Specifications
=====================================

In driving cycle analysis and synthesis, a **microtrip** is the fundamental building block. This document details the definition, configuration, and algorithmic segmentation of microtrips in the ``drive_cycle_calculator`` library, based on the system design specifications.

---

Core Concepts & Definitions
---------------------------

The pipeline uses three core entities to model vehicle driving activity:

Microtrip
~~~~~~~~~
A **microtrip** is a motion-based segment of a vehicle journey, defined as the interval from the start of a driving phase to the end of the subsequent sustained stop. 

* **Start condition**: Begins at the first sample where speed rises to or exceeds ``stop_threshold_kmh`` after a stop.
* **End condition**: Ends at the last sample of the trailing stop (inclusive).
* **Key characteristic**: Microtrips are not bounded by ignition states; a single ignition-to-shutdown trip can (and usually does) contain multiple microtrips separated by traffic stops.

Stop
~~~~
A **stop** is a sustained period of near-zero speed.
* **Stop condition**: Sustained duration where speed is strictly below ``stop_threshold_kmh`` for at least ``stop_min_duration_s``.
* **Ownership**: A stop belongs to the **closing microtrip** that precedes it. Stop samples are not duplicated into the following microtrip's motion phase.
* **Duration**: Trailing stop duration is tracked via the ``stop_duration_after`` property.

Trip
~~~~
A **trip** represents a single continuous logging session (typically bounded by ignition-on and ignition-off events). It owns the complete raw time-series DataFrame and acts as the container from which microtrips are segmented and extracted.

---

Segmentation Configuration
--------------------------

Microtrip segmentation is controlled by ``SegmentationConfig`` (defined in the schema), which contains the following parameters:

.. list-table:: Segmentation Configuration Parameters
   :widths: 25 15 60
   :header-rows: 1

   * - Parameter
     - Default
     - Description
   * - ``stop_threshold_kmh``
     - 2.0 km/h
     - Speed below which the vehicle is considered stopped. Accounts for GPS noise and sensor drift.
   * - ``stop_min_duration_s``
     - 1.0 s
     - Minimum duration of sustained low speed required to qualify as a stop boundary (guards against transient dips).
   * - ``microtrip_min_duration_s``
     - 15.0 s
     - Minimum total duration (motion phase + trailing stop) for a microtrip to be kept.
   * - ``microtrip_min_distance_m``
     - 50.0 m
     - Minimum cumulative distance covered by the motion phase. Discards crawl segments.

Domain Constraint
~~~~~~~~~~~~~~~~~
To prevent sensor noise from generating invalid microtrips, the library enforces a hardcoded floor of **5.0 seconds** on the minimum microtrip duration. A Pydantic validator raises a ``ValidationError`` if a user attempts to configure ``microtrip_min_duration_s`` below 5.0 seconds.

---

Two-Stage Segmentation Algorithm
--------------------------------

To maintain a clean architectural separation and facilitate unit testing, the segmentation process is divided into two distinct stages:

.. mermaid::

   flowchart LR
       A["Trip DataFrame\n(Speed Series)"] --> B["Stage 1: Boundary Detection\n(detect_boundaries)"]
       B --> C["List of SegmentBoundary"]
       C --> D["Stage 2: Object Assembly & Filter\n(build_microtrips)"]
       D --> E["List of Microtrip\n(Weakref-bound or Persisted)"]

Stage 1 — Boundary Detection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``detect_boundaries(speed, config)`` function scans a pre-smoothed speed series to locate transition boundaries.
* **Input**: A series of speed values. The input speed must be smoothed upstream (e.g. via ``ProcessingConfig`` rolling average) to ensure noise does not trigger spurious boundaries.
* **Output**: A list of ``SegmentBoundary`` objects, which store the integer indices for:

  - ``motion_start_idx``: First motion sample (inclusive).
  - ``motion_end_idx``: Last motion sample (exclusive).
  - ``stop_start_idx``: First trailing stop sample (inclusive).
  - ``stop_end_idx``: Last trailing stop sample (exclusive).

* **Degenerate handling**: Returns an empty list ``[]`` if the speed series is all zeros, if it is shorter than the minimum duration, or if no valid stops are found.

Stage 2 — Microtrip Construction and Filtering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``build_microtrips(trip, boundaries, config)`` function processes the detected boundaries:
1. **Total Duration Filter**: Verifies if:
   
   .. math::

      \frac{\text{stop\_end\_idx} - \text{motion\_start\_idx}}{\text{sample\_rate}} \ge \text{microtrip\_min\_duration\_s}

2. **Distance Filter**: Computes the cumulative distance covered during the motion phase and checks if it is at least ``microtrip_min_distance_m``.
3. **Binding**: Instantiates a ``Microtrip`` object for boundaries passing both filters, and establishes a weak reference to the parent ``Trip``.

---

Data Model & Persistence Lifecycle
----------------------------------

Dual-Mode Data Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~
A ``Microtrip`` object operates in one of two modes depending on its lifecycle stage:

1. **In-Memory/Bound Mode**:
   During active segmentation, the microtrip holds positional indices and a weak reference (``_trip_ref``) to the parent ``Trip`` container. Data is resolved on-the-fly by slicing the parent Trip's DataFrame. This avoids memory duplication. If the parent Trip is garbage-collected, accessing the data raises a ``RuntimeError``.
2. **Standalone/Persisted Mode**:
   For downstream cycle synthesis, microtrips are exported to disk as Parquet files (containing only the processed columns to save space) and a ``summary.csv`` catalog. When loaded using ``MicrotripCollection.from_parquets()``, the microtrips load their private data directly from their individual Parquet files (stored in the ``_df`` attribute). They do not require a live parent ``Trip`` object, ensuring they are self-contained.

Invariants
~~~~~~~~~~
The library enforces the following structural invariants:

* **Index Stability**: Row order in the microtrip Parquet files matches the original sequence of samples from the parent Trip.
* **Auditability**: All ``SegmentationConfig`` and ``ProcessingConfig`` parameters are serialized and embedded inside the exported microtrip records to provide end-to-end configuration auditability.
