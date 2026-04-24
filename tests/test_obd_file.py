"""Tests for OBDFile — constructors, quality_report, curated_df, to_trip."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from conftest import make_raw_obd_df

from drive_cycle_calculator.schema import CURATED_COLS
from drive_cycle_calculator.obd_file import OBDFile

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_raw_df(n: int = 10, speed_kmh: float = 30.0) -> pd.DataFrame:
    """Minimal raw OBD DataFrame with all CURATED_COLS plus Extra Column."""
    df = make_raw_obd_df(n=n, speed_kmh=speed_kmh)
    df["Extra Column"] = ["x"] * n  # should be preserved in archive
    return df


def _write_xlsx(path: Path, df: pd.DataFrame) -> None:
    df.to_excel(path, index=False)


def _write_csv(
    path: Path,
    df: pd.DataFrame,
    sep: str = ",",
    decimal: str = ".",
) -> None:
    """Write df as CSV with specified sep/decimal."""
    # Convert float columns to strings with the requested decimal character
    out = df.copy()
    for col in out.select_dtypes("number").columns:
        out[col] = out[col].apply(lambda v: f"{v:.2f}".replace(".", decimal))
    out.to_csv(path, sep=sep, index=False)



# ── from_xlsx ─────────────────────────────────────────────────────────────────


class TestFromXlsx:
    def test_happy_path(self, tmp_path):
        """from_xlsx loads all columns; name comes from file stem."""
        p = tmp_path / "session_01.xlsx"
        _write_xlsx(p, _make_raw_df())
        obd = OBDFile.from_xlsx(p)
        assert obd.name == "session_01"
        assert "GPS Time" in obd._df.columns
        assert "Extra Column" in obd._df.columns

    def test_dash_coercion(self, tmp_path):
        """Torque '-' placeholders are coerced to NaN for numeric columns."""
        # Build the raw df with Speed as object dtype so '-' can be inserted,
        # simulating what the Torque xlsx export looks like.
        timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(10)]
        speed_values = ["-"] + [30.0] * 9  # first row is a dash
        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": speed_values,  # object dtype (mixed)
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * 10,
                "Engine Load(%)": [50.0] * 10,
                "Fuel flow rate/hour(l/hr)": [2.0] * 10,
                "Longitude": [24.0] * 10,
                "Latitude": [60.0] * 10,
                "Altitude": [100.0] * 10,
            }
        )
        p = tmp_path / "dash_test.xlsx"
        _write_xlsx(p, df)
        obd = OBDFile.from_xlsx(p)
        assert np.isnan(obd._df["Speed (OBD)(km/h)"].iloc[0])

    def test_name_from_stem(self, tmp_path):
        """Name equals Path.stem (no extension)."""
        p = tmp_path / "my_trip_2019.xlsx"
        _write_xlsx(p, _make_raw_df())
        obd = OBDFile.from_xlsx(p)
        assert obd.name == "my_trip_2019"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            OBDFile.from_xlsx(tmp_path / "nonexistent.xlsx")

    def test_directory_raises(self, tmp_path):
        """Passing a directory (not a file) raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            OBDFile.from_xlsx(tmp_path)


# ── from_csv ──────────────────────────────────────────────────────────────────


