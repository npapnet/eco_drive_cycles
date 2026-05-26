"""CLI tests for dcc extract."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app

runner = CliRunner()

_EXPECTED_COLS = {
    "trip_id", "parquet_path", "parquet_id",
    "start_time", "end_time",
    "user", "fuel_type", "vehicle_category", "vehicle_make", "vehicle_model",
    "engine_size_cc", "year",
    "gps_lat_mean", "gps_lon_mean",
    "duration_s", "avg_velocity_kmh", "mean_speed_ns_kmh", "max_velocity_kmh",
    "avg_acceleration_ms2", "avg_deceleration_ms2", "idle_time_pct", "stop_count",
    "config_hash", "config_snapshot",
}


def _find_metrics_csv(data_dir):
    """Return the metrics.csv written by extract, or None."""
    csvs = sorted((data_dir / "analyses").glob("*/metrics.csv"))
    return csvs[-1] if csvs else None


class TestCliExtract:
    def test_produces_metrics_csv(self, tmp_path, archive_parquet):
        """extract creates a metrics.csv under analyses/<timestamp>/."""
        archive_parquet(tmp_path / "trips" / "trip_a.parquet")
        result = runner.invoke(app, ["extract", str(tmp_path)])
        assert result.exit_code == 0
        csv_path = _find_metrics_csv(tmp_path)
        assert csv_path is not None and csv_path.exists()
        df = pd.read_csv(csv_path)
        assert len(df) == 1

    def test_no_duckdb_created(self, tmp_path, archive_parquet):
        """extract does not create any .duckdb file."""
        archive_parquet(tmp_path / "trips" / "trip_a.parquet")
        runner.invoke(app, ["extract", str(tmp_path)])
        assert not any(tmp_path.rglob("*.duckdb"))

    def test_output_schema_completeness(self, tmp_path, archive_parquet):
        """metrics.csv has all expected columns including mean_speed_ns_kmh."""
        archive_parquet(tmp_path / "trips" / "trip_a.parquet", speed_kmh=36.0)
        runner.invoke(app, ["extract", str(tmp_path)])
        csv_path = _find_metrics_csv(tmp_path)
        df = pd.read_csv(csv_path)
        assert _EXPECTED_COLS.issubset(set(df.columns))
        row = df.iloc[0]
        assert row["trip_id"] is not None
        assert len(row["config_hash"]) == 8
        assert '"window"' in row["config_snapshot"]
        assert pd.notna(row["mean_speed_ns_kmh"])

    def test_skips_legacy_parquet_without_dcc_metadata(self, tmp_path):
        """Parquet lacking dcc_metadata is skipped; exit code 0; no metrics.csv written."""
        trips = tmp_path / "trips"
        trips.mkdir()
        df = pd.DataFrame({"Speed (OBD)(km/h)": [30.0]})
        table = pa.Table.from_pandas(df).replace_schema_metadata({b"format_version": b"2"})
        pq.write_table(table, trips / "legacy.parquet")
        result = runner.invoke(app, ["extract", str(tmp_path)])
        assert result.exit_code == 0
        assert "SKIP" in result.output
        assert _find_metrics_csv(tmp_path) is None
