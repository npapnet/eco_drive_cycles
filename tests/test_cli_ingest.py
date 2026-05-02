"""CLI tests for dcc ingest (N14–N17)."""

from __future__ import annotations

import pyarrow.parquet as pq
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.schema import ParquetMetadata

runner = CliRunner()


class TestCliIngest:
    def test_no_duckdb_created(self, tmp_path, raw_xlsx):
        """ingest does NOT create any DuckDB file — only archive Parquets."""
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw_xlsx(raw / "trip.xlsx")
        result = runner.invoke(app, ["ingest", str(raw), str(out)])
        assert result.exit_code == 0
        assert not (out / "metadata.duckdb").exists()
        assert not (out / "metrics.duckdb").exists()

    def test_embeds_dcc_metadata_in_parquet(self, tmp_path, raw_xlsx):
        """Ingested Parquet has dcc_metadata key with a 6-char hex parquet_id."""
        raw = tmp_path / "raw"
        raw_xlsx(raw / "trip.xlsx")
        result = runner.invoke(app, ["ingest", str(raw), str(tmp_path / "out")])
        assert result.exit_code == 0
        parquets = list((tmp_path / "out" / "trips").glob("*.parquet"))
        assert len(parquets) == 1
        schema_meta = pq.read_metadata(parquets[0]).metadata
        assert b"dcc_metadata" in schema_meta
        meta = ParquetMetadata.model_validate_json(schema_meta[b"dcc_metadata"])
        assert len(meta.parquet_id) == 6
        assert all(c in "0123456789abcdef" for c in meta.parquet_id)

    def test_reads_user_metadata_from_yaml(self, tmp_path, raw_xlsx):
        """With metadata-<folder>.yaml present, user fields are embedded in every Parquet."""
        raw = tmp_path / "raw"
        raw_xlsx(raw / "trip.xlsx")
        (raw / f"metadata-{raw.name}.yaml").write_text(
            "user: alice\nfuel_type: diesel\n", encoding="utf-8"
        )
        runner.invoke(app, ["ingest", str(raw), str(tmp_path / "out")])
        parquets = list((tmp_path / "out" / "trips").glob("*.parquet"))
        meta = ParquetMetadata.model_validate_json(
            pq.read_metadata(parquets[0]).metadata[b"dcc_metadata"]
        )
        assert meta.user_metadata.user == "alice"
        assert meta.user_metadata.fuel_type == "diesel"

    def test_proceeds_without_metadata_yaml(self, tmp_path, raw_xlsx):
        """Ingest succeeds when no metadata yaml is present; user fields are all None."""
        raw = tmp_path / "raw"
        raw_xlsx(raw / "trip.xlsx")
        result = runner.invoke(app, ["ingest", str(raw), str(tmp_path / "out")])
        assert result.exit_code == 0
        parquets = list((tmp_path / "out" / "trips").glob("*.parquet"))
        meta = ParquetMetadata.model_validate_json(
            pq.read_metadata(parquets[0]).metadata[b"dcc_metadata"]
        )
        assert meta.user_metadata.user is None
        assert meta.user_metadata.fuel_type is None
