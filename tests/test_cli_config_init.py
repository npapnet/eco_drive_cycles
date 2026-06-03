"""CLI tests for dcc config-init."""

from __future__ import annotations

from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app

runner = CliRunner()


def _project_with_raw(tmp_path):
    """Create a project dir with a raw/ subfolder, return the project dir."""
    (tmp_path / "raw").mkdir()
    return tmp_path


class TestConfigInit:
    def test_writes_metadata_yaml_in_raw_subfolder(self, tmp_path):
        """config-init writes metadata-<project_dir>.yaml into raw/."""
        proj = _project_with_raw(tmp_path)
        result = runner.invoke(app, ["config-init", str(proj)])
        assert result.exit_code == 0
        expected = proj / "raw" / f"metadata-{proj.name}.yaml"
        assert expected.exists()

    def test_yaml_uses_project_dir_name_not_raw(self, tmp_path):
        """YAML filename is derived from the project directory name, not 'raw'."""
        proj = tmp_path / "myproject"
        proj.mkdir()
        (proj / "raw").mkdir()
        runner.invoke(app, ["config-init", str(proj)])
        assert (proj / "raw" / "metadata-myproject.yaml").exists()
        assert not (proj / "raw" / "metadata-raw.yaml").exists()

    def test_yaml_contains_all_user_metadata_fields(self, tmp_path):
        """Output YAML contains every UserMetadata field as a null entry."""
        proj = _project_with_raw(tmp_path)
        runner.invoke(app, ["config-init", str(proj)])
        text = (proj / "raw" / f"metadata-{proj.name}.yaml").read_text(encoding="utf-8")
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
        proj = _project_with_raw(tmp_path)
        runner.invoke(app, ["config-init", str(proj)])
        text = (proj / "raw" / f"metadata-{proj.name}.yaml").read_text(encoding="utf-8")
        assert 'sep: ","' in text
        assert 'decimal: "."' in text

    def test_missing_raw_subfolder_exits_nonzero(self, tmp_path):
        """config-init exits nonzero with a clear message when raw/ is absent."""
        result = runner.invoke(app, ["config-init", str(tmp_path)])
        assert result.exit_code != 0
        assert "raw/" in result.output

    def test_existing_file_exits_nonzero_without_force(self, tmp_path):
        """Running config-init twice without --force exits with a nonzero code."""
        proj = _project_with_raw(tmp_path)
        runner.invoke(app, ["config-init", str(proj)])
        result = runner.invoke(app, ["config-init", str(proj)])
        assert result.exit_code != 0

    def test_force_flag_overwrites_existing(self, tmp_path):
        """--force allows overwriting an existing metadata yaml."""
        proj = _project_with_raw(tmp_path)
        runner.invoke(app, ["config-init", str(proj)])
        result = runner.invoke(app, ["config-init", "--force", str(proj)])
        assert result.exit_code == 0
