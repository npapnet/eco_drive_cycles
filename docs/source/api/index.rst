API Reference
=============

The ``drive_cycle_calculator`` package exposes four public classes at the top level:

.. code-block:: python

   from drive_cycle_calculator import OBDFile, Trip, TripCollection, MicrotripSegmenter

All other classes (``Microtrip``, ``ProcessingConfig``, ``SegmentationConfig``,
similarity measures) are accessible from their respective submodules.

.. toctree::
   :maxdepth: 1

   obd_file
   trip
   trip_collection
   microtrip
   segmentation
   processing_config
   schema
   similarity
   clustering
   synthesis_markov
   synthesis_targets
   synthesis_selection
   synthesis_assembly
   synthesis_wltp
   synthesis_cluster

