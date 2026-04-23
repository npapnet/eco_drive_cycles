"""CLI tests for dcc config-init (N13)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app

runner = CliRunner()


class TestConfigInit:
    def test_writes_metadata_yaml_in_folder(self, tmp_path):
        """config-init writes metadata-<folder>.yaml into the target folder."""
        result = runner.invoke(app, ["config-init", str(tmp_path)])
        assert result.exit_code == 0
        expected = tmp_path / f"metadata-{tmp_path.name}.yaml"
        assert expected.exists()

    def test_yaml_contains_all_user_metadata_fields(self, tmp_path):
        """Output YAML contains every UserMetadata field as a null entry."""
        runner.invoke(app, ["config-init", str(tmp_path)])
        text = (tmp_path / f"metadata-{tmp_path.name}.yaml").read_text(encoding="utf-8")
        for field in [
            "user",
            "fuel_type",
            "vehicle_category",
            "vehicle_make",
            "vehicle_model",
            "engine_size_cc",
            "year",
            "misc",
        ]:
            assert f"{field}: null" in text, f"Missing field: {field}"

    def test_yaml_contains_ingest_settings(self, tmp_path):
        """Output YAML includes sep and decimal CSV settings."""
        runner.invoke(app, ["config-init", str(tmp_path)])
        text = (tmp_path / f"metadata-{tmp_path.name}.yaml").read_text(encoding="utf-8")
        assert 'sep: ","' in text
        assert 'decimal: "."' in text

    def test_existing_file_exits_nonzero_without_force(self, tmp_path):
        """Running config-init twice without --force exits with a nonzero code."""
        runner.invoke(app, ["config-init", str(tmp_path)])
        result = runner.invoke(app, ["config-init", str(tmp_path)])
        assert result.exit_code != 0

    def test_force_flag_overwrites_existing(self, tmp_path):
        """--force allows overwriting an existing metadata yaml."""
        runner.invoke(app, ["config-init", str(tmp_path)])
        result = runner.invoke(app, ["config-init", "--force", str(tmp_path)])
        assert result.exit_code == 0
