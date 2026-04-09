"""Tests for Trip and TripCollection classes, plus _computations helpers."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.metrics import Trip, TripCollection, load_raw_df
from drive_cycle_calculator.metrics._computations import (
    process_raw_df,
)

# ────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ────────────────────────────────────────────────────────────────

_SEVEN_METRIC_KEYS = {
    "duration",
    "mean_speed",
    "mean_ns",
    "stops",
    "stop_pct",
    "mean_acc",
    "mean_dec",
}


def _make_processed_df(
    n: int = 10,
    speed_ms: float = 5.0,
    smooth_col: str = "smooth_speed_kmh",
) -> pd.DataFrame:
    """Minimal processed DataFrame matching the post-migration English column format."""
    return pd.DataFrame(
        {
            "elapsed_s": list(range(n)),
            smooth_col: [speed_ms * 3.6] * n,
            "speed_ms": [speed_ms] * n,
            "acceleration_ms2": [0.3] * n,
            "deceleration_ms2": [-0.2] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
            "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
        }
    )


def _make_raw_df(
    n: int = 10,
    speed_kmh: float = 30.0,
    gps_start: float = 0.0,
    a2_value: str = "Mon Sep 22 10:30:00 +0300 2019",
) -> pd.DataFrame:
    """Minimal raw OBD DataFrame as read directly from an xlsx file."""
    rows = n + 2  # row 0 = header area, row 1 = A2 with timestamp, then data
    df = pd.DataFrame(
        {
            "GPS Time": [a2_value] + [gps_start + i for i in range(rows - 1)],
            "Speed (OBD)(km/h)": [a2_value] + [speed_kmh] * (rows - 1),
            "CO\u2082 in g/km (Average)(g/km)": [a2_value] + [120.0] * (rows - 1),
            "Engine Load(%)": [a2_value] + [50.0] * (rows - 1),
            "Fuel flow rate/hour(l/hr)": [a2_value] + [2.0] * (rows - 1),
        }
    )
    return df


def _write_processed_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    """Write a multi-sheet xlsx in the combined log format."""
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)


def _write_raw_xlsx(path: Path, df: pd.DataFrame) -> None:
    """Write a raw OBD xlsx file."""
    df.to_excel(path, index=False)


# ────────────────────────────────────────────────────────────────
# TestTrip
# ────────────────────────────────────────────────────────────────


class TestTrip:
    def test_construction_from_dataframe(self):
        df = _make_processed_df()
        t = Trip(df, "2025-05-14_Morning")
        assert t.name == "2025-05-14_Morning"

    def test_date_and_session_from_name(self):
        t = Trip(_make_processed_df(), "2025-05-14_Morning")
        assert t.date == "2025-05-14"
        assert t.session == "Morning"

    def test_name_without_underscore(self):
        t = Trip(_make_processed_df(), "NoUnderscore")
        assert t.date == "NoUnderscore"
        assert t.session == "Unknown"

    def test_all_seven_metrics_available(self):
        t = Trip(_make_processed_df(), "s")
        assert set(t.metrics.keys()) == _SEVEN_METRIC_KEYS

    def test_mean_speed_cached_property(self):
        t = Trip(_make_processed_df(speed_ms=10.0), "s")
        first = t.mean_speed
        second = t.mean_speed
        assert first == second
        assert first == pytest.approx(10.0 * 3.6, abs=0.01)

    def test_speed_profile_returns_aligned_series(self):
        t = Trip(_make_processed_df(n=8), "s")
        x, y = t.speed_profile
        assert len(x) == len(y)
        assert len(x) > 0

    def test_speed_profile_missing_column_raises(self):
        df = _make_processed_df()
        df = df.drop(columns=["smooth_speed_kmh"])
        t = Trip(df, "s")
        with pytest.raises(RuntimeError, match="not found"):
            _ = t.speed_profile

    def test_microtrips_raises_not_implemented(self):
        t = Trip(_make_processed_df(), "s")
        with pytest.raises(NotImplementedError):
            _ = t.microtrips

    def test_repr(self):
        t = Trip(_make_processed_df(), "2025-05-14_Morning")
        assert "Trip(" in repr(t)
        assert "2025-05-14_Morning" in repr(t)


# ────────────────────────────────────────────────────────────────
# TestTripCollection
# ────────────────────────────────────────────────────────────────


class TestTripCollection:
    def test_from_folder_reads_raw_xlsx(self, tmp_path):
        raw_df = _make_raw_df()
        _write_raw_xlsx(tmp_path / "session.xlsx", raw_df)
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 1

    def test_from_folder_skips_bad_files_with_warning(self, tmp_path):
        # Valid file
        _write_raw_xlsx(tmp_path / "good.xlsx", _make_raw_df())
        # Corrupt file (not a valid xlsx)
        (tmp_path / "bad.xlsx").write_bytes(b"not a zip file")
        with pytest.warns(UserWarning, match="bad.xlsx"):
            tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 1

    def test_from_folder_empty_folder_returns_empty_collection(self, tmp_path):
        tc = TripCollection.from_folder(tmp_path)
        assert len(tc) == 0

    def test_from_folder_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TripCollection.from_folder(tmp_path / "nonexistent")

    def test_find_representative_returns_trip_instance(self):
        t1 = Trip(_make_processed_df(speed_ms=10.0), "a")
        t2 = Trip(_make_processed_df(speed_ms=12.0), "b")
        tc = TripCollection([t1, t2])
        rep = tc.find_representative()
        assert isinstance(rep, Trip)
        assert rep.name in {"a", "b"}

    def test_find_representative_single_trip(self):
        t = Trip(_make_processed_df(), "only")
        tc = TripCollection([t])
        rep = tc.find_representative()
        assert rep.name == "only"
        scores = tc.similarity_scores()
        assert scores["only"] == pytest.approx(100.0)

    def test_find_representative_raises_on_empty(self):
        with pytest.raises(ValueError, match="empty"):
            TripCollection([]).find_representative()

    def test_similarity_scores_range_0_to_100(self):
        trips = [
            Trip(_make_processed_df(speed_ms=s), f"trip_{i}")
            for i, s in enumerate([5.0, 10.0, 15.0])
        ]
        tc = TripCollection(trips)
        scores = tc.similarity_scores()
        assert set(scores.keys()) == {"trip_0", "trip_1", "trip_2"}
        for v in scores.values():
            assert 0.0 <= v <= 100.0

    def test_similarity_scores_raises_on_empty(self):
        with pytest.raises(ValueError, match="empty"):
            TripCollection([]).similarity_scores()

    def test_len_and_iter(self):
        trips = [Trip(_make_processed_df(), f"t{i}") for i in range(3)]
        tc = TripCollection(trips)
        assert len(tc) == 3
        assert list(tc) == trips


# ────────────────────────────────────────────────────────────────
# TestProcessRawDf
# ────────────────────────────────────────────────────────────────

_REQUIRED_COLS = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]

_EXPECTED_OUTPUT_COLS = {
    "elapsed_s",
    "smooth_speed_kmh",
    "speed_ms",
    "acceleration_ms2",
    "deceleration_ms2",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
    "a(m/s2)",
}


class TestProcessRawDf:
    def _make_valid_raw(self, n: int = 15) -> pd.DataFrame:
        """Raw OBD DataFrame with all required columns."""
        return pd.DataFrame(
            {
                "GPS Time": list(range(n)),
                "Speed (OBD)(km/h)": [30.0] * n,
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
            }
        )

    def test_happy_path_returns_processed_columns(self):
        result = process_raw_df(self._make_valid_raw())
        assert _EXPECTED_OUTPUT_COLS.issubset(set(result.columns))
        assert len(result) > 0

    @pytest.mark.parametrize("missing_col", _REQUIRED_COLS)
    def test_missing_required_column_raises_value_error(self, missing_col):
        df = self._make_valid_raw().drop(columns=[missing_col])
        with pytest.raises(ValueError, match="Missing required columns"):
            process_raw_df(df)

    def test_output_has_duration_column(self):
        result = process_raw_df(self._make_valid_raw())
        assert "elapsed_s" in result.columns
        # first duration value should be 0 (elapsed from start)
        first = pd.to_numeric(result["elapsed_s"], errors="coerce").dropna().iloc[0]
        assert first == pytest.approx(0.0)

    def test_dash_placeholders_coerced_to_float_not_object(self, tmp_path):
        """Torque '-' sensor-off markers must not produce object-dtype columns.

        Regression: pyarrow raises ArrowTypeError when a column has dtype=object
        with mixed str/float values. The three passthrough columns (CO2, Engine
        Load, Fuel flow) must be float64 after processing.
        """
        n = 5
        df_raw = pd.DataFrame(
            {
                "GPS Time": list(range(n)),
                "Speed (OBD)(km/h)": [30.0] * n,
                # Mix of '-' strings and real floats, exactly as Torque exports
                "CO\u2082 in g/km (Average)(g/km)": ["-", "-", 47.5, 53.6, "-"],
                "Engine Load(%)": ["-", 30.2, 31.8, 30.9, 31.4],
                "Fuel flow rate/hour(l/hr)": ["-", "-", 0.99, 0.79, "-"],
            }
        )
        result = process_raw_df(df_raw)

        for col in [
            "CO\u2082 in g/km (Average)(g/km)",
            "Engine Load(%)",
            "Fuel flow rate/hour(l/hr)",
        ]:
            assert result[col].dtype == float, (
                f"Column {col!r} should be float64, got {result[col].dtype}. "
                "Torque '-' markers must be coerced to NaN at ingest."
            )

        # Verify parquet write succeeds (the original failure point)
        path = tmp_path / "trip.parquet"
        result.to_parquet(path, index=True)
        assert path.exists()


# ────────────────────────────────────────────────────────────────
# TestLoadRawDf
# ────────────────────────────────────────────────────────────────


class TestLoadRawDf:
    def test_missing_file_raises_file_not_found(self, tmp_path):
        """load_raw_df raises FileNotFoundError for a non-existent path."""
        with pytest.raises(FileNotFoundError):
            load_raw_df(tmp_path / "does_not_exist.xlsx")

    def test_non_xlsx_file_raises_exception(self, tmp_path):
        """load_raw_df raises an exception when the file is not a valid xlsx."""
        bad = tmp_path / "not_excel.xlsx"
        bad.write_text("this is not excel content")
        with pytest.raises(Exception):
            load_raw_df(bad)

    def test_directory_raises_file_not_found(self, tmp_path):
        """load_raw_df raises FileNotFoundError when path is a directory."""
        with pytest.raises(FileNotFoundError):
            load_raw_df(tmp_path)





# ────────────────────────────────────────────────────────────────
# TestTripMaxSpeed
# ────────────────────────────────────────────────────────────────


class TestTripMaxSpeed:
    def test_returns_max_speed_in_kmh(self):
        df = _make_processed_df(speed_ms=10.0, n=5)
        t = Trip(df, "s")
        assert t.max_speed == pytest.approx(10.0 * 3.6, abs=0.01)

    def test_returns_nan_when_speed_ms_absent(self):
        df = pd.DataFrame({"elapsed_s": [0, 1, 2]})
        t = Trip(df, "s")
        assert np.isnan(t.max_speed)

    def test_cached(self):
        t = Trip(_make_processed_df(speed_ms=5.0), "s")
        assert t.max_speed is t.max_speed  # same object from cache


# ────────────────────────────────────────────────────────────────
# TestTripLazyLoading
# ────────────────────────────────────────────────────────────────


class TestTripLazyLoading:
    def test_df_none_with_path_loads_on_first_access(self, tmp_path):
        """Trip(df=None) + _path → lazy load on first .metrics access."""
        df = _make_processed_df(speed_ms=8.0)
        parquet = tmp_path / "session.parquet"
        df.to_parquet(parquet)

        t = Trip(df=None, name="session")
        t._path = parquet
        # Access metrics → triggers load
        assert t.mean_speed == pytest.approx(8.0 * 3.6, abs=0.01)

    def test_df_loaded_once_and_cached(self, tmp_path):
        """Second .metrics access does not re-read the file."""
        df = _make_processed_df()
        parquet = tmp_path / "s.parquet"
        df.to_parquet(parquet)

        t = Trip(df=None, name="s")
        t._path = parquet
        _ = t.metrics  # triggers load
        # Internal __df should now be set; rename the file to prove no re-read
        parquet.rename(tmp_path / "renamed.parquet")
        _ = t.mean_speed  # should not raise even though file is gone

    def test_df_none_path_none_raises_runtime_error(self):
        """Trip(df=None) with no _path raises RuntimeError on access."""
        t = Trip(df=None, name="orphan")
        with pytest.raises(RuntimeError, match="no DataFrame"):
            _ = t.metrics

    def test_df_none_missing_file_raises_file_not_found(self, tmp_path):
        """Trip(df=None) with missing parquet raises FileNotFoundError."""
        t = Trip(df=None, name="gone")
        t._path = tmp_path / "does_not_exist.parquet"
        with pytest.raises(FileNotFoundError):
            _ = t.metrics


# ────────────────────────────────────────────────────────────────
# TestTripCollectionParquet
# ────────────────────────────────────────────────────────────────


class TestTripCollectionParquet:
    def test_roundtrip(self, tmp_path):
        """to_parquet → from_parquet produces same trips."""
        t1 = Trip(_make_processed_df(speed_ms=5.0), "morning")
        t2 = Trip(_make_processed_df(speed_ms=8.0), "evening")
        tc = TripCollection([t1, t2])
        tc.to_parquet(tmp_path)

        loaded = TripCollection.from_parquet(tmp_path)
        assert len(loaded) == 2
        names = {t.name for t in loaded}
        assert names == {"morning", "evening"}

    def test_roundtrip_metrics_preserved(self, tmp_path):
        """Metrics computed from loaded parquet match original."""
        t = Trip(_make_processed_df(speed_ms=10.0), "trip")
        TripCollection([t]).to_parquet(tmp_path)
        loaded = TripCollection.from_parquet(tmp_path)
        assert loaded.trips[0].mean_speed == pytest.approx(10.0 * 3.6, abs=0.01)

    def test_overwrite_by_default(self, tmp_path):
        """Re-running to_parquet() overwrites existing files without error."""
        t = Trip(_make_processed_df(speed_ms=5.0), "trip")
        tc = TripCollection([t])
        tc.to_parquet(tmp_path)  # first write
        tc.to_parquet(tmp_path)  # second write — should not raise

    def test_overwrite_false_raises_on_existing(self, tmp_path):
        """overwrite=False raises ValueError if file already exists."""
        t = Trip(_make_processed_df(), "trip")
        tc = TripCollection([t])
        tc.to_parquet(tmp_path)
        with pytest.raises(ValueError, match="already exists"):
            tc.to_parquet(tmp_path, overwrite=False)

    def test_empty_collection_writes_no_files(self, tmp_path):
        """Empty TripCollection writes nothing."""
        TripCollection([]).to_parquet(tmp_path)
        assert list(tmp_path.glob("*.parquet")) == []

    def test_name_collision_within_collection_raises(self, tmp_path):
        """Two trips with same sanitised name raise ValueError before any write."""
        t1 = Trip(_make_processed_df(), "a/b")
        t2 = Trip(_make_processed_df(), "a b")  # both sanitise to "a_b"
        tc = TripCollection([t1, t2])
        with pytest.raises(ValueError, match="collision"):
            tc.to_parquet(tmp_path)
        assert list(tmp_path.glob("*.parquet")) == []  # no partial writes

    def test_special_chars_in_name_sanitised(self, tmp_path):
        """Trip names with special chars produce valid filenames."""
        t = Trip(_make_processed_df(), "2025-05-14 Morning (test)")
        TripCollection([t]).to_parquet(tmp_path)
        files = list(tmp_path.glob("*.parquet"))
        assert len(files) == 1
        assert " " not in files[0].name

    def test_from_parquet_empty_directory(self, tmp_path):
        """Empty directory returns empty TripCollection."""
        tc = TripCollection.from_parquet(tmp_path)
        assert len(tc) == 0

    def test_from_parquet_missing_directory(self, tmp_path):
        """Non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            TripCollection.from_parquet(tmp_path / "nonexistent")

    def test_to_parquet_missing_directory(self, tmp_path):
        """Non-existent directory raises FileNotFoundError."""
        t = Trip(_make_processed_df(), "trip")
        with pytest.raises(FileNotFoundError):
            TripCollection([t]).to_parquet(tmp_path / "nonexistent")

    def test_to_parquet_sets_path_on_trips(self, tmp_path):
        """to_parquet() sets trip._path so to_duckdb_catalog() can find files."""
        t = Trip(_make_processed_df(), "trip")
        tc = TripCollection([t])
        tc.to_parquet(tmp_path)
        assert t._path is not None
        assert t._path.exists()


