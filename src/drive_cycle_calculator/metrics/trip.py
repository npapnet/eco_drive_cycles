# trip.py
# -------
# Trip and TripCollection — the core domain classes for eco-driving analysis.
#
# Trip wraps one recorded session (one processed .xlsx sheet or one raw OBD file).
# TripCollection groups multiple trips and supports representative-trip selection.

from __future__ import annotations

import re
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
    _normalise_columns,
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
        if "speed_ms" not in self._df.columns:
            return float("nan")
        return float(pd.to_numeric(self._df["speed_ms"], errors="coerce").max() * 3.6)

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
        trips = [
            Trip(_normalise_columns(df), name)
            for name, df in sheets.items()
            if not df.empty
        ]
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

    # ── Parquet persistence ───────────────────────────────────────────────────

    @staticmethod
    def _sanitise_name(name: str) -> str:
        """Replace filesystem-unsafe characters with '_'."""
        return re.sub(r"[^\w\-.]", "_", name)

    def to_parquet(self, directory: str | Path, overwrite: bool = True) -> None:
        """Write each trip as {trip_name}.parquet in directory.

        Overwrites existing files by default (overwrite=True). Suitable for
        research workflows where re-ingesting after algorithm changes is common.

        Raises
        ------
        ValueError
            If two trips in this collection produce the same sanitised filename
            (within-collection name collision). Check names before any writes.
        FileNotFoundError
            If directory does not exist.
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # Pre-check for within-collection name collisions before any writes.
        sanitised = [self._sanitise_name(t.name) for t in self.trips]
        if len(sanitised) != len(set(sanitised)):
            from collections import Counter
            dupes = [n for n, c in Counter(sanitised).items() if c > 1]
            raise ValueError(
                f"Name collision after sanitisation — two trips map to the same "
                f"filename: {dupes}. Rename source trips before ingesting."
            )

        for trip, stem in zip(self.trips, sanitised):
            path = directory / f"{stem}.parquet"
            if path.exists() and not overwrite:
                raise ValueError(
                    f"File already exists: {path}. Pass overwrite=True to replace."
                )
            trip._df.to_parquet(path, index=True)
            trip._path = path  # enables to_duckdb_catalog() to find the file

    @classmethod
    def from_parquet(cls, directory: str | Path) -> "TripCollection":
        """Load all .parquet files in directory as a TripCollection.

        Files are sorted by name for deterministic ordering. Trip.name is inferred
        from the filename stem (round-trip symmetric with to_parquet()).

        Raises
        ------
        FileNotFoundError
            If directory does not exist.
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        trips = []
        for parquet_path in sorted(directory.glob("*.parquet")):
            df = pd.read_parquet(parquet_path)
            trips.append(Trip(df, parquet_path.stem))
        return cls(trips)

    # ── DuckDB catalog ────────────────────────────────────────────────────────

    def to_duckdb_catalog(self, db_path: str | Path) -> None:
        """Write/update trip metadata in a DuckDB catalog file.

        Creates the `trip_metadata` table if it does not exist. Upserts rows
        keyed on trip_id (INSERT OR REPLACE). Empty TripCollection is a no-op
        and does NOT truncate an existing catalog.

        Column mapping to DBML trips schema:
          avg_velocity_kmh  ← trip.metrics['mean_speed']
          max_velocity_kmh  ← trip.max_speed
          avg_acceleration_ms2 ← trip.metrics['mean_acc']
          avg_deceleration_ms2 ← trip.metrics['mean_dec']
          idle_time_pct     ← trip.metrics['stop_pct']  (approximation: speed ≤ 2 km/h;
                              current instrumentation cannot distinguish engine-idle
                              from low-speed motion)
          stop_count        ← trip.metrics['stops']
          duration_s        ← trip.metrics['duration']

        Notes
        -----
        parquet_path stores the absolute local path. pla_trajectory_uri mirrors this
        locally; at Supabase migration it is updated to the S3/GCS URL.
        Moving the data directory will stale the catalog — paths are absolute.

        Raises
        ------
        FileNotFoundError
            If the parent directory of db_path does not exist.
        """
        import duckdb

        db_path = Path(db_path)
        if not db_path.parent.exists():
            raise FileNotFoundError(f"Directory not found: {db_path.parent}")

        _CREATE = """
        CREATE TABLE IF NOT EXISTS trip_metadata (
            trip_id               VARCHAR PRIMARY KEY,
            parquet_path          VARCHAR NOT NULL,
            start_time            TIMESTAMP,
            end_time              TIMESTAMP,
            duration_s            DOUBLE,
            avg_velocity_kmh      DOUBLE,
            max_velocity_kmh      DOUBLE,
            avg_acceleration_ms2  DOUBLE,
            avg_deceleration_ms2  DOUBLE,
            idle_time_pct         DOUBLE,
            stop_count            INTEGER,
            estimated_fuel_liters DOUBLE,
            wavelet_anomaly_count INTEGER,
            markov_matrix_uri     VARCHAR,
            pla_trajectory_uri    VARCHAR
        )
        """
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(_CREATE)
            for trip in self.trips:
                m = trip.metrics
                sanitised = self._sanitise_name(trip.name)
                # parquet_path is stored alongside to_parquet() output; we don't
                # know the directory here, so we derive it from trip._path if set.
                parquet_path = str(trip._path) if trip._path is not None else ""
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trip_metadata VALUES (
                        ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?
                    )
                    """,
                    [
                        sanitised,
                        parquet_path,
                        m["duration"] if not np.isnan(m["duration"]) else None,
                        m["mean_speed"] if not np.isnan(m["mean_speed"]) else None,
                        trip.max_speed if not np.isnan(trip.max_speed) else None,
                        m["mean_acc"] if not np.isnan(m["mean_acc"]) else None,
                        m["mean_dec"] if not np.isnan(m["mean_dec"]) else None,
                        m["stop_pct"] if not np.isnan(m["stop_pct"]) else None,
                        m["stops"],
                        parquet_path,   # pla_trajectory_uri = parquet_path locally
                    ],
                )

    @classmethod
    def from_duckdb_catalog(cls, db_path: str | Path) -> "TripCollection":
        """Load trip stubs from DuckDB catalog. DataFrames are NOT loaded yet.

        Creates Trip(df=None, name=trip_id) with _path set to parquet_path.
        The DataFrame is loaded lazily on first access to .metrics, .speed_profile,
        or ._df.

        Notes
        -----
        parquet_path is stored as an absolute local path. If the data directory
        has moved since the catalog was written, accessing trip data will raise
        FileNotFoundError.

        Raises
        ------
        FileNotFoundError
            If db_path does not exist.
        """
        import duckdb

        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(f"Catalog not found: {db_path}")

        with duckdb.connect(str(db_path), read_only=True) as conn:
            rows = conn.execute(
                "SELECT trip_id, parquet_path FROM trip_metadata"
            ).fetchall()

        trips = []
        for trip_id, parquet_path in rows:
            t = Trip(df=None, name=trip_id)
            t._path = Path(parquet_path) if parquet_path else None
            trips.append(t)
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
