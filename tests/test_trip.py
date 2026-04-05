"""Tests for Trip and TripCollection classes, plus _computations helpers."""
from __future__ import annotations

import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.metrics import Trip, TripCollection
from drive_cycle_calculator.metrics._computations import (
    _infer_sheet_name,
    _process_raw_df,
)

# ────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ────────────────────────────────────────────────────────────────

_SEVEN_METRIC_KEYS = {"duration", "mean_speed", "mean_ns", "stops", "stop_pct", "mean_acc", "mean_dec"}


def _make_processed_df(
    n: int = 10,
    speed_ms: float = 5.0,
    smooth_col: str = "Εξομαλυνση",
) -> pd.DataFrame:
    """Minimal processed DataFrame matching the calculations-log format."""
    return pd.DataFrame({
        "Διάρκεια (sec)": list(range(n)),
        smooth_col: [speed_ms * 3.6] * n,
        "Ταχ m/s": [speed_ms] * n,
        "Επιταχυνση": [0.3] * n,
        "Επιβραδυνση": [-0.2] * n,
        "Engine Load(%)": [50.0] * n,
        "Fuel flow rate/hour(l/hr)": [2.0] * n,
        "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
    })


def _make_raw_df(
    n: int = 10,
    speed_kmh: float = 30.0,
    gps_start: float = 0.0,
    a2_value: str = "Mon Sep 22 10:30:00 +0300 2019",
) -> pd.DataFrame:
    """Minimal raw OBD DataFrame as read directly from an xlsx file."""
    rows = n + 2  # row 0 = header area, row 1 = A2 with timestamp, then data
    df = pd.DataFrame({
        "GPS Time": [a2_value] + [gps_start + i for i in range(rows - 1)],
        "Speed (OBD)(km/h)": [a2_value] + [speed_kmh] * (rows - 1),
        "CO\u2082 in g/km (Average)(g/km)": [a2_value] + [120.0] * (rows - 1),
        "Engine Load(%)": [a2_value] + [50.0] * (rows - 1),
        "Fuel flow rate/hour(l/hr)": [a2_value] + [2.0] * (rows - 1),
    })
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
        t = Trip(_make_processed_df(n=8, smooth_col="Εξομαλυνση"), "s")
        x, y = t.speed_profile
        assert len(x) == len(y)
        assert len(x) > 0

    def test_speed_profile_accent_variant(self):
        t = Trip(_make_processed_df(n=8, smooth_col="Εξομάλυνση"), "s")
        x, y = t.speed_profile
        assert len(x) == len(y)
        assert len(x) > 0

    def test_speed_profile_missing_column_raises(self):
        df = _make_processed_df()
        df = df.drop(columns=["Εξομαλυνση"])
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
    def test_from_excel_reads_all_sheets(self, tmp_path):
        xlsx = tmp_path / "log.xlsx"
        _write_processed_xlsx(xlsx, {
            "2025-05-14_Morning": _make_processed_df(),
            "2025-05-14_Evening": _make_processed_df(speed_ms=8.0),
        })
        tc = TripCollection.from_excel(xlsx)
        assert len(tc) == 2
        names = {t.name for t in tc}
        assert names == {"2025-05-14_Morning", "2025-05-14_Evening"}

    def test_from_excel_skips_empty_sheets(self, tmp_path):
        xlsx = tmp_path / "log.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
            _make_processed_df().to_excel(w, sheet_name="Good", index=False)
            pd.DataFrame().to_excel(w, sheet_name="Empty", index=False)
        tc = TripCollection.from_excel(xlsx)
        assert len(tc) == 1
        assert tc.trips[0].name == "Good"

    def test_from_excel_raises_on_zero_valid_sheets(self, tmp_path):
        xlsx = tmp_path / "log.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
            pd.DataFrame().to_excel(w, sheet_name="Empty", index=False)
        with pytest.raises(ValueError, match="No valid sheets"):
            TripCollection.from_excel(xlsx)

    def test_from_excel_file_not_found(self, tmp_path):
        with pytest.raises(Exception):
            TripCollection.from_excel(tmp_path / "does_not_exist.xlsx")

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
    "Διάρκεια (sec)",
    "Εξομαλυνση",
    "Ταχ m/s",
    "Επιταχυνση",
    "Επιβραδυνση",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
    "a(m/s2)",
}


class TestProcessRawDf:
    def _make_valid_raw(self, n: int = 15) -> pd.DataFrame:
        """Raw OBD DataFrame with all required columns."""
        return pd.DataFrame({
            "GPS Time": list(range(n)),
            "Speed (OBD)(km/h)": [30.0] * n,
            "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
        })

    def test_happy_path_returns_processed_columns(self):
        result = _process_raw_df(self._make_valid_raw())
        assert _EXPECTED_OUTPUT_COLS.issubset(set(result.columns))
        assert len(result) > 0

    @pytest.mark.parametrize("missing_col", _REQUIRED_COLS)
    def test_missing_required_column_raises_value_error(self, missing_col):
        df = self._make_valid_raw().drop(columns=[missing_col])
        with pytest.raises(ValueError, match="Missing required columns"):
            _process_raw_df(df)

    def test_output_has_duration_column(self):
        result = _process_raw_df(self._make_valid_raw())
        assert "Διάρκεια (sec)" in result.columns
        # first duration value should be 0 (elapsed from start)
        first = pd.to_numeric(result["Διάρκεια (sec)"], errors="coerce").dropna().iloc[0]
        assert first == pytest.approx(0.0)


# ────────────────────────────────────────────────────────────────
# TestInferSheetName
# ────────────────────────────────────────────────────────────────

class TestInferSheetName:
    def _make_df_with_a2(self, a2_value: str) -> pd.DataFrame:
        """DataFrame where iloc[1, 0] contains a2_value."""
        return pd.DataFrame({
            "col": ["header_row_0", a2_value, "data", "data"]
        })

    def test_valid_a2_timestamp_morning(self, tmp_path):
        """Valid A2 timestamp with hour < 12 → Morning."""
        df = self._make_df_with_a2("Mon Sep 22 10:30:00 +0300 2019")
        name = _infer_sheet_name(df, tmp_path / "f.xlsx")
        assert name == "2019-09-22_Morning"

    def test_valid_a2_timestamp_evening(self, tmp_path):
        """Valid A2 timestamp with hour >= 12 → Evening."""
        df = self._make_df_with_a2("Mon Sep 22 18:45:00 +0300 2019")
        name = _infer_sheet_name(df, tmp_path / "f.xlsx")
        assert name == "2019-09-22_Evening"

    def test_invalid_a2_falls_back_to_mtime(self, tmp_path):
        """Unparseable A2 falls back to file mtime, still returns YYYY-MM-DD_Session."""
        xlsx = tmp_path / "session.xlsx"
        xlsx.write_text("placeholder")
        df = self._make_df_with_a2("this is not a timestamp")
        name = _infer_sheet_name(df, xlsx)
        # Should be YYYY-MM-DD_Morning or YYYY-MM-DD_Evening
        parts = name.split("_")
        assert len(parts) == 2
        assert parts[1] in {"Morning", "Evening"}
        # Date should look like a date
        date_parts = parts[0].split("-")
        assert len(date_parts) == 3

    def test_result_within_excel_sheet_name_limit(self, tmp_path):
        """Sheet names must be ≤ 31 characters."""
        df = self._make_df_with_a2("Mon Sep 22 10:30:00 +0300 2019")
        name = _infer_sheet_name(df, tmp_path / "f.xlsx")
        assert len(name) <= 31
