Trip
====

Represents one processed driving session. Holds the processed DataFrame and exposes
scalar metrics as ``@cached_property`` attributes computed on first access.

Call :py:meth:`Trip.segment` to slice the trip into microtrips.

.. autoclass:: drive_cycle_calculator.Trip
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource
