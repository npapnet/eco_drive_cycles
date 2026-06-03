"""CLI tests for dcc ingest."""

from __future__ import annotations

import pyarrow.parquet as pq
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.schema import ParquetMetadata

runner = CliRunner()


class TestCliIngestTwoArg:
    """Backward-compat two-argument form: dcc ingest <raw_dir> <out_dir>."""

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


class TestCliIngestSingleArg:
    """Single-argument project-dir mode: dcc ingest <project_dir>."""

    def test_creates_trips_dir_from_raw(self, tmp_path, raw_xlsx):
        """Single-arg mode reads raw/ and writes archive Parquets to trips/."""
        (tmp_path / "raw").mkdir()
        raw_xlsx(tmp_path / "raw" / "trip.xlsx")
        result = runner.invoke(app, ["ingest", str(tmp_path)])
        assert result.exit_code == 0
        parquets = list((tmp_path / "trips").glob("*.parquet"))
        assert len(parquets) == 1

    def test_missing_raw_subfolder_exits_nonzero(self, tmp_path):
        """Single-arg mode exits nonzero with a clear message when raw/ is absent."""
        result = runner.invoke(app, ["ingest", str(tmp_path)])
        assert result.exit_code != 0
        assert "raw/" in result.output

    def test_reads_metadata_yaml_from_raw(self, tmp_path, raw_xlsx):
        """Single-arg mode auto-discovers metadata yaml from raw/."""
        (tmp_path / "raw").mkdir()
        raw_xlsx(tmp_path / "raw" / "trip.xlsx")
        (tmp_path / "raw" / f"metadata-{tmp_path.name}.yaml").write_text(
            "user: bob\n", encoding="utf-8"
        )
        runner.invoke(app, ["ingest", str(tmp_path)])
        parquets = list((tmp_path / "trips").glob("*.parquet"))
        meta = ParquetMetadata.model_validate_json(
            pq.read_metadata(parquets[0]).metadata[b"dcc_metadata"]
        )
        assert meta.user_metadata.user == "bob"

    def test_also_creates_layout_subdirs(self, tmp_path, raw_xlsx):
        """Single-arg mode creates microtrips/, reports/, and analyses/ alongside trips/."""
        (tmp_path / "raw").mkdir()
        raw_xlsx(tmp_path / "raw" / "trip.xlsx")
        runner.invoke(app, ["ingest", str(tmp_path)])
        assert (tmp_path / "trips").is_dir()
        assert (tmp_path / "microtrips").is_dir()
        assert (tmp_path / "reports").is_dir()
        assert (tmp_path / "analyses").is_dir()
