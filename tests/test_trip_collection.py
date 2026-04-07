"""Tests for TripCollection — constructors, catalog, similarity scoring."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.metrics.trip import Trip
from drive_cycle_calculator.metrics.trip_collection import TripCollection
from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_raw_df(n: int = 20, speed_kmh: float = 30.0) -> pd.DataFrame:
    timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
    return pd.DataFrame({
        "GPS Time": timestamps,
        "Speed (OBD)(km/h)": [speed_kmh] * n,
        "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
        "Engine Load(%)": [50.0] * n,
        "Fuel flow rate/hour(l/hr)": [2.0] * n,
    })


def _write_archive(path: Path, speed_kmh: float = 30.0, n: int = 20) -> None:
    """Write a v2 archive Parquet via OBDFile."""
    OBDFile(_make_raw_df(n=n, speed_kmh=speed_kmh), path.stem).to_parquet(path)


def _write_xlsx(path: Path, speed_kmh: float = 30.0, n: int = 20) -> None:
    _make_raw_df(n=n, speed_kmh=speed_kmh).to_excel(path, index=False)


# ── from_folder (uses OBDFile pipeline) ──────────────────────────────────────

class TestFromFolder:
    def test_loads_all_xlsx(self, tmp_path):
        """from_folder processes all .xlsx files and returns a TripCollection."""
        _write_xlsx(tmp_path / "trip_a.xlsx")
        _write_xlsx(tmp_path / "trip_b.xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 2

    def test_produces_no_speed_ms_column(self, tmp_path):
        """from_folder uses OBDFile pipeline — output has speed_kmh not speed_ms."""
        _write_xlsx(tmp_path / "trip.xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert "speed_ms" not in tc.trips[0]._df.columns
        assert "speed_kmh" in tc.trips[0]._df.columns

    def test_custom_config_applied(self, tmp_path):
        """ProcessingConfig.window is passed through to OBDFile.to_trip."""
        _write_xlsx(tmp_path / "trip.xlsx", n=30)
        tc4 = TripCollection.from_folder(tmp_path, config=ProcessingConfig(window=4))
        tc8 = TripCollection.from_folder(tmp_path, config=ProcessingConfig(window=8))
        # Both must produce valid trips; smooth speed widths will differ
        assert tc4.trips[0].mean_speed >= 0
        assert tc8.trips[0].mean_speed >= 0

    def test_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_folder(tmp_path / "ghost")

    def test_bad_file_skipped_with_warning(self, tmp_path, recwarn):
        """Unparseable xlsx files are skipped, not fatal."""
        good = tmp_path / "good.xlsx"
        bad = tmp_path / "bad.xlsx"
        _write_xlsx(good)
        bad.write_bytes(b"not an xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 1
        assert any("bad.xlsx" in str(w.message) for w in recwarn.list)


# ── from_folder_raw ───────────────────────────────────────────────────────────

class TestFromFolderRaw:
    def test_returns_list_of_obd_files(self, tmp_path):
        """from_folder_raw returns list[OBDFile], not a TripCollection."""
        _write_xlsx(tmp_path / "trip_a.xlsx")
        _write_xlsx(tmp_path / "trip_b.xlsx")
        result = TripCollection.from_folder_raw(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(f, OBDFile) for f in result)

    def test_no_processing_applied(self, tmp_path):
        """Raw files have original column names, not renamed English names."""
        _write_xlsx(tmp_path / "trip.xlsx")
        result = TripCollection.from_folder_raw(tmp_path)
        assert "Speed (OBD)(km/h)" in result[0]._df.columns

    def test_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_folder_raw(tmp_path / "ghost")


# ── from_archive_parquets ─────────────────────────────────────────────────────

class TestFromArchiveParquets:
    def test_loads_v2_parquets(self, tmp_path):
        """from_archive_parquets loads v2 archive Parquets into Trips."""
        _write_archive(tmp_path / "trip_a.parquet")
        _write_archive(tmp_path / "trip_b.parquet")
        tc = TripCollection.from_archive_parquets(tmp_path)
        assert len(tc) == 2

    def test_v1_parquet_skipped_with_warning(self, tmp_path):
        """from_archive_parquets warns+skips a v1 Parquet rather than aborting."""
        df = _make_raw_df()
        df["smooth_speed_kmh"] = 30.0  # v1 marker
        df.to_parquet(tmp_path / "v1.parquet", index=False)
        with pytest.warns(UserWarning, match="processed format"):
            tc = TripCollection.from_archive_parquets(tmp_path)
        assert len(tc) == 0

    def test_custom_config_applied(self, tmp_path):
        """ProcessingConfig is forwarded to OBDFile.to_trip."""
        _write_archive(tmp_path / "trip.parquet", n=30)
        tc = TripCollection.from_archive_parquets(
            tmp_path, config=ProcessingConfig(window=4)
        )
        assert "smooth_speed_kmh" in tc.trips[0]._df.columns

    def test_trip_path_set(self, tmp_path):
        """Each trip._path is set to its archive Parquet path."""
        p = tmp_path / "trip_a.parquet"
        _write_archive(p)
        tc = TripCollection.from_archive_parquets(tmp_path)
        assert tc.trips[0]._path == p

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_archive_parquets(tmp_path / "ghost")


# ── to_duckdb_catalog / from_duckdb_catalog ───────────────────────────────────

class TestDuckDBCatalog:
    def test_config_hash_written_to_catalog(self, tmp_path):
        """to_duckdb_catalog stores config_hash in trip_metadata."""
        import duckdb
        p = tmp_path / "trip.parquet"
        _write_archive(p)
        tc = TripCollection.from_archive_parquets(tmp_path)
        db = tmp_path / "catalog.db"
        config = ProcessingConfig(window=4)
        tc.to_duckdb_catalog(db, config=config)
        with duckdb.connect(str(db), read_only=True) as conn:
            rows = conn.execute("SELECT config_hash FROM trip_metadata").fetchall()
        assert rows[0][0] == config.config_hash

    def test_eager_load_via_catalog(self, tmp_path):
        """from_duckdb_catalog returns Trips with loaded DataFrames (eager)."""
        p = tmp_path / "trip.parquet"
        _write_archive(p, speed_kmh=45.0)
        tc = TripCollection.from_archive_parquets(tmp_path)
        db = tmp_path / "catalog.db"
        tc.to_duckdb_catalog(db)
        loaded_tc = TripCollection.from_duckdb_catalog(db)
        # Accessing metrics must not raise — data is loaded eagerly
        assert loaded_tc.trips[0].mean_speed >= 0

    def test_alter_table_migration_for_existing_catalog(self, tmp_path):
        """to_duckdb_catalog adds config_hash column to catalogs that lack it."""
        import duckdb
        db = tmp_path / "old_catalog.db"
        # Create a catalog without config_hash
        with duckdb.connect(str(db)) as conn:
            conn.execute("""
                CREATE TABLE trip_metadata (
                    trip_id VARCHAR PRIMARY KEY,
                    parquet_path VARCHAR NOT NULL,
                    start_time TIMESTAMP, end_time TIMESTAMP,
                    duration_s DOUBLE, avg_velocity_kmh DOUBLE,
                    max_velocity_kmh DOUBLE, avg_acceleration_ms2 DOUBLE,
                    avg_deceleration_ms2 DOUBLE, idle_time_pct DOUBLE,
                    stop_count INTEGER, estimated_fuel_liters DOUBLE,
                    wavelet_anomaly_count INTEGER, markov_matrix_uri VARCHAR,
                    pla_trajectory_uri VARCHAR
                )
            """)
        # Now call to_duckdb_catalog — should migrate silently
        p = tmp_path / "trip.parquet"
        _write_archive(p)
        tc = TripCollection.from_archive_parquets(tmp_path)
        tc.to_duckdb_catalog(db)
        with duckdb.connect(str(db), read_only=True) as conn:
            cols = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='trip_metadata'"
            ).fetchall()]
        assert "config_hash" in cols

    def test_stale_parquet_path_warns_at_load(self, tmp_path):
        """from_duckdb_catalog warns+skips trips whose archive Parquet is gone."""
        p = tmp_path / "trip.parquet"
        _write_archive(p)
        tc = TripCollection.from_archive_parquets(tmp_path)
        db = tmp_path / "catalog.db"
        tc.to_duckdb_catalog(db)
        p.unlink()  # delete archive after catalog is written
        with pytest.warns(UserWarning, match="cannot load"):
            loaded = TripCollection.from_duckdb_catalog(db)
        assert len(loaded) == 0


# ── similarity_scores / find_representative ───────────────────────────────────

class TestSimilarity:
    def _make_tc(self, speeds: list[float], tmp_path: Path) -> TripCollection:
        """Build a TripCollection from a list of constant speeds."""
        trips = []
        for i, spd in enumerate(speeds):
            p = tmp_path / f"trip_{i}.parquet"
            _write_archive(p, speed_kmh=spd, n=30)
            trips.append(OBDFile.from_parquet(p).to_trip())
        return TripCollection(trips)

    def test_similarity_scores_returns_dict(self, tmp_path):
        tc = self._make_tc([30.0, 40.0, 50.0], tmp_path)
        scores = tc.similarity_scores()
        assert isinstance(scores, dict)
        assert len(scores) == 3

    def test_find_representative_returns_trip(self, tmp_path):
        tc = self._make_tc([30.0, 40.0, 50.0], tmp_path)
        rep = tc.find_representative()
        assert isinstance(rep, Trip)

    def test_find_representative_middle_trip_wins(self, tmp_path):
        """The middle-speed trip should score highest (closest to fleet average)."""
        tc = self._make_tc([10.0, 30.0, 50.0], tmp_path)
        rep = tc.find_representative()
        assert rep.mean_speed == pytest.approx(tc.trips[1].mean_speed, rel=0.1)

    def test_empty_collection_raises(self):
        with pytest.raises(ValueError, match="empty"):
            TripCollection([]).similarity_scores()

    def test_find_representative_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            TripCollection([]).find_representative()


# ── Dunder ────────────────────────────────────────────────────────────────────

class TestDunder:
    def test_len(self):
        tc = TripCollection([Trip(pd.DataFrame(), "a"), Trip(pd.DataFrame(), "b")])
        assert len(tc) == 2

    def test_iter(self):
        trips = [Trip(pd.DataFrame(), "a"), Trip(pd.DataFrame(), "b")]
        tc = TripCollection(trips)
        assert list(tc) == trips

    def test_repr(self):
        tc = TripCollection([Trip(pd.DataFrame(), "a")])
        assert "1" in repr(tc)
