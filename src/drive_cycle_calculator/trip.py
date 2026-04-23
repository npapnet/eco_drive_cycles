# trip.py
# -------
# Trip — the core domain class for a single recorded driving session.
#
# TripCollection has been extracted to trip_collection.py.
# The re-export below preserves backward compatibility for code that imports
# TripCollection directly from this module.

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import pandas as pd

from drive_cycle_calculator.microtrip import Microtrip
from drive_cycle_calculator.schema import SegmentationConfig


class Trip:
    """One recorded driving session.

    Parameters
    ----------
    df : pd.DataFrame
        Processed DataFrame with columns produced by _computations.process_raw_df().
    name : str
        Sheet / session name, e.g. '2025-05-14_Morning'.
    """

    def __init__(
        self,
        df: pd.DataFrame | None = None,
        name: str = "",
        stop_threshold_kmh: float = 2.0,
        parquet_id: str = "",
    ) -> None:
        self.__df = df
        self.name = name
        self.stop_threshold_kmh = stop_threshold_kmh
        self.parquet_id = parquet_id
        self._path: Path | None = None  # set by from_duckdb_catalog() for lazy loading

    @property
    def _df(self) -> pd.DataFrame:
        """Return the DataFrame, loading from _path on first access if needed."""
        if self.__df is None:
            if self._path is None:
                raise RuntimeError(f"Trip {self.name!r} has no DataFrame and no _path set.")
            if not self._path.exists():
                raise FileNotFoundError(
                    f"Parquet file for trip {self.name!r} not found: {self._path}"
                )
            self.__df = pd.read_parquet(self._path)
        return self.__df

    # ── Identity ─────────────────────────────────────────────────────────────

    @cached_property
    def date(self) -> str:
        """Date portion of name, e.g. '2025-05-14'. Returns full name if no '_'."""
        return self.name.split("_", 1)[0] if "_" in self.name else self.name

    @cached_property
    def session(self) -> str:
        """Session label, e.g. 'Morning' or 'Evening'. 'Unknown' if no '_' in name.

        TODO: remove this property in favor of parsing session labels from metadata when creating Trip objects, rather than relying on naming conventions. See TODOS.md: 'Session labels from metadata (P1)'.
        """
        return self.name.split("_", 1)[1] if "_" in self.name else "Unknown"

    # ── Metrics (computed once on first access, then cached) ─────────────────
    #
    # metrics is the single computation; the 7 scalar properties are thin
    # read-through aliases that provide a nicer access path.

    @cached_property
    def metrics(self) -> dict:
        """All 7 session metrics.

        Keys: duration, mean_speed, mean_ns, stops, stop_pct, mean_acc, mean_dec.
        Missing source columns return NaN rather than raising.
        """
        df = self._df
        stop_threshold_kmh = self.stop_threshold_kmh

        duration = (
            float(df["elapsed_s"].dropna().max()) if "elapsed_s" in df.columns else float("nan")
        )

        # Speed: prefer smooth_speed_kmh (new pipeline); fall back to speed_ms (old pipeline).
        if "smooth_speed_kmh" in df.columns:
            speed_kmh = pd.to_numeric(df["smooth_speed_kmh"], errors="coerce").dropna()
        elif "speed_ms" in df.columns:
            speed_kmh = pd.to_numeric(df["speed_ms"], errors="coerce").dropna() * 3.6
        else:
            speed_kmh = pd.Series(dtype=float)
        mean_speed = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0

        moving = speed_kmh[speed_kmh > stop_threshold_kmh]
        mean_ns = float(moving.mean()) if not moving.empty else 0.0

        total_rows = len(speed_kmh)
        stops = int((speed_kmh <= stop_threshold_kmh).sum())
        stop_pct = (stops / total_rows * 100) if total_rows else 0.0

        # Acceleration: prefer acc_ms2 (new pipeline); fall back to split columns (old pipeline).
        if "acc_ms2" in df.columns:
            acc = pd.to_numeric(df["acc_ms2"], errors="coerce")
            mean_acc = float(acc.where(acc > 0).mean())
            mean_dec = float(acc.where(acc < 0).mean())
        else:
            mean_acc = (
                float(pd.to_numeric(df["acceleration_ms2"], errors="coerce").mean())
                if "acceleration_ms2" in df.columns
                else float("nan")
            )
            mean_dec = (
                float(pd.to_numeric(df["deceleration_ms2"], errors="coerce").mean())
                if "deceleration_ms2" in df.columns
                else float("nan")
            )

        return dict(
            duration=duration,
            mean_speed=mean_speed,
            mean_ns=mean_ns,
            stops=stops,
            stop_pct=stop_pct,
            mean_acc=mean_acc,
            mean_dec=mean_dec,
        )

    @cached_property
    def duration(self) -> float:
        """Trip duration in seconds."""
        return self.metrics["duration"]

    @cached_property
    def mean_speed(self) -> float:
        """Mean speed in km/h (including stops)."""
        return self.metrics["mean_speed"]

    @cached_property
    def mean_speed_no_stops(self) -> float:
        """Mean speed in km/h excluding stop samples (speed ≤ 2 km/h)."""
        return self.metrics["mean_ns"]

    @cached_property
    def stop_count(self) -> int:
        """Number of samples at or below the stop threshold (row count, not events)."""
        return self.metrics["stops"]

    @cached_property
    def stop_pct(self) -> float:
        """Percentage of samples at or below the stop threshold."""
        return self.metrics["stop_pct"]

    @cached_property
    def mean_acceleration(self) -> float:
        """Mean positive acceleration in m/s²."""
        return self.metrics["mean_acc"]

    @cached_property
    def mean_deceleration(self) -> float:
        """Mean negative deceleration (braking) in m/s²."""
        return self.metrics["mean_dec"]

    # ── Public DataFrame accessors ────────────────────────────────────────────
    #
    # Microtrip._resolve_data() calls trip.data; trip.file is the parquet key.
    # These are thin public aliases over the private lazy-load mechanism.

    @property
    def data(self) -> pd.DataFrame:
        """The processed DataFrame for this trip.

        Public alias for the internal lazy-load accessor. Required by
        Microtrip._resolve_data().

        See microtrip_design_spec.md §4.2.
        """
        return self._df

    @property
    def file(self) -> Path | None:
        """Path to the archive Parquet backing this trip, or None if in-memory only.

        See microtrip_design_spec.md §4.2.
        """
        return self._path

    # ── Speed profile (accesses full DataFrame) ───────────────────────────────

    @cached_property
    def speed_profile(self) -> tuple[pd.Series, pd.Series]:
        """Return (elapsed_s, smooth_speed_kmh) aligned Series for plotting.

        Reads:
          - 'elapsed_s' for the x-axis (elapsed seconds)
          - 'smooth_speed_kmh' for smoothed speed in km/h

        Both Series are truncated to min(len(x), len(y)) to guarantee alignment.

        Raises
        ------
        RuntimeError
            If 'smooth_speed_kmh' is not present in the DataFrame.
        """
        if "smooth_speed_kmh" not in self._df.columns:
            raise RuntimeError(
                f"Smoothed speed column not found in trip {self.name!r}. "
                f"Expected 'smooth_speed_kmh'."
            )
        x = pd.to_numeric(self._df["elapsed_s"], errors="coerce").dropna()
        y = pd.to_numeric(self._df["smooth_speed_kmh"], errors="coerce").dropna()
        n = min(len(x), len(y))
        return x.iloc[:n], y.iloc[:n]

    @cached_property
    def max_speed(self) -> float:
        """Maximum speed in km/h."""
        if "smooth_speed_kmh" not in self._df.columns:
            return float("nan")
        return float(pd.to_numeric(self._df["smooth_speed_kmh"], errors="coerce").max())

    # ── Segmentation ──────────────────────────────────────────────────────────

    @property
    def microtrips(self) -> list[Microtrip]:
        """Microtrip segmentation — not yet implemented.

        Deprecated stub. Use Trip.segment(config) instead.

        See microtrip_design_spec.md §4.2, TODOS.md: 'Microtrip segmentation (P1)'.
        """
        raise NotImplementedError(
            "Use Trip.segment(config) to obtain microtrips. "
            "See microtrip_design_spec.md §5 and TODOS.md for tracking."
        )

    def segment(self, config: SegmentationConfig) -> list[Microtrip]:
        """Segment this trip into microtrips using the given segmentation config.

        Delegates to detect_boundaries() then build_microtrips(). Each returned
        Microtrip has its weakref bound to this Trip instance.

        Parameters
        ----------
        config : SegmentationConfig
            Segmentation parameters: stop threshold, minimum durations,
            minimum distance.

        Returns
        -------
        list[Microtrip]
            Ordered list of microtrips. Empty list if no valid segments are
            found (e.g. trip is entirely stopped, or all segments are below
            the minimum duration/distance filters).

        See microtrip_design_spec.md §5 (two-stage design).
        """
        from drive_cycle_calculator.segmentation import build_microtrips, detect_boundaries

        data = self.data
        if "smooth_speed_kmh" not in data.columns:
            return []

        # reset_index guarantees 0-based positions that match iloc in build_microtrips.
        speed = (
            pd.to_numeric(data["smooth_speed_kmh"], errors="coerce")
            .fillna(0.0)
            .reset_index(drop=True)
        )
        boundaries = detect_boundaries(speed, config)
        return build_microtrips(self, boundaries, config)

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Trip(name={self.name!r}, mean_speed={self.mean_speed:.1f} km/h)"