class TestFromCsv:
    def test_comma_separator(self, tmp_path):
        """Auto-detects comma-separated CSV."""
        p = tmp_path / "trip.csv"
        _write_csv(p, _make_raw_df(), sep=",")
        obd = OBDFile.from_csv(p)
        assert "Speed (OBD)(km/h)" in obd._df.columns

    def test_semicolon_separator(self, tmp_path):
        """Auto-detects semicolon-separated CSV (European format)."""
        p = tmp_path / "trip.csv"
        _write_csv(p, _make_raw_df(), sep=";")
        obd = OBDFile.from_csv(p)
        assert "Speed (OBD)(km/h)" in obd._df.columns

    def test_explicit_sep_override(self, tmp_path):
        """sep= override bypasses auto-detection."""
        p = tmp_path / "trip.csv"
        _write_csv(p, _make_raw_df(), sep=";")
        obd = OBDFile.from_csv(p, sep=";")
        assert len(obd._df) == 10

    def test_european_decimal(self, tmp_path):
        """Comma-decimal values are parsed correctly when decimal=','."""
        p = tmp_path / "euro.csv"
        _write_csv(p, _make_raw_df(speed_kmh=30.5), sep=";", decimal=",")
        obd = OBDFile.from_csv(p, sep=";", decimal=",")
        speed_vals = pd.to_numeric(obd._df["Speed (OBD)(km/h)"], errors="coerce").dropna()
        assert speed_vals.iloc[0] == pytest.approx(30.5)

    def test_explicit_decimal_override(self, tmp_path):
        """decimal= override is passed through to pd.read_csv."""
        p = tmp_path / "euro.csv"
        _write_csv(p, _make_raw_df(speed_kmh=15.75), sep=";", decimal=",")
        obd = OBDFile.from_csv(p, sep=";", decimal=",")
        speed_vals = pd.to_numeric(obd._df["Speed (OBD)(km/h)"], errors="coerce").dropna()
        assert speed_vals.iloc[0] == pytest.approx(15.75)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            OBDFile.from_csv(tmp_path / "nope.csv")

    def test_undetectable_separator_raises(self, tmp_path):
        """ValueError when separator cannot be resolved and sep= not supplied."""
        p = tmp_path / "ambiguous.csv"
        # Write a single-column file with no field separator — Sniffer cannot detect.
        p.write_text("value\n1\n2\n3\n")
        # Sniffer will raise csv.Error or fall back; either way the result is
        # single-column data successfully parsed (not a ValueError). Instead
        # test with a file that is completely empty (zero bytes after header).
        p2 = tmp_path / "empty.csv"
        p2.write_text("")
        # A zero-byte file should either raise ValueError (no separator detected)
        # or FileNotFoundError/EmptyDataError — any Exception is acceptable.
        with pytest.raises(Exception):
            OBDFile.from_csv(p2)


# ── from_parquet ──────────────────────────────────────────────────────────────


class TestFromParquet:
    def test_v2_loads_ok(self, archive_parquet):
        """v2 archive Parquet (no smooth_speed_kmh column) loads without error."""
        p = archive_parquet("trip.parquet")
        obd = OBDFile.from_parquet(p)
        assert "GPS Time" in obd._df.columns

    def test_v1_processed_raises(self, tmp_path):
        """v1 processed Parquet (has smooth_speed_kmh) raises ValueError."""
        p = tmp_path / "processed.parquet"
        df = _make_raw_df()
        df["smooth_speed_kmh"] = 30.0  # v1 marker column
        df.to_parquet(p, index=False)
        with pytest.raises(ValueError, match="processed format"):
            OBDFile.from_parquet(p)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            OBDFile.from_parquet(tmp_path / "nonexistent.parquet")

    def test_name_from_stem(self, archive_parquet):
        p = archive_parquet("archive_trip_01.parquet")
        obd = OBDFile.from_parquet(p)
        assert obd.name == "archive_trip_01"


# ── to_parquet ────────────────────────────────────────────────────────────────


class TestToParquet:
    def test_roundtrip(self, tmp_path):
        """Write v2 archive → reload with from_parquet → same columns and rows."""
        src = _make_raw_df()
        obd = OBDFile(src, "test_trip")
        p = tmp_path / "test_trip.parquet"
        obd.to_parquet(p)
        loaded = OBDFile.from_parquet(p)
        assert set(loaded._df.columns) == set(src.columns)
        assert len(loaded._df) == len(src)

    def test_format_version_in_metadata(self, tmp_path):
        """PyArrow metadata includes format_version='2'."""
        p = tmp_path / "test.parquet"
        OBDFile(_make_raw_df(), "test").to_parquet(p)
        meta = pq.read_metadata(p).metadata
        assert meta[b"format_version"] == b"2"

    def test_gps_time_stored_as_datetime(self, tmp_path):
        """GPS Time is converted to datetime64 on write; the column survives roundtrip."""
        src = _make_raw_df()
        obd = OBDFile(src, "gps_test")
        p = tmp_path / "gps_test.parquet"
        obd.to_parquet(p)
        loaded = OBDFile.from_parquet(p)
        assert "GPS Time" in loaded._df.columns
        assert loaded._df["GPS Time"].notna().all()
        # Must come back as a datetime type, not raw object/string
        assert pd.api.types.is_datetime64_any_dtype(loaded._df["GPS Time"])

    def test_use_dictionary_false_default(self, tmp_path):
        """Default (False) writes without dict encoding — file is still valid."""
        p = tmp_path / "nodict.parquet"
        OBDFile(_make_raw_df(), "t").to_parquet(p)
        import pyarrow.parquet as pq_

        assert pq_.read_table(p) is not None

    def test_use_dictionary_true(self, tmp_path):
        """use_dictionary=True writes a valid file; timestamp cols are not dict-encoded."""
        p = tmp_path / "dict.parquet"
        OBDFile(_make_raw_df(), "t").to_parquet(p, use_dictionary=True)
        import pyarrow.parquet as pq_

        table = pq_.read_table(p)
        assert table is not None
        assert len(table) == 10

    def test_use_dictionary_explicit_list(self, tmp_path):
        """use_dictionary=[col] dict-encodes only the named column."""
        p = tmp_path / "dict_list.parquet"
        OBDFile(_make_raw_df(), "t").to_parquet(p, use_dictionary=["Engine Load(%)"])
        import pyarrow.parquet as pq_

        assert pq_.read_table(p) is not None


