Segmentation
============

Two-stage microtrip segmentation:

1. **Boundary detection** — ``detect_boundaries()`` scans the speed signal for
   transitions below ``stop_threshold_kmh`` lasting at least ``stop_min_duration_s``.
2. **Microtrip construction** — ``build_microtrips()`` slices the trip at each
   boundary, discards segments that are too short (duration or distance), and attaches
   the trailing stop period to each microtrip.

:py:class:`MicrotripSegmenter` is the high-level entry point; it wraps both stages and
accepts a :py:class:`~drive_cycle_calculator.schema.SegmentationConfig`.

.. autoclass:: drive_cycle_calculator.MicrotripSegmenter
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource

.. automodule:: drive_cycle_calculator.segmentation
   :members: SegmentBoundary, detect_boundaries, build_microtrips
   :undoc-members: False
