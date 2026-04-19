"""Tests for Trip and TripCollection classes, plus _computations helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.trip import Trip
from drive_cycle_calculator.trip_collection import TripCollection

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
            "Longitude": [a2_value] + [24.0] * (rows - 1),
            "Latitude": [a2_value] + [60.0] * (rows - 1),
            "Altitude": [a2_value] + [100.0] * (rows - 1),
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


class TestTripCollectionClass:
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
