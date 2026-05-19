"""Tests for P1 — Resampling and Gap-Check During Ingestion.

Test IDs map to the plan:
  R1–R5  Resampling correctness
  N1–N3  Non-numeric column handling
  G1–G3  Gap-check
  E1–E3  Edge cases
  C1–C3  CLI integration
  B1     Backward compatibility
"""

from __future__ import annotations

import json
import logging

import pandas as pd
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.schema import IngestConfig, ParquetMetadata


runner = CliRunner()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_obd_df_with_timestamps(timestamps: list[str], speed_values=None, n=None):
    """Build a raw OBD DataFrame from explicit timestamp strings."""
    if n is None:
        n = len(timestamps)
    if speed_values is None:
        speed_values = [30.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "GPS Time": timestamps[:n],
            "Speed (OBD)(km/h)": speed_values[:n],
            "CO₂ in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
            "Longitude": [24.0 + i * 0.001 for i in range(n)],
            "Latitude": [60.0 + i * 0.001 for i in range(n)],
            "Altitude": [100.0] * n,
        }
    )


def _make_regular_1hz_timestamps(n: int = 10, start_sec: int = 0) -> list[str]:
    """Generate Torque-format timestamps at exactly 1 Hz."""
    return [
        f"Mon Sep 22 10:30:{start_sec + i:02d} +0300 2019"
        for i in range(n)
    ]


def _make_5hz_timestamps(n_seconds: int = 5) -> list[str]:
    """Generate Torque-style timestamps at 5 Hz (0.2 s intervals).

    Uses datetime objects formatted as strings since Torque format doesn't
    support sub-second precision. We use ISO format instead.
    """
    base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
    timestamps = []
    for i in range(n_seconds * 5):
        ts = base + pd.Timedelta(seconds=i * 0.2)
        timestamps.append(str(ts))
    return timestamps


# ── R: Resampling Tests ─────────────────────────────────────────────────────


