# microtrip.py
# ------------
# Microtrip — one motion segment of a Trip, from stop to stop.
# See microtrip_design_spec.md §4.1.

from __future__ import annotations

import weakref
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from pydantic import BaseModel, PrivateAttr

if TYPE_CHECKING:
    from drive_cycle_calculator.trip import Trip


class Microtrip(BaseModel):
    """One motion segment bounded by stops, derived from a parent Trip.

    Holds positional iloc indices into the parent Trip's processed DataFrame.
    Data access is live-only via weakref — there is no parquet reload fallback.
    If the parent Trip is garbage-collected, all data-access properties raise.

    Fields
    ------
    trip_file : Path
        Path to the archive Parquet that produced the parent Trip.
        Stable traceability key; not used for data reload.
    parquet_id : str
        6-char GPS hash from ParquetMetadata. Canonical DuckDB foreign key.
    start_idx : int
        Positional (iloc) index of the first motion sample, inclusive.
    end_idx : int
        Positional (iloc) index of the last motion sample, exclusive.
    stop_start_idx : int
        Positional (iloc) index of the first trailing-stop sample, inclusive.
    stop_end_idx : int
        Positional (iloc) index of the last trailing-stop sample, exclusive.

    See microtrip_design_spec.md §4.1.
    """

    trip_file: Path
    parquet_id: str
    start_idx: int
    end_idx: int
    stop_start_idx: int
    stop_end_idx: int

    _trip_ref: weakref.ref | None = PrivateAttr(default=None)

    def bind(self, trip: Trip) -> None:
        """Bind an in-memory Trip reference for fast data access.

        Must be called immediately after instantiation. Without a live
        reference all data-access properties raise RuntimeError.

        See microtrip_design_spec.md §4.1.
        """
        self._trip_ref = weakref.ref(trip)

    @property
    def samples(self) -> pd.DataFrame:
        """Motion samples for this microtrip.

        Returns the slice Trip.data.iloc[start_idx:end_idx].

        Raises
        ------
        RuntimeError
            If the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §4.1.
        """
        return self._resolve_data().iloc[self.start_idx:self.end_idx]

    @property
    def stop_samples(self) -> pd.DataFrame:
        """Trailing stop samples (the stop that closes this microtrip).

        Returns the slice Trip.data.iloc[stop_start_idx:stop_end_idx].
        Stop samples belong to the closing microtrip and are not duplicated
        into the following microtrip.

        Raises
        ------
        RuntimeError
            If the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §2.2, §4.1.
        """
        return self._resolve_data().iloc[self.stop_start_idx:self.stop_end_idx]

    @property
    def stop_duration_after(self) -> float:
        """Duration of the trailing stop in seconds.

        Derived from stop_samples['elapsed_s']: last value minus first value.

        Raises
        ------
        RuntimeError
            If the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §4.1.
        """
        ss = self.stop_samples
        if "elapsed_s" not in ss.columns or len(ss) < 2:
            return 0.0
        elapsed = pd.to_numeric(ss["elapsed_s"], errors="coerce").dropna()
        if len(elapsed) < 2:
            return 0.0
        return float(elapsed.iloc[-1] - elapsed.iloc[0])

    def _resolve_data(self) -> pd.DataFrame:
        """Return the parent Trip's processed DataFrame via weakref.

        No parquet reload fallback. If the Trip is GC'd this raises immediately.

        Raises
        ------
        RuntimeError
            If _trip_ref is unset or the referenced Trip has been GC'd.

        See microtrip_design_spec.md §4.1 (D1: no fallback).
        """
        trip = self._trip_ref() if self._trip_ref is not None else None
        if trip is None:
            raise RuntimeError(
                f"Microtrip (parquet_id={self.parquet_id!r}) has no live Trip reference. "
                "The parent Trip has been garbage-collected. "
                "See microtrip_design_spec.md §4.1 (D1: no fallback)."
            )
        return trip.data
