"""CLI tests for dcc analyze."""

from __future__ import annotations

import pytest
from conftest import make_raw_obd_df
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app

runner = CliRunner()


@pytest.fixture
def data_dir(tmp_path, archive_parquet):
    """Populated project directory: 2 archive Parquets + metrics CSV from extract."""
    for i in range(2):
        df = make_raw_obd_df(n=10, speed_kmh=float(20 + i * 10))
        df["Longitude"] = float(24 + i)  # unique coords → unique parquet_id per trip
        archive_parquet(tmp_path / "trips" / f"trip_{i}.parquet", df=df)
    runner.invoke(app, ["extract", str(tmp_path)])
    return tmp_path


class TestCliAnalyze:
    def test_reads_metrics_csv_and_prints_scores(self, data_dir):
        """analyze reads metrics.csv from analyses/ and prints similarity results."""
        csv_files = list((data_dir / "analyses").glob("*/metrics.csv"))
        assert len(csv_files) == 1, "fixture should have produced one metrics.csv"
        result = runner.invoke(app, ["analyze", str(data_dir)])
        assert result.exit_code == 0
        assert "Representative trip" in result.output

    def test_writes_similarity_scores_csv(self, data_dir):
        """analyze writes similarity_scores.csv into a dcca-<ts>/ output directory."""
        runner.invoke(app, ["analyze", str(data_dir)])
        dcca_dirs = list((data_dir / "analyses").glob("dcca-*"))
        assert len(dcca_dirs) == 1
        assert (dcca_dirs[0] / "similarity_scores.csv").exists()

    def test_writes_report_md(self, data_dir):
        """analyze writes report.md alongside similarity_scores.csv."""
        runner.invoke(app, ["analyze", str(data_dir)])
        dcca_dirs = list((data_dir / "analyses").glob("dcca-*"))
        assert (dcca_dirs[0] / "report.md").exists()

    def test_missing_metrics_csv_exits_nonzero(self, tmp_path):
        """analyze exits nonzero with a clear message when no metrics.csv is found."""
        result = runner.invoke(app, ["analyze", str(tmp_path)])
        assert result.exit_code != 0
        assert "metrics.csv" in result.output