class TestResamplingCorrectness:
    """R1–R5: resampling produces correct output."""

    def test_r1_regular_1hz_unchanged(self, tmp_path):
        """R1: Regular 1 s data → output has same row count and values."""
        n = 10
        timestamps = _make_regular_1hz_timestamps(n)
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_r1")

        resampled = obd._resample_to_1hz()

        assert len(resampled) == n
        # Speed values should be preserved (no interpolation needed)
        pd.testing.assert_series_equal(
            resampled["Speed (OBD)(km/h)"].reset_index(drop=True),
            df["Speed (OBD)(km/h)"].reset_index(drop=True),
            check_names=False,
            atol=0.1,
        )

    def test_r2_jittery_upsampled(self, tmp_path):
        """R2: Irregular data (0.5–1.5 s jitter) → uniform 1 s spacing."""
        # Create timestamps with jitter: 0, 0.8, 2.1, 3.0, 4.2, 5.0, 5.9, 7.1, 8.0, 9.0
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        offsets = [0, 0.8, 2.1, 3.0, 4.2, 5.0, 5.9, 7.1, 8.0, 9.0]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_r2")

        resampled = obd._resample_to_1hz()

        # Check uniform spacing
        gps = pd.to_datetime(resampled["GPS Time"])
        dt_seconds = gps.diff().dropna().dt.total_seconds()
        assert (dt_seconds == 1.0).all(), f"Non-uniform spacing found: {dt_seconds.unique()}"

    def test_r3_5hz_downsampled(self, tmp_path):
        """R3: 5 Hz oversampled data → output at 1 Hz, values are means."""
        n_seconds = 5
        timestamps = _make_5hz_timestamps(n_seconds)
        # All speed values within a 1s bin are the same → mean == the value
        speed_values = []
        for sec in range(n_seconds):
            speed_values.extend([30.0 + sec * 10.0] * 5)
        df = _make_obd_df_with_timestamps(timestamps, speed_values=speed_values)
        obd = OBDFile(df, "test_r3")

        resampled = obd._resample_to_1hz()

        # Should have approximately n_seconds rows (1 per second)
        assert len(resampled) == n_seconds
        # Speed values should be the mean of each bin
        expected_speeds = [30.0 + sec * 10.0 for sec in range(n_seconds)]
        for i, expected in enumerate(expected_speeds):
            actual = resampled["Speed (OBD)(km/h)"].iloc[i]
            assert abs(actual - expected) < 0.1, (
                f"Row {i}: expected {expected}, got {actual}"
            )

    def test_r4_mixed_rate(self, tmp_path):
        """R4: Mixed-rate data (bursts of high freq + gaps) → clean 1 Hz bins."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        # Burst of 5 Hz for 2s, then a 2s gap, then more 5 Hz for 2s
        offsets = (
            [i * 0.2 for i in range(10)]         # 0.0..1.8  (10 samples at 5 Hz)
            + [i * 0.2 + 4.0 for i in range(10)]  # 4.0..5.8  (10 samples at 5 Hz)
        )
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_r4")

        resampled = obd._resample_to_1hz()

        # Downsampled output: each bin is 1s-aligned.
        # With a 2s gap in the source, there will be missing bins (seconds 2, 3)
        # which are correctly dropped. Output should have 4 bins: seconds 0, 1, 4, 5.
        gps = pd.to_datetime(resampled["GPS Time"])
        dt_seconds = gps.diff().dropna().dt.total_seconds()
        # All spacing should be integer seconds (no sub-second intervals)
        assert (dt_seconds >= 1.0).all(), f"Sub-second intervals found: {dt_seconds.values}"
        # Should have 4 output rows (2 filled bins per burst)
        assert len(resampled) == 4

    def test_r5_resample_false_preserves_raw(self, tmp_path):
        """R5: resample=False → raw timestamps, IngestConfig.resample=False in metadata."""
        timestamps = _make_regular_1hz_timestamps(10)
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_r5")

        dest = tmp_path / "test_r5.parquet"
        obd.to_parquet(dest, resample=False)

        # Read back metadata
        schema_meta = pq.read_metadata(dest).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.ingest_config is not None
        assert meta.ingest_config.resample is False


# ── N: Non-Numeric Column Tests ─────────────────────────────────────────────


class TestNonNumericColumns:
    """N1–N3: non-numeric columns handled correctly during resampling."""

    def test_n1_upsample_ffill_non_numeric(self, tmp_path):
        """N1: Upsampled non-numeric columns are forward-filled, not interpolated."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        # 3 s gap → will create intermediate 1 s rows
        offsets = [0, 1, 2, 5, 6, 7]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        n = len(timestamps)

        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": [30.0] * n,
                "CO₂ in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
                "Longitude": [24.0] * n,
                "Latitude": [60.0] * n,
                "Altitude": [100.0] * n,
                "note_col": ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
            }
        )
        obd = OBDFile(df, "test_n1")
        resampled = obd._resample_to_1hz()

        # The gap rows (seconds 3, 4) should be forward-filled from "gamma"
        assert "note_col" in resampled.columns
        notes = resampled["note_col"].tolist()
        # Find the value at the interpolated rows (after "gamma" and before "delta")
        # gamma is at second 2, delta is at second 5 → seconds 3, 4 are interpolated
        for val in notes:
            assert isinstance(val, str), f"Non-numeric column contains non-string: {val!r}"
        # No NaN in the forward-filled column (within the filled range)
        assert resampled["note_col"].notna().all()

    def test_n2_downsample_first_non_numeric(self, tmp_path):
        """N2: Downsampled non-numeric columns take first value per bin."""
        timestamps = _make_5hz_timestamps(3)  # 3 seconds at 5 Hz = 15 rows
        n = len(timestamps)

        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": [30.0] * n,
                "CO₂ in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
                "Longitude": [24.0] * n,
                "Latitude": [60.0] * n,
                "Altitude": [100.0] * n,
                "tag": [f"tag_{i}" for i in range(n)],
            }
        )
        obd = OBDFile(df, "test_n2")
        resampled = obd._resample_to_1hz()

        # Should have 3 rows (one per second)
        assert len(resampled) == 3
        # Each row should have the first tag from that 1s bin
        assert resampled["tag"].iloc[0] == "tag_0"
        assert resampled["tag"].iloc[1] == "tag_5"
        assert resampled["tag"].iloc[2] == "tag_10"

    def test_n3_mixed_object_dtype_no_crash(self, tmp_path):
        """N3: Object-dtype column with mixed values doesn't crash."""
        timestamps = _make_regular_1hz_timestamps(5)
        n = 5
        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": [30.0] * n,
                "CO₂ in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
                "Longitude": [24.0] * n,
                "Latitude": [60.0] * n,
                "Altitude": [100.0] * n,
                "mixed_col": ["text", "123", None, "True", "-"],
            }
        )
        obd = OBDFile(df, "test_n3")

        # Should not raise
        resampled = obd._resample_to_1hz()
        assert "mixed_col" in resampled.columns


# ── G: Gap-Check Tests ──────────────────────────────────────────────────────


