# trip_collection.py
# ------------------
# TripCollection — groups multiple Trip objects and supports representative-trip
# selection via 7-metric similarity scoring.
#
# This file is the canonical home for TripCollection.
# metrics/__init__.py re-exports it to preserve the public API.

from __future__ import annotations

import re
import warnings
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from drive_cycle_calculator.obd_file import OBDFile
    from drive_cycle_calculator.processing_config import ProcessingConfig
    from drive_cycle_calculator.trip import Trip


_SEVEN_METRIC_KEYS = (
    "duration",
    "mean_speed",
    "mean_ns",
    "stops",
    "stop_pct",
    "mean_acc",
    "mean_dec",
)


class TripCollection:
    """A set of recorded driving sessions.

    Construct via:
      - TripCollection.from_excel(path)             — combined log xlsx
      - TripCollection.from_folder(path)            — folder of raw OBD xlsx
      - TripCollection.from_folder_raw(path)        — returns list[OBDFile]
      - TripCollection.from_archive_parquets(path)  — v2 archive Parquets
      - TripCollection.from_duckdb_catalog(db_path) — DuckDB catalog
      - TripCollection([trip1, trip2, …])            — from existing Trips
    """

    def __init__(self, trips: list[Trip]) -> None:
        self.trips = trips

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_folder(
        cls,
        folder: str | Path,
        config: "ProcessingConfig | None" = None,
    ) -> "TripCollection":
        """Load from a folder of raw OBD xlsx files using the OBDFile pipeline.

        Each xlsx is processed via OBDFile.from_xlsx() → to_trip(config).
        Files that cannot be parsed are skipped with a warnings.warn() call.

        Parameters
        ----------
        folder : str | Path
            Directory containing *.xlsx files.
        config : ProcessingConfig, optional
            Processing parameters. Defaults to DEFAULT_CONFIG (window=4).

        Raises
        ------
        FileNotFoundError
            If folder does not exist.
        """
        from drive_cycle_calculator.obd_file import OBDFile
        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG

        if config is None:
            config = DEFAULT_CONFIG

        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")
        trips = []
        for xlsx_path in sorted(folder.glob("*.xlsx")):
            try:
                obd = OBDFile.from_xlsx(xlsx_path)
                trips.append(obd.to_trip(config))
            except (OSError, ValueError, pd.errors.ParserError, zipfile.BadZipFile) as exc:
                warnings.warn(f"Skipping {xlsx_path.name}: {exc}", stacklevel=2)
        return cls(trips)

    @classmethod
    def from_folder_raw(cls, folder: str | Path) -> "list[OBDFile]":
        """Load all xlsx files in folder as raw OBDFile objects. No processing.

        Returns a plain list[OBDFile] — not a TripCollection. Use this for
        interactive data-quality inspection before archiving:

            raw_files = TripCollection.from_folder_raw("./raw_data/")
            for f in raw_files:
                print(f.name, f.quality_report()["missing_curated_cols"])

        Parameters
        ----------
        folder : str | Path
            Directory containing *.xlsx files.

        Raises
        ------
        FileNotFoundError
            If folder does not exist.
        """
        from drive_cycle_calculator.obd_file import OBDFile

        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")
        result: list[OBDFile] = []
        for xlsx_path in sorted(folder.glob("*.xlsx")):
            try:
                result.append(OBDFile.from_xlsx(xlsx_path))
            except (OSError, ValueError, pd.errors.ParserError, zipfile.BadZipFile) as exc:
                warnings.warn(f"Skipping {xlsx_path.name}: {exc}", stacklevel=2)
        return result

    @classmethod
    def from_archive_parquets(
        cls,
        directory: str | Path,
        config: "ProcessingConfig | None" = None,
    ) -> "TripCollection":
        """Load v2 archive Parquets and build a TripCollection.

        Each Parquet is loaded via OBDFile.from_parquet() — raises ValueError if
        any file is in the old v1 processed format (smooth_speed_kmh present).

        Parameters
        ----------
        directory : str | Path
            Directory containing *.parquet archive files.
        config : ProcessingConfig, optional
            Processing parameters. Defaults to DEFAULT_CONFIG (window=4).

        Raises
        ------
        FileNotFoundError
            If directory does not exist.
        ValueError
            If any Parquet in the folder is in the old v1 format.
        """
        from drive_cycle_calculator.obd_file import OBDFile
        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG

        if config is None:
            config = DEFAULT_CONFIG

        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        trips = []
        for parquet_path in sorted(directory.glob("*.parquet")):
            try:
                obd = OBDFile.from_parquet(parquet_path)
                trip = obd.to_trip(config)
                trip._path = parquet_path  # so to_duckdb_catalog() knows the archive path
                trips.append(trip)
            except Exception as exc:
                warnings.warn(f"Skipping {parquet_path.name}: {exc}", stacklevel=2)
        return cls(trips)

    # ── Parquet helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_name(name: str) -> str:
        """Replace filesystem-unsafe characters with '_'."""
        return re.sub(r"[^\w\-.]", "_", name)

    # ── DuckDB catalog ────────────────────────────────────────────────────────

    def to_duckdb_catalog(
        self,
        db_path: str | Path,
        config: "ProcessingConfig | None" = None,
    ) -> None:
        """Write/update trip metadata in a DuckDB catalog file.

        Creates the ``trip_metadata`` table if it does not exist. Upserts rows
        keyed on trip_id (INSERT OR REPLACE). Empty TripCollection is a no-op.

        If the table already exists but lacks the ``config_hash`` column, an
        ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` is issued first.

        Parameters
        ----------
        config : ProcessingConfig, optional
            The config used when building this collection. Its hash is stored
            in the catalog for reproducibility auditing.
        """
        import duckdb

        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG

        if config is None:
            config = DEFAULT_CONFIG

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
            pla_trajectory_uri    VARCHAR,
            config_hash           VARCHAR
        )
        """
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(_CREATE)
            # Migrate existing catalogs that lack config_hash column.
            conn.execute("ALTER TABLE trip_metadata ADD COLUMN IF NOT EXISTS config_hash VARCHAR")
            for trip in self.trips:
                m = trip.metrics
                sanitised = self._sanitise_name(trip.name)
                parquet_path = str(trip._path) if trip._path is not None else ""
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trip_metadata VALUES (
                        ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?
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
                        config.config_hash,
                    ],
                )

    @classmethod
    def from_duckdb_catalog(
        cls,
        db_path: str | Path,
        config: "ProcessingConfig | None" = None,
    ) -> "TripCollection":
        """Load trips eagerly from a DuckDB catalog.

        Creates OBDFile stubs from each row's parquet_path, then calls
        to_trip(config) for each. All Parquets are read at load time.

        Parameters
        ----------
        config : ProcessingConfig, optional
            Processing parameters for building Trips from archive Parquets.
            Defaults to DEFAULT_CONFIG.

        Raises
        ------
        FileNotFoundError
            If db_path does not exist.
        """
        import duckdb

        from drive_cycle_calculator.obd_file import OBDFile
        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG

        if config is None:
            config = DEFAULT_CONFIG

        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(f"Catalog not found: {db_path}")

        with duckdb.connect(str(db_path), read_only=True) as conn:
            tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
            table = "trip_metrics" if "trip_metrics" in tables else "trip_metadata"
            rows = conn.execute(f"SELECT trip_id, parquet_path FROM {table}").fetchall()

        trips = []
        for trip_id, parquet_path in rows:
            if parquet_path:
                try:
                    obd = OBDFile.from_parquet(parquet_path)
                    trip = obd.to_trip(config)
                    trip._path = Path(parquet_path)
                    trips.append(trip)
                except Exception as exc:
                    warnings.warn(
                        f"Trip {trip_id!r}: cannot load {parquet_path!r} — {exc}. Skipping.",
                        stacklevel=2,
                    )
            else:
                warnings.warn(
                    f"Trip {trip_id!r} has no parquet_path in catalog — skipping.",
                    stacklevel=2,
                )
        return cls(trips)

    # ── Analysis ─────────────────────────────────────────────────────────────

    def similarity_scores(self) -> dict[str, float]:
        """Mean similarity score (0–100) per trip name.

        Raises
        ------
        ValueError
            If the collection is empty.
        """
        if not self.trips:
            raise ValueError("Cannot compute similarity scores: collection is empty.")
        per = {t.name: t.metrics for t in self.trips}
        overall = {k: float(np.nanmean([m[k] for m in per.values()])) for k in _SEVEN_METRIC_KEYS}
        return {
            t.name: float(
                np.nanmean([similarity(overall[k], t.metrics[k]) for k in _SEVEN_METRIC_KEYS])
            )
            for t in self.trips
        }

    def find_representative(self) -> "Trip":
        """Return the trip most similar to the collection average (7-metric scoring).

        Raises
        ------
        ValueError
            If the collection is empty.
        """
        if not self.trips:
            raise ValueError("Cannot find representative trip: collection is empty.")
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


def similarity(overall_val: float, rep_val: float) -> float:
    """% similarity between a representative value and the overall mean.

    Returns a value in [0, 100]. Perfect match returns 100.0.
    """
    if np.isnan(overall_val):
        return 0.0
    if overall_val == 0:
        return 100.0 if rep_val == 0 else 0.0
    return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)
