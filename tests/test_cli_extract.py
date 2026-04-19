"""CLI tests for dcc extract (N18–N20)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.obd_file import OBDFile

runner = CliRunner()

_EXPECTED_COLS = {
    "trip_id", "parquet_path", "parquet_id",
    "start_time", "end_time",
    "user", "fuel_type", "vehicle_category", "vehicle_make", "vehicle_model",
    "engine_size_cc", "year",
    "gps_lat_mean", "gps_lon_mean",
    "duration_s", "avg_velocity_kmh", "max_velocity_kmh",
    "avg_acceleration_ms2", "avg_deceleration_ms2", "idle_time_pct", "stop_count",
    "config_hash", "config_snapshot",
}


def _make_archive_parquet(path: Path, speed_kmh: float = 30.0, n: int = 10) -> None:
    """Write a v2 archive Parquet with embedded dcc_metadata."""
    timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
    df = pd.DataFrame(
        {
            "GPS Time": timestamps,
            "Speed (OBD)(km/h)": [speed_kmh] * n,
            "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
            "Longitude": [24.0] * n,
            "Latitude": [60.0] * n,
        }
    )
    OBDFile(df, path.stem).to_parquet(path)


class TestCliExtract:
    def test_produces_metrics_duckdb(self, tmp_path):
        """extract creates metrics.duckdb with a trip_metrics table."""
        import duckdb

        trips = tmp_path / "trips"
        trips.mkdir()
        _make_archive_parquet(trips / "trip_a.parquet")
        result = runner.invoke(app, ["extract", str(tmp_path)])
        assert result.exit_code == 0
        db_path = tmp_path / "metrics.duckdb"
        assert db_path.exists()
        with duckdb.connect(str(db_path), read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM trip_metrics").fetchone()[0]
        assert count == 1

    def test_output_schema_completeness(self, tmp_path):
        """trip_metrics table has all expected columns with non-null trip_id."""
        import duckdb

        trips = tmp_path / "trips"
        trips.mkdir()
        _make_archive_parquet(trips / "trip_a.parquet", speed_kmh=36.0)
        runner.invoke(app, ["extract", str(tmp_path)])
        db_path = tmp_path / "metrics.duckdb"
        with duckdb.connect(str(db_path), read_only=True) as conn:
            cols = {
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='trip_metrics'"
                ).fetchall()
            }
            row = conn.execute("SELECT trip_id, config_hash, config_snapshot FROM trip_metrics").fetchone()
        assert _EXPECTED_COLS.issubset(cols)
        assert row is not None
        trip_id, config_hash, config_snapshot = row
        assert trip_id is not None
        assert len(config_hash) == 8
        assert '"window"' in config_snapshot

    def test_skips_legacy_parquet_without_dcc_metadata(self, tmp_path):
        """Parquet lacking dcc_metadata is skipped; exit code 0; no output file."""
        trips = tmp_path / "trips"
        trips.mkdir()
        df = pd.DataFrame({"Speed (OBD)(km/h)": [30.0]})
        table = pa.Table.from_pandas(df).replace_schema_metadata({b"format_version": b"2"})
        pq.write_table(table, trips / "legacy.parquet")
        result = runner.invoke(app, ["extract", str(tmp_path)])
        assert result.exit_code == 0
        assert "SKIP" in result.output
        assert not (tmp_path / "metrics.duckdb").exists()