class TestGapCheck:
    """G1–G3: gap detection and policy enforcement."""

    def test_g1_sub_threshold_gap_warns(self, tmp_path, caplog):
        """G1: 3 s gap below default 5 s threshold → no warning from _check_time_gaps."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        # 3 s gap between second 2 and second 5
        offsets = [0, 1, 2, 5, 6, 7]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_g1")

        with caplog.at_level(logging.WARNING):
            descriptors = obd._check_time_gaps(max_gap_s=5.0, strict=False)

        # 3 s gap does NOT exceed 5 s threshold → no descriptors
        assert len(descriptors) == 0

    def test_g2_above_threshold_warns(self, tmp_path, caplog):
        """G2: 10 s gap + strict=False → warning logged, file still written."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        # 10 s gap between second 2 and second 12
        offsets = [0, 1, 2, 12, 13, 14]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_g2")

        with caplog.at_level(logging.WARNING, logger="drive_cycle_calculator.obd_file"):
            descriptors = obd._check_time_gaps(max_gap_s=5.0, strict=False)

        assert len(descriptors) == 1
        assert descriptors[0]["gap_s"] == 10.0
        assert "exceed" in caplog.text.lower()

        # Should still be able to write
        dest = tmp_path / "test_g2.parquet"
        obd.to_parquet(dest, strict_gaps=False)
        assert dest.exists()

    def test_g3_above_threshold_strict_raises(self, tmp_path):
        """G3: 10 s gap + strict=True → ValueError raised."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        offsets = [0, 1, 2, 12, 13, 14]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_g3")

        with pytest.raises(ValueError, match="gap.*exceed"):
            obd._check_time_gaps(max_gap_s=5.0, strict=True)

    def test_g3_strict_gaps_blocks_to_parquet(self, tmp_path):
        """G3b: strict_gaps=True on to_parquet → ValueError, no file written."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        offsets = [0, 1, 2, 12, 13, 14]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_g3b")

        dest = tmp_path / "test_g3b.parquet"
        with pytest.raises(ValueError, match="gap.*exceed"):
            obd.to_parquet(dest, strict_gaps=True, max_gap_s=5.0)
        assert not dest.exists()


# ── E: Edge Case Tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    """E1–E3: deduplication, single-row, all-NaT."""

    def test_e1_duplicate_timestamps_deduplicated(self, tmp_path):
        """E1: Duplicate timestamps → deduplicated before resample."""
        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        # Two rows with the same timestamp at second 2
        offsets = [0, 1, 2, 2, 3, 4]
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        speeds = [10.0, 20.0, 30.0, 35.0, 40.0, 50.0]
        df = _make_obd_df_with_timestamps(timestamps, speed_values=speeds)
        obd = OBDFile(df, "test_e1")

        resampled = obd._resample_to_1hz()

        # Should have 5 rows (0–4 seconds), duplicate dropped
        assert len(resampled) == 5
        # The first occurrence at second 2 (speed=30.0) should be kept
        assert resampled["Speed (OBD)(km/h)"].iloc[2] == pytest.approx(30.0, abs=0.1)

    def test_e2_single_row_returned_as_is(self, tmp_path):
        """E2: Single-row file → returned as-is (no resample possible)."""
        timestamps = ["Mon Sep 22 10:30:00 +0300 2019"]
        df = _make_obd_df_with_timestamps(timestamps, speed_values=[30.0], n=1)
        obd = OBDFile(df, "test_e2")

        resampled = obd._resample_to_1hz()
        assert len(resampled) == 1

    def test_e3_all_nat_gps_time_no_crash(self, tmp_path):
        """E3: All-NaN GPS Time → returned as-is (no crash)."""
        n = 5
        df = pd.DataFrame(
            {
                "GPS Time": [pd.NaT] * n,
                "Speed (OBD)(km/h)": [30.0] * n,
                "CO₂ in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
                "Longitude": [24.0] * n,
                "Latitude": [60.0] * n,
                "Altitude": [100.0] * n,
            }
        )
        obd = OBDFile(df, "test_e3")

        # Should not raise — all NaT rows are dropped, leaving < 2 rows
        resampled = obd._resample_to_1hz()
        assert len(resampled) == 0


# ── C: CLI Integration Tests ────────────────────────────────────────────────


