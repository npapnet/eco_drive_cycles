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

    **Bound mode** (from segmentation): data access goes via weakref to the live
    Trip. Raises RuntimeError if the Trip is garbage-collected (D1: no fallback).

    **Standalone mode** (from ``from_parquet()``): data is held directly in
    ``_df``; no weakref needed. Use this mode for synthesis.

    Fields
    ------
    trip_file : Path
        Path to the archive Parquet that produced the parent Trip.
        Kept for traceability; not required for data access in standalone mode.
    parquet_id : str
        6-char GPS hash from ParquetMetadata. Canonical foreign key.
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
    _df: pd.DataFrame | None = PrivateAttr(default=None)
    _path: Path | None = PrivateAttr(default=None)

    def bind(self, trip: Trip) -> None:
        """Bind an in-memory Trip reference for fast data access.

        Must be called immediately after instantiation. Without a live
        reference all data-access properties raise RuntimeError.

        See microtrip_design_spec.md §4.1.
        """
        self._trip_ref = weakref.ref(trip)

    @property
    def path(self) -> Path | None:
        """Own saved Parquet path, or None if this microtrip has not been persisted."""
        return self._path

    @property
    def samples(self) -> pd.DataFrame:
        """Motion samples for this microtrip.

        In standalone mode returns ``_df.iloc[start_idx:end_idx]``.
        In bound mode returns the slice from the live parent Trip.

        Raises
        ------
        RuntimeError
            If bound mode and the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §4.1.
        """
        return self._resolve_data().iloc[self.start_idx:self.end_idx]

    @property
    def stop_samples(self) -> pd.DataFrame:
        """Trailing stop samples (the stop that closes this microtrip).

        Raises
        ------
        RuntimeError
            If bound mode and the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §2.2, §4.1.
        """
        return self._resolve_data().iloc[self.stop_start_idx:self.stop_end_idx]

    @property
    def stop_duration_after(self) -> float:
        """Duration of the trailing stop in seconds.

        Raises
        ------
        RuntimeError
            If bound mode and the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §4.1.
        """
        ss = self.stop_samples
        if "elapsed_s" not in ss.columns or len(ss) < 2:
            return 0.0
        elapsed = pd.to_numeric(ss["elapsed_s"], errors="coerce").dropna()
        if len(elapsed) < 2:
            return 0.0
        return float(elapsed.iloc[-1] - elapsed.iloc[0])

    def to_parquet(self, dest: Path) -> None:
        """Write motion + stop samples to a Parquet file.

        Stores ``n_motion``, ``trip_file``, and ``parquet_id`` in Parquet
        metadata so the file is self-describing. Sets ``self._path`` so the
        microtrip becomes self-locating after the call.

        Parameters
        ----------
        dest : Path
            Destination Parquet path. Parent directory must exist.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        motion = self.samples.reset_index(drop=True)
        stop = self.stop_samples.reset_index(drop=True)
        n_motion = len(motion)
        combined = pd.concat([motion, stop], ignore_index=True)

        table = pa.Table.from_pandas(combined, preserve_index=False)
        existing = table.schema.metadata or {}
        meta = {
            **existing,
            b"mt_n_motion": str(n_motion).encode(),
            b"mt_trip_file": str(self.trip_file).encode(),
            b"mt_parquet_id": self.parquet_id.encode(),
        }
        table = table.replace_schema_metadata(meta)
        pq.write_table(table, dest)
        self._path = dest

    @classmethod
    def from_parquet(cls, path: Path) -> "Microtrip":
        """Load a standalone microtrip from a Parquet file written by ``to_parquet``.

        Sets ``_df`` directly — no weakref is needed. ``trip_file`` is
        restored from Parquet metadata for traceability but is not used for
        data access.

        Parameters
        ----------
        path : Path
            Parquet file previously written by ``to_parquet()``.
        """
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        raw_meta = pf.schema_arrow.metadata or {}
        n_motion = int(raw_meta.get(b"mt_n_motion", b"0"))
        trip_file_str = raw_meta.get(b"mt_trip_file", b"").decode()
        parquet_id = raw_meta.get(b"mt_parquet_id", b"").decode()

        df = pf.read().to_pandas()
        n_total = len(df)

        mt = cls(
            trip_file=Path(trip_file_str) if trip_file_str else Path(""),
            parquet_id=parquet_id,
            start_idx=0,
            end_idx=n_motion,
            stop_start_idx=n_motion,
            stop_end_idx=n_total,
        )
        mt._df = df
        mt._path = path
        return mt

    def _resolve_data(self) -> pd.DataFrame:
        """Return the data source: ``_df`` in standalone mode, Trip in bound mode.

        Raises
        ------
        RuntimeError
            If bound mode and the parent Trip has been garbage-collected.

        See microtrip_design_spec.md §4.1 (D1: no fallback in bound mode).
        """
        if self._df is not None:
            return self._df
        trip = self._trip_ref() if self._trip_ref is not None else None
        if trip is None:
            raise RuntimeError(
                f"Microtrip (parquet_id={self.parquet_id!r}) has no live Trip reference. "
                "The parent Trip has been garbage-collected. "
                "See microtrip_design_spec.md §4.1 (D1: no fallback)."
            )
        return trip.data
