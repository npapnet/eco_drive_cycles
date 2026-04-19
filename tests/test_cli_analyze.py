"""CLI tests for dcc analyze (N21)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.obd_file import OBDFile

runner = CliRunner()


def _setup_data_dir(data_dir: Path, n_trips: int = 2) -> None:
    """Write archive Parquets and run extract to produce metrics.duckdb."""
    trips_dir = data_dir / "trips"
    trips_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n_trips):
        timestamps = [f"Mon Sep 22 10:30:{j:02d} +0300 2019" for j in range(10)]
        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": [float(20 + i * 10)] * 10,
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * 10,
                "Engine Load(%)": [50.0] * 10,
                "Fuel flow rate/hour(l/hr)": [2.0] * 10,
                "Longitude": [float(24 + i)] * 10,
                "Latitude": [60.0] * 10,
            }
        )
        OBDFile(df, f"trip_{i}").to_parquet(trips_dir / f"trip_{i}.parquet")
    runner.invoke(app, ["extract", str(data_dir)])


class TestCliAnalyze:
    def test_reads_metrics_duckdb_and_prints_scores(self, tmp_path):
        """analyze reads metrics.duckdb (not metadata.duckdb) and prints results."""
        _setup_data_dir(tmp_path)
        assert (tmp_path / "metrics.duckdb").exists()
        result = runner.invoke(app, ["analyze", str(tmp_path)])
        assert result.exit_code == 0
        assert "Representative trip" in result.output

    def test_missing_metrics_duckdb_exits_nonzero(self, tmp_path):
        """analyze exits nonzero with a clear message when metrics.duckdb is absent."""
        result = runner.invoke(app, ["analyze", str(tmp_path)])
        assert result.exit_code != 0
        assert "metrics.duckdb" in result.output