class TestCliIntegration:
    """C1–C3: CLI flag propagation."""

    def _write_raw_xlsx(self, path, timestamps, speed_values=None):
        """Write a raw OBD xlsx for CLI testing."""
        df = _make_obd_df_with_timestamps(
            timestamps, speed_values=speed_values
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(path, index=False)
        return path

    def test_c1_strict_gaps_skips_file(self, tmp_path):
        """C1: --max-gap-s 3 --strict-gaps → file with 4 s gap is skipped."""
        raw = tmp_path / "raw"
        out = tmp_path / "out"

        base = pd.Timestamp("2019-09-22 10:30:00", tz="UTC")
        offsets = [0, 1, 2, 6, 7, 8]  # 4 s gap between second 2 and 6
        timestamps = [str(base + pd.Timedelta(seconds=s)) for s in offsets]
        self._write_raw_xlsx(raw / "trip.xlsx", timestamps)

        result = runner.invoke(
            app, ["ingest", "--max-gap-s", "3", "--strict-gaps", str(raw), str(out)]
        )

        assert result.exit_code == 0
        assert "SKIPPED" in result.output
        # No parquet should have been written
        parquets = list((out / "trips").glob("*.parquet"))
        assert len(parquets) == 0

    def test_c2_max_gap_s_in_metadata(self, tmp_path):
        """C2: --max-gap-s value embedded in Parquet IngestConfig metadata."""
        raw = tmp_path / "raw"
        out = tmp_path / "out"

        timestamps = _make_regular_1hz_timestamps(10)
        self._write_raw_xlsx(raw / "trip.xlsx", timestamps)

        result = runner.invoke(
            app, ["ingest", "--max-gap-s", "8", str(raw), str(out)]
        )
        assert result.exit_code == 0

        parquets = list((out / "trips").glob("*.parquet"))
        assert len(parquets) == 1
        schema_meta = pq.read_metadata(parquets[0]).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.ingest_config is not None
        assert meta.ingest_config.max_gap_s == 8.0
        assert meta.ingest_config.resample is True

    def test_c3_no_resample_flag(self, tmp_path):
        """C3: --no-resample → archive has IngestConfig.resample=False."""
        raw = tmp_path / "raw"
        out = tmp_path / "out"

        timestamps = _make_regular_1hz_timestamps(10)
        self._write_raw_xlsx(raw / "trip.xlsx", timestamps)

        result = runner.invoke(
            app, ["ingest", "--no-resample", str(raw), str(out)]
        )
        assert result.exit_code == 0

        parquets = list((out / "trips").glob("*.parquet"))
        assert len(parquets) == 1
        schema_meta = pq.read_metadata(parquets[0]).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.ingest_config is not None
        assert meta.ingest_config.resample is False


# ── B: Backward Compatibility Tests ─────────────────────────────────────────


class TestBackwardCompatibility:
    """B1: old Parquets without ingest_config still work."""

    def test_b1_missing_ingest_config_deserializes(self):
        """B1: ParquetMetadata without ingest_config field deserializes (None)."""
        # Simulate an old v2 Parquet's dcc_metadata JSON (no ingest_config key)
        old_meta_json = json.dumps(
            {
                "schema_version": "1.0",
                "software_version": "0.3.0",
                "parquet_id": "abc123",
                "ingest_provenance": {
                    "ingest_timestamp": "2025-01-01T00:00:00Z",
                    "source_filename": "old_trip",
                },
                "computed_trip_stats": {
                    "start_time": None,
                    "end_time": None,
                    "gps_lat_mean": 0.0,
                    "gps_lat_std": 0.0,
                    "gps_lon_mean": 0.0,
                    "gps_lon_std": 0.0,
                },
                "user_metadata": {},
                # NOTE: no "ingest_config" key
            }
        )
        meta = ParquetMetadata.model_validate_json(old_meta_json)
        assert meta.ingest_config is None


# ── Metadata round-trip ─────────────────────────────────────────────────────


class TestMetadataRoundTrip:
    """Verify IngestConfig survives write → read cycle."""

    def test_ingest_config_embedded_in_parquet(self, tmp_path):
        """to_parquet() embeds IngestConfig; from_parquet() can read the archive."""
        timestamps = _make_regular_1hz_timestamps(10)
        df = _make_obd_df_with_timestamps(timestamps)
        obd = OBDFile(df, "test_roundtrip")

        dest = tmp_path / "roundtrip.parquet"
        obd.to_parquet(dest, max_gap_s=7.5, resample=True)

        # Read metadata
        schema_meta = pq.read_metadata(dest).metadata
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert meta.ingest_config is not None
        assert meta.ingest_config.resample is True
        assert meta.ingest_config.max_gap_s == 7.5
        assert meta.ingest_config.strict_gaps is False

        # Verify the archive can be loaded back
        obd2 = OBDFile.from_parquet(dest)
        assert obd2 is not None
