Microtrip
=========

A single motion segment derived from a parent :py:class:`~drive_cycle_calculator.Trip`.
Carries index positions into the parent DataFrame rather than copying data; the parent
Trip is held via a ``weakref`` to avoid reference cycles.

.. warning::
   Microtrips are **intermediate disposable artifacts**. Data access raises
   ``RuntimeError`` if the parent Trip has been garbage-collected.

.. autoclass:: drive_cycle_calculator.microtrip.Microtrip
   :members:
   :undoc-members: False
   :show-inheritance:
   :member-order: bysource