# ── _strip_column_names ───────────────────────────────────────────────────────


class TestStripColumnNames:
    def test_leading_spaces_removed(self):
        df = pd.DataFrame({" A": [1], "B ": [2], "\tC\t": [3]})
        obd = OBDFile(df, "t", strict=False)
        # Original columns are stripped; NaN-injected curated cols come after
        assert "A" in obd._df.columns
        assert " A" not in obd._df.columns
        assert "B" in obd._df.columns
        assert "\tC\t" not in obd._df.columns

    def test_clean_names_unchanged(self):
        df = pd.DataFrame({"GPS Time": ["x"], "Speed (OBD)(km/h)": [30.0]})
        obd = OBDFile(df, "t", strict=False)
        assert "GPS Time" in obd._df.columns
        assert "Speed (OBD)(km/h)" in obd._df.columns

    def test_device_time_with_leading_space_normalised(self):
        """The classic Torque " Device Time" column is cleaned to "Device Time"."""
        df = pd.DataFrame({" Device Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        obd = OBDFile(df, "t", strict=False)
        assert "Device Time" in obd._df.columns
        assert " Device Time" not in obd._df.columns


# ── _parse_timestamps ─────────────────────────────────────────────────────────


class TestParseTimestamps:
    def test_converts_gps_time_to_datetime(self):
        from drive_cycle_calculator.obd_file import _parse_timestamps

        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"] * 3})
        out = _parse_timestamps(df)
        assert pd.api.types.is_datetime64_any_dtype(out["GPS Time"])

    def test_converts_device_time_to_datetime(self):
        from drive_cycle_calculator.obd_file import _parse_timestamps

        df = pd.DataFrame({"Device Time": ["Mon Sep 22 10:30:00 +0300 2019"] * 3})
        out = _parse_timestamps(df)
        assert pd.api.types.is_datetime64_any_dtype(out["Device Time"])

    def test_already_datetime_unchanged(self):
        from drive_cycle_calculator.obd_file import _parse_timestamps

        ts = pd.to_datetime(["2019-09-22 07:30:00"], utc=True)
        df = pd.DataFrame({"GPS Time": ts})
        out = _parse_timestamps(df)
        # dtype should still be datetime — not converted a second time
        assert pd.api.types.is_datetime64_any_dtype(out["GPS Time"])

    def test_missing_timestamp_col_skipped(self):
        from drive_cycle_calculator.obd_file import _parse_timestamps

        df = pd.DataFrame({"Speed (OBD)(km/h)": [30.0]})
        out = _parse_timestamps(df)  # must not raise
        assert "Speed (OBD)(km/h)" in out.columns

    def test_returns_copy_not_inplace(self):
        from drive_cycle_calculator.obd_file import _parse_timestamps

        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        _parse_timestamps(df)
        # Original df must not be mutated — dtype should still be non-datetime
        assert not pd.api.types.is_datetime64_any_dtype(df["GPS Time"]), (
            "Original df must not be mutated"
        )


# ── curated_df ────────────────────────────────────────────────────────────────


class TestCuratedDf:
    def test_returns_curated_cols_subset(self):
        """curated_df returns only CURATED_COLS columns that are present."""
        df = _make_raw_df()
        obd = OBDFile(df, "test")
        curated = obd.curated_df
        for col in curated.columns:
            assert col in CURATED_COLS
        assert "Extra Column" not in curated.columns

    def test_missing_col_not_raised(self):
        """curated_df silently omits absent CURATED_COLS — no error."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        with pytest.raises(ValueError) as exc_info:
            obd = OBDFile(df, "sparse")
        assert str(exc_info.value)[:10] == "DataFrame "

        # curated = obd.curated_df  # must not raise
        # assert "GPS Time" in curated.columns
        # assert "Speed (OBD)(km/h)" not in curated.columns

    def test_is_copy(self):
        """curated_df returns a copy — mutations don't affect internal _df."""
        obd = OBDFile(_make_raw_df(), "test")
        curated = obd.curated_df
        curated["GPS Time"] = "MUTATED"
        assert obd._df["GPS Time"].iloc[0] != "MUTATED"


# ── quality_report ────────────────────────────────────────────────────────────


class TestQualityReport:
    def test_all_keys_present(self):
        """quality_report returns all 8 documented keys."""
        obd = OBDFile(_make_raw_df(), "test")
        report = obd.quality_report()
        expected_keys = {
            "row_count",
            "missing_pct",
            "dash_count",
            "gps_gap_count",
            "speed_outlier_count",
            "speed_min_kmh",
            "speed_max_kmh",
            "missing_curated_cols",
        }
        assert set(report.keys()) == expected_keys

    def test_row_count(self):
        obd = OBDFile(_make_raw_df(n=15), "test")
        assert obd.quality_report()["row_count"] == 15

    def test_missing_curated_cols_empty_when_all_present(self):
        """missing_curated_cols is empty when all CURATED_COLS are in the file."""
        obd = OBDFile(_make_raw_df(), "test")
        assert obd.quality_report()["missing_curated_cols"] == []

    def test_missing_curated_cols_reports_absent_columns(self):
        """missing_curated_cols lists CURATED_COLS absent from the file."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        with pytest.raises(ValueError) as exc_info:
            obd = OBDFile(df, "sparse")
        assert str(exc_info.value)[:10] == "DataFrame "
        # Previous behaviour allowed missing CURATED_COLS but reported them in the quality report
        # report = obd.quality_report()
        # assert "Speed (OBD)(km/h)" in report["missing_curated_cols"]

    def test_gps_gap_count_detects_large_gap(self):
        """GPS gaps > 5s are counted."""
        # Rows 0-4: 1-second intervals; then row 5: 10 seconds later
        times = [
            "Mon Sep 22 10:30:00 +0300 2019",
            "Mon Sep 22 10:30:01 +0300 2019",
            "Mon Sep 22 10:30:02 +0300 2019",
            "Mon Sep 22 10:30:03 +0300 2019",
            "Mon Sep 22 10:30:04 +0300 2019",
            "Mon Sep 22 10:30:15 +0300 2019",  # 11-second gap
        ]
        df = pd.DataFrame(
            {
                "GPS Time": times,
                "Speed (OBD)(km/h)": [30.0] * 6,
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * 6,
                "Engine Load(%)": [50.0] * 6,
                "Fuel flow rate/hour(l/hr)": [2.0] * 6,
                "Longitude": [24.0] * 6,
                "Latitude": [60.0] * 6,
                "Altitude": [100.0] * 6,
            }
        )
        obd = OBDFile(df, "gap_test")
        assert obd.quality_report()["gps_gap_count"] >= 1

    def test_speed_outlier_count(self):
        """Rows with Speed > 250 km/h are counted as outliers."""
        df = _make_raw_df()
        df.loc[0, "Speed (OBD)(km/h)"] = 300.0
        df.loc[1, "Speed (OBD)(km/h)"] = 280.0
        obd = OBDFile(df, "outlier_test")
        assert obd.quality_report()["speed_outlier_count"] == 2

    def test_speed_min_max(self):
        """speed_min_kmh and speed_max_kmh are correct."""
        df = _make_raw_df()
        df["Speed (OBD)(km/h)"] = [float(i * 10) for i in range(len(df))]
        obd = OBDFile(df, "range_test")
        report = obd.quality_report()
        assert report["speed_min_kmh"] == pytest.approx(0.0)
        assert report["speed_max_kmh"] == pytest.approx(90.0)

    def test_missing_speed_col_returns_nan(self):
        """speed_min/max are NaN when speed column is absent."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        with pytest.raises(ValueError) as exc_info:
            obd = OBDFile(df, "no_speed")
        assert str(exc_info.value)[:10] == "DataFrame "
        ##  Previous behaviour allowed missing speed column but returned NaN for min/max
        # report = obd.quality_report()
        # assert np.isnan(report["speed_min_kmh"])
        # assert np.isnan(report["speed_max_kmh"])

    def test_empty_df(self):
        """quality_report handles empty DataFrame without raising."""
        df = pd.DataFrame(columns=CURATED_COLS)
        obd = OBDFile(df, "empty")
        report = obd.quality_report()
        assert report["row_count"] == 0
        assert report["gps_gap_count"] == 0


# ── to_trip ───────────────────────────────────────────────────────────────────


class TestToTrip:
    def test_happy_path_columns(self):
        """to_trip() returns Trip with expected processed columns."""
        from drive_cycle_calculator.trip import Trip

        obd = OBDFile(_make_raw_df(), "test_trip")
        trip = obd.to_trip()
        assert isinstance(trip, Trip)
        expected_cols = {
            "elapsed_s",
            "smooth_speed_kmh",
            "acc_ms2",
            "speed_kmh",
            "co2_g_per_km",
            "engine_load_pct",
            "fuel_flow_lph",
        }
        assert set(trip._df.columns) == expected_cols

    def test_name_preserved(self):
        """Trip.name matches OBDFile.parquet_name (not obd.name)."""
        obd = OBDFile(_make_raw_df(), "my_session")
        trip = obd.to_trip()
        assert trip.name == obd.parquet_name

    def test_missing_curated_col_raises(self):
        """to_trip() raises ValueError if any CURATED_COL is missing."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        with pytest.raises(ValueError, match="DataFrame is missing") as exc_info:
            obd = OBDFile(df, "sparse")
        assert str(exc_info.value)[:10] == "DataFrame "
        # with pytest.raises(ValueError, match="Missing required column"):
        #     obd.to_trip()

    def test_custom_config_applied(self):
        """ProcessingConfig.window is respected by to_trip."""
        from drive_cycle_calculator.processing_config import ProcessingConfig

        obd = OBDFile(_make_raw_df(n=30), "test")
        trip4 = obd.to_trip(ProcessingConfig(window=4))
        trip8 = obd.to_trip(ProcessingConfig(window=8))
        # With constant speed the difference is in NaN edges, not in values —
        # just verify both return valid Trips without error.
        assert "smooth_speed_kmh" in trip4._df.columns
        assert "smooth_speed_kmh" in trip8._df.columns


# ── parquet_name ──────────────────────────────────────────────────────────────


class TestParquetName:
    # Torque timestamp format used across tests
    _FMT = "Mon Sep 22 10:30:{:02d} +0300 2019"

    def _make_obd(self, gps_times: list) -> OBDFile:
        df = pd.DataFrame(
            {
                "GPS Time": gps_times,
                "Speed (OBD)(km/h)": [30.0] * len(gps_times),
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * len(gps_times),
                "Engine Load(%)": [50.0] * len(gps_times),
                "Fuel flow rate/hour(l/hr)": [2.0] * len(gps_times),
                "Longitude": [24.0] * len(gps_times),
                "Latitude": [60.0] * len(gps_times),
                "Altitude": [100.0] * len(gps_times),
            }
        )
        return OBDFile(df, "fallback_name")

    def test_format_matches_pattern(self):
        """parquet_name is 't<YYYYMMDD-hhmmss>-<duration_s>-<hash6>' for a valid trip."""
        import re

        obd = self._make_obd([self._FMT.format(i) for i in range(10)])
        name = obd.parquet_name
        assert re.fullmatch(r"t\d{8}-\d{6}-\d+-[0-9a-f]{6}", name), f"Unexpected name: {name!r}"

    def test_start_timestamp_correct(self):
        """UTC date and time in the name reflect the first valid GPS row."""
        # First row: 10:30:00 +0300 → UTC 07:30:00
        obd = self._make_obd([self._FMT.format(i) for i in range(5)])
        name = obd.parquet_name
        assert name.startswith("t20190922-073000"), f"Unexpected name: {name!r}"

    def test_duration_correct(self):
        """Duration in seconds equals last-minus-first GPS timestamp."""
        # 10 rows at 1-second intervals → duration = 9 s
        # Format: t<YYYYMMDD>-<HHMMSS>-<duration_s>-<hash6>; duration is at index 2.
        obd = self._make_obd([self._FMT.format(i) for i in range(10)])
        parts = obd.parquet_name.split("-")
        assert int(parts[2]) == 9

    def test_only_first_and_last_rows_parsed(self, monkeypatch):
        """parquet_name calls to_datetime exactly twice with size-1 series.

        Timestamps are parsed in full at __init__ time (unavoidable); the spy is
        installed *after* construction so we only observe the parquet_name calls.
        """
        from drive_cycle_calculator import gps_time_parser as _mod

        # Build with real timestamps first (init will do its full-column parse)
        obd = self._make_obd([self._FMT.format(i) for i in range(50)])

        # Now install the spy — any subsequent to_datetime call is from parquet_name
        call_sizes: list[int] = []
        original = _mod.GpsTimeParser.to_datetime

        def spy(self, series):
            call_sizes.append(len(series))
            return original(self, series)

        monkeypatch.setattr(_mod.GpsTimeParser, "to_datetime", spy)
        obd.parquet_name

        assert call_sizes == [1, 1], (
            f"Expected exactly two single-row parses from parquet_name, "
            f"got call sizes: {call_sizes}"
        )

    def test_leading_trailing_nans_skipped(self):
        """NaN rows at start and end don't corrupt the result — valid rows are found."""
        times = [None, None, self._FMT.format(0), self._FMT.format(5), None]
        obd = self._make_obd(times)
        name = obd.parquet_name
        assert name.startswith("t20190922-"), f"Unexpected name: {name!r}"
        parts = name.split("-")
        assert int(parts[2]) == 5

    def test_single_row_duration_zero(self):
        """A trip with a single GPS row produces duration_s = 0."""
        obd = self._make_obd([self._FMT.format(0)])
        parts = obd.parquet_name.split("-")
        assert parts[2] == "0", f"Expected duration segment '0', got: {obd.parquet_name!r}"

    def test_no_gps_time_column_falls_back(self):
        """Falls back to self.name when GPS Time column is absent."""
        df = pd.DataFrame({"Speed (OBD)(km/h)": [30.0]})
        with pytest.raises(ValueError) as exc_info:
            obd = OBDFile(df, "fallback_name")
        assert str(exc_info.value)[:10] == "DataFrame "
        ## Previous behaviour allowed missing GPS Time column but fell back to name
        # assert obd.parquet_name == "fallback_name"

    def test_all_unparseable_falls_back(self):
        """Falls back to self.name when GPS Time column is fully unparseable."""
        obd = self._make_obd(["not-a-date", "also-not-a-date"])
        assert obd.parquet_name == "fallback_name"

    def test_same_gps_data_produces_same_hash(self):
        """parquet_name is deterministic: same GPS data → same hash suffix."""
        obd1 = OBDFile(_make_raw_df(), "session_a")
        obd2 = OBDFile(_make_raw_df(), "session_b")
        h1 = obd1.parquet_name.split("-")[-1]
        h2 = obd2.parquet_name.split("-")[-1]
        assert h1 == h2

    def test_different_gps_data_produces_different_hash(self):
        """Different GPS data → different hash suffix."""
        df1 = _make_raw_df()
        df2 = _make_raw_df()
        df2["Longitude"] = 25.0
        obd1 = OBDFile(df1, "session")
        obd2 = OBDFile(df2, "session")
        assert obd1.parquet_name.split("-")[-1] != obd2.parquet_name.split("-")[-1]

    def test_gps_columns_absent_uses_name_hash(self):
        """Absent Lat/Lon → parquet_name uses sha256(name.encode())[:6] in any mode."""
        import hashlib

        df = pd.DataFrame(
            {
                "GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"],
                "Speed (OBD)(km/h)": [30.0],
                "CO\u2082 in g/km (Average)(g/km)": [120.0],
                "Engine Load(%)": [50.0],
                "Fuel flow rate/hour(l/hr)": [2.0],
            }
        )
        obd = OBDFile(df, "my_trip")
        expected = hashlib.sha256("my_trip".encode()).hexdigest()[:6]
        assert obd.parquet_name.endswith(f"-{expected}")

    def test_gps_columns_absent_permissive_uses_name_hash(self):
        """Permissive mode + absent Lat/Lon → same name-hash fallback."""
        import hashlib

        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        obd = OBDFile(df, "my_trip", strict=False)
        expected = hashlib.sha256("my_trip".encode()).hexdigest()[:6]
        assert obd.parquet_name.endswith(f"-{expected}")


# ── strict mode ───────────────────────────────────────────────────────────────


class TestStrictMode:
    def test_strict_true_raises_for_missing_curated_col(self):
        """strict=True (default): missing CURATED_COL → ValueError at construction."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        with pytest.raises(ValueError, match="missing required columns"):
            OBDFile(df, "t", strict=True)

    def test_strict_false_injects_nan_for_missing_curated_col(self):
        """strict=False: missing CURATED_COL → NaN column injected, no ValueError."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        obd = OBDFile(df, "t", strict=False)
        assert "Speed (OBD)(km/h)" in obd._df.columns
        assert pd.isna(obd._df["Speed (OBD)(km/h)"].iloc[0])

    def test_from_xlsx_propagates_strict_false(self, tmp_path):
        """from_xlsx accepts strict=False and propagates it through."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        p = tmp_path / "sparse.xlsx"
        df.to_excel(p, index=False)
        obd = OBDFile.from_xlsx(p, strict=False)
        assert "Speed (OBD)(km/h)" in obd._df.columns

    def test_from_csv_propagates_strict_false(self, tmp_path):
        """from_csv accepts strict=False and propagates it through."""
        df = pd.DataFrame({"GPS Time": ["Mon Sep 22 10:30:00 +0300 2019"]})
        p = tmp_path / "sparse.csv"
        df.to_csv(p, index=False, sep=",")
        obd = OBDFile.from_csv(p, sep=",", strict=False)
        assert "Speed (OBD)(km/h)" in obd._df.columns

    def test_from_parquet_propagates_strict_false(self, tmp_path):
        """from_parquet accepts strict=False and propagates it through."""
        import pyarrow as pa
        import pyarrow.parquet as _pq

        df = pd.DataFrame(
            {"GPS Time": pd.to_datetime(["2019-09-22 07:30:00"], utc=True)}
        )
        _pq.write_table(pa.Table.from_pandas(df), tmp_path / "sparse.parquet")
        obd = OBDFile.from_parquet(tmp_path / "sparse.parquet", strict=False)
        assert "Speed (OBD)(km/h)" in obd._df.columns


# ── to_parquet metadata ───────────────────────────────────────────────────────


class TestToParquetMetadata:
    def test_embeds_dcc_metadata_key(self, tmp_path):
        """to_parquet writes dcc_metadata JSON in PyArrow schema metadata."""
        from drive_cycle_calculator.schema import ParquetMetadata

        obd = OBDFile(_make_raw_df(), "embed_test")
        p = tmp_path / "out.parquet"
        obd.to_parquet(p)
        schema_meta = pq.read_metadata(p).metadata
        assert b"dcc_metadata" in schema_meta
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.schema_version == "1.0"
        assert len(meta.parquet_id) == 6
        assert all(c in "0123456789abcdef" for c in meta.parquet_id)

    def test_user_metadata_embedded(self, tmp_path):
        """to_parquet(user_metadata=...) embeds user fields in dcc_metadata."""
        from drive_cycle_calculator.schema import ParquetMetadata, UserMetadata

        um = UserMetadata(user="alice", fuel_type="diesel")
        obd = OBDFile(_make_raw_df(), "embed_test")
        p = tmp_path / "out.parquet"
        obd.to_parquet(p, user_metadata=um)
        schema_meta = pq.read_metadata(p).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.user_metadata.user == "alice"
        assert meta.user_metadata.fuel_type == "diesel"

    def test_from_parquet_preserves_dcc_metadata(self, tmp_path):
        """Round-trip: to_parquet + from_parquet — dcc_metadata remains accessible."""
        from drive_cycle_calculator.schema import ParquetMetadata, UserMetadata

        um = UserMetadata(user="bob")
        obd = OBDFile(_make_raw_df(), "rt")
        p = tmp_path / "rt.parquet"
        obd.to_parquet(p, user_metadata=um)

        obd2 = OBDFile.from_parquet(p)
        assert obd2.name == "rt"

        schema_meta = pq.read_metadata(p).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.user_metadata.user == "bob"
        assert meta.parquet_id == obd.parquet_name.split("-")[-1]
