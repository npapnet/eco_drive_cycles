# trip.py
# -------
# Trip and TripCollection — the core domain classes for eco-driving analysis.
#
# Trip wraps one recorded session (one processed .xlsx sheet or one raw OBD file).
# TripCollection groups multiple trips and supports representative-trip selection.

from __future__ import annotations

import warnings
import zipfile
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from drive_cycle_calculator.metrics._computations import (
    _SEVEN_METRIC_KEYS,
    _compute_session_metrics,
    _infer_sheet_name,
    _process_raw_df,
    _similarity,
)


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

    def __init__(self, df: pd.DataFrame, name: str = "") -> None:
        self._df = df
        self.name = name
        self._path: Path | None = None  # reserved for future lazy loading

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
        """Return (duration_sec, smoothed_speed_kmh) aligned Series for plotting.

        Reads:
          - 'Διάρκεια (sec)' for the x-axis (elapsed seconds)
          - 'Εξομαλυνση' or 'Εξομάλυνση' (accent variant) for smoothed speed km/h

        Both Series are truncated to min(len(x), len(y)) to guarantee alignment.

        Raises
        ------
        RuntimeError
            If neither smoothed-speed column variant is present.
        """
        smooth_candidates = ["Εξομαλυνση", "Εξομάλυνση"]
        smooth_col = next(
            (c for c in smooth_candidates if c in self._df.columns), None
        )
        if smooth_col is None:
            raise RuntimeError(
                f"Smoothed speed column not found in trip {self.name!r}. "
                f"Expected one of {smooth_candidates}."
            )
        x = pd.to_numeric(self._df["Διάρκεια (sec)"], errors="coerce").dropna()
        y = pd.to_numeric(self._df[smooth_col], errors="coerce").dropna()
        n = min(len(x), len(y))
        return x.iloc[:n], y.iloc[:n]

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


class TripCollection:
    """A set of recorded driving sessions.

    Construct via:
      - TripCollection.from_excel(path)   — combined log xlsx (one sheet per trip)
      - TripCollection.from_folder(path)  — folder of raw OBD xlsx files
      - TripCollection([trip1, trip2, …]) — from existing Trip objects
    """

    def __init__(self, trips: list[Trip]) -> None:
        self.trips = trips

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_excel(cls, path: str | Path) -> "TripCollection":
        """Load from a combined calculations-log xlsx (one sheet per trip).

        The log xlsx is produced by calculations.run_calculations() and already
        contains processed columns (smoothed speed, acceleration, duration).
        Empty sheets are silently skipped.

        Raises
        ------
        FileNotFoundError
            If path does not exist.
        ValueError
            If the file contains zero valid (non-empty) sheets.
        """
        sheets = pd.read_excel(Path(path), sheet_name=None)
        trips = [Trip(df, name) for name, df in sheets.items() if not df.empty]
        if not trips:
            raise ValueError(f"No valid sheets found in {path}")
        return cls(trips)

    @classmethod
    def from_folder(cls, folder: str | Path) -> "TripCollection":
        """Load from a folder of raw OBD xlsx files. No intermediate files written.

        Each xlsx is processed in memory via _process_raw_df() (GPS time conversion,
        rolling smoothing, acceleration derivation). Files that cannot be parsed are
        skipped with a warnings.warn() call. Returns an empty TripCollection if no
        valid files are found — check len(tc) > 0 before calling find_representative().

        Raises
        ------
        FileNotFoundError
            If folder does not exist.
        """
        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")
        trips = []
        for xlsx_path in sorted(folder.glob("*.xlsx")):
            try:
                df_raw = pd.read_excel(xlsx_path)
                df = _process_raw_df(df_raw)
                name = _infer_sheet_name(df_raw, xlsx_path)
                trips.append(Trip(df, name))
            except (OSError, ValueError, pd.errors.ParserError, zipfile.BadZipFile) as exc:
                warnings.warn(f"Skipping {xlsx_path.name}: {exc}", stacklevel=2)
        return cls(trips)

    # ── Analysis ─────────────────────────────────────────────────────────────

    def similarity_scores(self) -> dict[str, float]:
        """Mean similarity score (0–100) per trip name.

        The scoring loop lives here; find_representative() delegates to this method.

        Algorithm:
          1. Compute metrics for each trip (cached on Trip.metrics)
          2. Compute overall mean for each of the 7 metrics via np.nanmean
          3. For each trip, compute _similarity(overall[k], trip.metrics[k]) for all k
          4. Return {trip.name: mean_similarity_score}

        100 = perfect match to collection average. 0 = maximally dissimilar.

        Raises
        ------
        ValueError
            If the collection is empty.
        """
        if not self.trips:
            raise ValueError(
                "Cannot compute similarity scores: collection is empty."
            )
        per = {t.name: t.metrics for t in self.trips}
        overall = {
            k: float(np.nanmean([m[k] for m in per.values()]))
            for k in _SEVEN_METRIC_KEYS
        }
        return {
            t.name: float(
                np.nanmean([_similarity(overall[k], t.metrics[k]) for k in _SEVEN_METRIC_KEYS])
            )
            for t in self.trips
        }

    def find_representative(self) -> "Trip":
        """Return the trip most similar to the collection average (7-metric scoring).

        Delegates to similarity_scores() and returns the argmax.

        Raises
        ------
        ValueError
            If the collection is empty.
        """
        if not self.trips:
            raise ValueError(
                "Cannot find representative trip: collection is empty. "
                "Check len(tc) > 0 before calling this method."
            )
        scores = self.similarity_scores()
        best_name = max(scores, key=scores.__getitem__)
        return next(t for t in self.trips if t.name == best_name)

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.trips)

    def __iter__(self):
        return iter(self.trips)

    def __repr__(self) -> str:
        return f"TripCollection({len(self.trips)} trips)"
