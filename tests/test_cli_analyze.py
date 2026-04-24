"""CLI tests for dcc analyze (N21)."""

from __future__ import annotations

import pytest
from conftest import make_raw_obd_df
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app

runner = CliRunner()


@pytest.fixture
def data_dir(tmp_path, archive_parquet):
    """Populated data directory: 2 archive Parquets + metrics.duckdb from extract."""
    for i in range(2):
        df = make_raw_obd_df(n=10, speed_kmh=float(20 + i * 10))
        df["Longitude"] = float(24 + i)  # unique coords \u2192 unique parquet_id per trip
        archive_parquet(tmp_path / "trips" / f"trip_{i}.parquet", df=df)
    runner.invoke(app, ["extract", str(tmp_path)])
    return tmp_path


class TestCliAnalyze:
    def test_reads_metrics_duckdb_and_prints_scores(self, data_dir):
        """analyze reads metrics.duckdb (not metadata.duckdb) and prints results."""
        assert (data_dir / "metrics.duckdb").exists()
        result = runner.invoke(app, ["analyze", str(data_dir)])
        assert result.exit_code == 0
        assert "Representative trip" in result.output

    def test_missing_metrics_duckdb_exits_nonzero(self, tmp_path):
        """analyze exits nonzero with a clear message when metrics.duckdb is absent."""
        result = runner.invoke(app, ["analyze", str(tmp_path)])
        assert result.exit_code != 0
        assert "metrics.duckdb" in result.output