# ────────────────────────────────────────────────────────────────
# TestTripCollectionDuckDB
# ────────────────────────────────────────────────────────────────


def _make_archive_df(n: int = 10, speed_kmh: float = 30.0) -> pd.DataFrame:
    """Minimal raw OBD DataFrame suitable for OBDFile.to_parquet() (v2 archive).

    GPS Time is a proper timestamp string column — unlike _make_raw_df which
    mixes a string in row 0 with floats. PyArrow requires a uniform column type.
    """
    timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
    return pd.DataFrame(
        {
            "GPS Time": timestamps,
            "Speed (OBD)(km/h)": [speed_kmh] * n,
            "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
        }
    )


def _write_archive_parquet(tmp_path: Path, name: str, speed_kmh: float = 30.0) -> Path:
    """Write a v2 archive Parquet using OBDFile and return its path."""
    from drive_cycle_calculator.obd_file import OBDFile

    raw_df = _make_archive_df(speed_kmh=speed_kmh)
    obd = OBDFile(raw_df, name)
    dest = tmp_path / f"{name}.parquet"
    obd.to_parquet(dest)
    return dest


class TestTripCollectionDuckDB:
    def test_roundtrip(self, tmp_path):
        """to_duckdb_catalog → from_duckdb_catalog loads trips via OBDFile archives."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        _write_archive_parquet(archive_dir, "trip", speed_kmh=36.0)
        db = tmp_path / "metadata.duckdb"
        tc = TripCollection.from_archive_parquets(archive_dir)
        tc.to_duckdb_catalog(db)

        loaded = TripCollection.from_duckdb_catalog(db)
        assert len(loaded) == 1
        assert loaded.trips[0].name == "trip"

    def test_eager_load_via_catalog(self, tmp_path):
        """Trips loaded from catalog are eagerly loaded (not lazy)."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        _write_archive_parquet(archive_dir, "session", speed_kmh=36.0)
        db = tmp_path / "metadata.duckdb"
        tc = TripCollection.from_archive_parquets(archive_dir)
        tc.to_duckdb_catalog(db)

        loaded = TripCollection.from_duckdb_catalog(db)
        trip = loaded.trips[0]
        # Trips are eagerly loaded — _df is populated immediately
        assert trip._Trip__df is not None
        assert trip.mean_speed > 0.0

    def test_upsert_idempotency(self, tmp_path):
        """Calling to_duckdb_catalog() twice produces no duplicate rows."""
        import duckdb

        t = Trip(_make_processed_df(), "trip")
        tc = TripCollection([t])
        trips_dir = tmp_path / "trips"
        trips_dir.mkdir()
        tc.to_parquet(trips_dir)
        db = tmp_path / "metadata.duckdb"
        tc.to_duckdb_catalog(db)
        tc.to_duckdb_catalog(db)  # second call

        with duckdb.connect(str(db), read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM trip_metadata").fetchone()[0]
        assert count == 1  # not 2

    def test_empty_collection_no_op(self, tmp_path):
        """Empty TripCollection does not truncate an existing catalog."""
        import duckdb

        t = Trip(_make_processed_df(), "existing")
        tc = TripCollection([t])
        trips_dir = tmp_path / "trips"
        trips_dir.mkdir()
        tc.to_parquet(trips_dir)
        db = tmp_path / "metadata.duckdb"
        tc.to_duckdb_catalog(db)

        TripCollection([]).to_duckdb_catalog(db)  # empty — should not truncate

        with duckdb.connect(str(db), read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM trip_metadata").fetchone()[0]
        assert count == 1

    def test_from_catalog_missing_db_raises(self, tmp_path):
        """Non-existent db_path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            TripCollection.from_duckdb_catalog(tmp_path / "does_not_exist.duckdb")

    def test_from_catalog_empty_db_returns_empty(self, tmp_path):
        """Catalog with zero rows returns empty TripCollection."""
        import duckdb

        db = tmp_path / "empty.duckdb"
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
        tc = TripCollection.from_duckdb_catalog(db)
        assert len(tc) == 0

    def test_stale_parquet_path_warns_at_load(self, tmp_path):
        """from_duckdb_catalog warns+skips when the archive parquet is gone.

        Eager loading means the warning surfaces in from_duckdb_catalog(), not lazily
        on first metrics access. The collection is returned with zero trips.
        """
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        archive_path = _write_archive_parquet(archive_dir, "trip")
        db = tmp_path / "metadata.duckdb"
        tc = TripCollection.from_archive_parquets(archive_dir)
        tc.to_duckdb_catalog(db)

        # Delete the archive to simulate stale catalog entry
        archive_path.unlink()

        with pytest.warns(UserWarning, match="cannot load"):
            loaded = TripCollection.from_duckdb_catalog(db)
        assert len(loaded) == 0

    def test_max_velocity_populated(self, tmp_path):
        """max_velocity_kmh is stored (not NULL) for trips with speed_ms column."""
        import duckdb

        t = Trip(_make_processed_df(speed_ms=10.0), "trip")
        tc = TripCollection([t])
        trips_dir = tmp_path / "trips"
        trips_dir.mkdir()
        tc.to_parquet(trips_dir)
        db = tmp_path / "metadata.duckdb"
        tc.to_duckdb_catalog(db)

        with duckdb.connect(str(db), read_only=True) as conn:
            row = conn.execute(
                "SELECT max_velocity_kmh FROM trip_metadata WHERE trip_id = 'trip'"
            ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(10.0 * 3.6, abs=0.01)
