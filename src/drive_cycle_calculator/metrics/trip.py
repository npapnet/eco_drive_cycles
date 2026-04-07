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

from drive_cycle_calculator.metrics._computations import _compute_session_metrics


class Trip:
    """One recorded driving session.

    Parameters
    ----------
    df : pd.DataFrame
        Processed DataFrame with columns produced by calculations.run_calculations()
        or _computations._process_raw_df().
    name : str
        Sheet / session name, e.g. '2025-05-14_Morning'.
    """

    def __init__(self, df: pd.DataFrame | None = None, name: str = "") -> None:
        self.__df = df
        self.name = name
        self._path: Path | None = None  # set by from_duckdb_catalog() for lazy loading

    @property
    def _df(self) -> pd.DataFrame:
        """Return the DataFrame, loading from _path on first access if needed."""
        if self.__df is None:
            if self._path is None:
                raise RuntimeError(
                    f"Trip {self.name!r} has no DataFrame and no _path set."
                )
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
        """Session label, e.g. 'Morning' or 'Evening'. 'Unknown' if no '_' in name."""
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
        return _compute_session_metrics(self._df)

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

    # ── Future stubs ──────────────────────────────────────────────────────────

    @property
    def microtrips(self) -> list:
        """Microtrip segmentation — not yet implemented.

        See TODOS.md: 'Microtrip segmentation (P1)'.
        """
        raise NotImplementedError(
            "Microtrip segmentation is planned for a future release. "
            "See TODOS.md for tracking."
        )

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Trip(name={self.name!r}, mean_speed={self.mean_speed:.1f} km/h)"


# Backward-compat re-export — TripCollection now lives in trip_collection.py.
from drive_cycle_calculator.metrics.trip_collection import TripCollection  # noqa: E402, F401
