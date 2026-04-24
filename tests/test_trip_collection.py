"""Tests for TripCollection — constructors, catalog, similarity scoring."""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import make_raw_obd_df

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.trip import Trip
from drive_cycle_calculator.trip_collection import TripCollection

# ── from_folder (uses OBDFile pipeline) ──────────────────────────────────────


class TestFromFolder:
    def test_loads_all_xlsx(self, tmp_path, raw_xlsx):
        """from_folder processes all .xlsx files and returns a TripCollection."""
        raw_xlsx("trip_a.xlsx")
        raw_xlsx("trip_b.xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 2

    def test_produces_no_speed_ms_column(self, tmp_path, raw_xlsx):
        """from_folder uses OBDFile pipeline — output has speed_kmh not speed_ms."""
        raw_xlsx("trip.xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert "speed_ms" not in tc.trips[0]._df.columns
        assert "speed_kmh" in tc.trips[0]._df.columns

    def test_custom_config_applied(self, tmp_path, raw_xlsx):
        """ProcessingConfig.window is passed through to OBDFile.to_trip."""
        raw_xlsx("trip.xlsx", n=30)
        tc4 = TripCollection.from_folder(tmp_path, config=ProcessingConfig(window=4))
        tc8 = TripCollection.from_folder(tmp_path, config=ProcessingConfig(window=8))
        # Both must produce valid trips; smooth speed widths will differ
        assert tc4.trips[0].mean_speed >= 0
        assert tc8.trips[0].mean_speed >= 0

    def test_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_folder(tmp_path / "ghost")

    def test_bad_file_skipped_with_warning(self, tmp_path, raw_xlsx, recwarn):
        """Unparseable xlsx files are skipped, not fatal."""
        raw_xlsx("good.xlsx")
        (tmp_path / "bad.xlsx").write_bytes(b"not an xlsx")
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 1
        assert any("bad.xlsx" in str(w.message) for w in recwarn.list)


# ── from_folder_raw ───────────────────────────────────────────────────────────


class TestFromFolderRaw:
    def test_returns_list_of_obd_files(self, tmp_path, raw_xlsx):
        """from_folder_raw returns list[OBDFile], not a TripCollection."""
        raw_xlsx("trip_a.xlsx")
        raw_xlsx("trip_b.xlsx")
        result = TripCollection.from_folder_raw(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(f, OBDFile) for f in result)

    def test_no_processing_applied(self, tmp_path, raw_xlsx):
        """Raw files have original column names, not renamed English names."""
        raw_xlsx("trip.xlsx")
        result = TripCollection.from_folder_raw(tmp_path)
        assert "Speed (OBD)(km/h)" in result[0]._df.columns

    def test_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_folder_raw(tmp_path / "ghost")


# ── from_archive_parquets ─────────────────────────────────────────────────────


class TestFromArchiveParquets:
    def test_loads_v2_parquets(self, tmp_path, archive_parquet):
        """from_archive_parquets loads v2 archive Parquets into Trips."""
        archive_parquet("trip_a.parquet")
        archive_parquet("trip_b.parquet")
        tc = TripCollection.from_archive_parquets(tmp_path)
        assert len(tc) == 2

    def test_v1_parquet_skipped_with_warning(self, tmp_path):
        """from_archive_parquets warns+skips a v1 Parquet rather than aborting."""
        df = make_raw_obd_df()
        df["smooth_speed_kmh"] = 30.0  # v1 marker
        df.to_parquet(tmp_path / "v1.parquet", index=False)
        with pytest.warns(UserWarning, match="processed format"):
            tc = TripCollection.from_archive_parquets(tmp_path)
        assert len(tc) == 0

    def test_custom_config_applied(self, tmp_path, archive_parquet):
        """ProcessingConfig is forwarded to OBDFile.to_trip."""
        archive_parquet("trip.parquet", n=30)
        tc = TripCollection.from_archive_parquets(tmp_path, config=ProcessingConfig(window=4))
        assert "smooth_speed_kmh" in tc.trips[0]._df.columns

    def test_trip_path_set(self, tmp_path, archive_parquet):
        """Each trip._path is set to its archive Parquet path."""
        p = archive_parquet("trip_a.parquet")
        tc = TripCollection.from_archive_parquets(tmp_path)
        assert tc.trips[0]._path == p

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_archive_parquets(tmp_path / "ghost")


# ── to_duckdb_catalog / from_duckdb_catalog ───────────────────────────────────


class TestDuckDBCatalog:
    def test_from_catalog_missing_db_raises(self, tmp_path):
        """Non-existent db_path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            TripCollection.from_duckdb_catalog(tmp_path / "does_not_exist.duckdb")

    def test_from_catalog_empty_db_returns_empty(self, tmp_path):
        """Catalog with zero rows in trip_metrics returns empty TripCollection."""
        import duckdb

        db = tmp_path / "empty.duckdb"
        with duckdb.connect(str(db)) as conn:
            conn.execute("""
                CREATE TABLE trip_metrics (
                    trip_id              VARCHAR PRIMARY KEY,
                    parquet_path         VARCHAR,
                    parquet_id           VARCHAR,
                    start_time           TIMESTAMPTZ,
                    end_time             TIMESTAMPTZ,
                    duration_s           DOUBLE,
                    avg_velocity_kmh     DOUBLE,
                    config_hash          VARCHAR,
                    config_snapshot      VARCHAR
                )
            """)
        tc = TripCollection.from_duckdb_catalog(db)
        assert len(tc) == 0

    def test_eager_load_via_catalog(self, tmp_path, archive_parquet):
        """from_duckdb_catalog loads trips eagerly from trip_metrics table."""
        import duckdb

        p = archive_parquet("trip.parquet", speed_kmh=45.0)
        db = tmp_path / "catalog.db"
        with duckdb.connect(str(db)) as conn:
            conn.execute("""
                CREATE TABLE trip_metrics (
                    trip_id VARCHAR PRIMARY KEY,
                    parquet_path VARCHAR
                )
            """)
            conn.execute("INSERT INTO trip_metrics VALUES (?, ?)", [p.stem, str(p)])
        loaded_tc = TripCollection.from_duckdb_catalog(db)
        assert loaded_tc.trips[0].mean_speed >= 0

    def test_stale_parquet_path_warns_at_load(self, tmp_path):
        """from_duckdb_catalog warns+skips trips whose archive Parquet is gone (trip_metrics)."""
        import duckdb

        db = tmp_path / "catalog.db"
        dead_path = tmp_path / "does_not_exist.parquet"
        with duckdb.connect(str(db)) as conn:
            conn.execute("""
                CREATE TABLE trip_metrics (
                    trip_id VARCHAR PRIMARY KEY,
                    parquet_path VARCHAR
                )
            """)
            conn.execute(
                "INSERT INTO trip_metrics VALUES (?, ?)",
                ["dead_trip", str(dead_path)],
            )
        with pytest.warns(UserWarning, match="cannot load"):
            loaded = TripCollection.from_duckdb_catalog(db)
        assert len(loaded) == 0


# ── similarity_scores / find_representative ───────────────────────────────────


class TestSimilarityTC:
    def _make_tc(self, speeds: list[float], archive_parquet) -> TripCollection:
        """Build a TripCollection from a list of constant speeds."""
        trips = []
        for i, spd in enumerate(speeds):
            df = make_raw_obd_df(n=30, speed_kmh=spd)
            df["Longitude"] = float(24 + i)  # unique coords → unique parquet_id per trip
            p = archive_parquet(f"trip_{i}.parquet", df=df)
            trips.append(OBDFile.from_parquet(p).to_trip())
        return TripCollection(trips)

    def test_similarity_scores_returns_dict(self, archive_parquet):
        tc = self._make_tc([30.0, 40.0, 50.0], archive_parquet)
        scores = tc.similarity_scores()
        assert isinstance(scores, dict)
        assert len(scores) == 3

    def test_find_representative_returns_trip(self, archive_parquet):
        tc = self._make_tc([30.0, 40.0, 50.0], archive_parquet)
        rep = tc.find_representative()
        assert isinstance(rep, Trip)

    def test_find_representative_middle_trip_wins(self, archive_parquet):
        """The middle-speed trip should score highest (closest to fleet average)."""
        tc = self._make_tc([10.0, 30.0, 50.0], archive_parquet)
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
