"""Tests for Pydantic models in schema.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from drive_cycle_calculator.schema import (
    ClusterSynthesisConfig,
    ComputedTripStats,
    MarkovConfig,
    SynthesisSelectionConfig,
    WLTPSynthesisConfig,
    FuelType,
    IngestProvenance,
    ParquetMetadata,
    UserMetadata,
    VehicleCategory,
)


class TestParquetMetadataRoundtrip:
    def test_roundtrip_preserves_all_fields(self):
        """model_dump_json → model_validate_json restores all fields."""
        meta = ParquetMetadata(
            schema_version="1.0",
            software_version="0.3.0",
            parquet_id="a3f9bc",
            ingest_provenance=IngestProvenance(
                ingest_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                source_filename="morning.xlsx",
            ),
            computed_trip_stats=ComputedTripStats(
                start_time=datetime(2026, 1, 1, 7, 30, tzinfo=timezone.utc),
                end_time=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc),
                gps_lat_mean=37.97,
                gps_lat_std=0.002,
                gps_lon_mean=23.73,
                gps_lon_std=0.001,
            ),
            user_metadata=UserMetadata(user="nikos", fuel_type="diesel"),
        )
        recovered = ParquetMetadata.model_validate_json(meta.model_dump_json())
        assert recovered.schema_version == "1.0"
        assert recovered.parquet_id == "a3f9bc"
        assert recovered.user_metadata.user == "nikos"
        assert recovered.user_metadata.fuel_type == "diesel"
        assert recovered.computed_trip_stats.gps_lat_mean == pytest.approx(37.97)
        assert recovered.ingest_provenance.source_filename == "morning.xlsx"

    def test_parquet_id_preserved_as_string(self):
        """parquet_id round-trips as a plain string."""
        meta = ParquetMetadata(
            schema_version="1.0",
            software_version="0.3.0",
            parquet_id="ff00aa",
            ingest_provenance=IngestProvenance(
                ingest_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                source_filename="f.csv",
            ),
            computed_trip_stats=ComputedTripStats(),
            user_metadata=UserMetadata(),
        )
        recovered = ParquetMetadata.model_validate_json(meta.model_dump_json())
        assert recovered.parquet_id == "ff00aa"


class TestUserMetadataEnumValidation:
    def test_valid_fuel_type_accepted(self):
        """UserMetadata accepts all FuelType enum values."""
        for val in FuelType:
            um = UserMetadata(fuel_type=val.value)
            assert um.fuel_type == val.value

    def test_valid_vehicle_category_accepted(self):
        """UserMetadata accepts all VehicleCategory enum values."""
        for val in VehicleCategory:
            um = UserMetadata(vehicle_category=val.value)
            assert um.vehicle_category == val.value

    def test_invalid_fuel_type_raises_validation_error(self):
        """Invalid fuel_type value raises ValidationError naming the field."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserMetadata(fuel_type="gazoline")
        assert "fuel_type" in str(exc_info.value)

    def test_invalid_vehicle_category_raises_validation_error(self):
        """Invalid vehicle_category value raises ValidationError naming the field."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserMetadata(vehicle_category="spaceship")
        assert "vehicle_category" in str(exc_info.value)

    def test_all_none_user_metadata_is_valid(self):
        """UserMetadata with all fields None is valid — empty is the default."""
        um = UserMetadata()
        assert um.fuel_type is None
        assert um.user is None
        assert um.vehicle_make is None


_WORKFLOW_DIR = Path(__file__).parent.parent / "examples" / "workflow"


class TestSynthesisConfigs:
    def test_markov_config_defaults_validate(self):
        """MarkovConfig instantiates with defaults and no JSON input."""
        cfg = MarkovConfig()
        assert cfg.speed_bin_width_kmh == 10.0
        assert cfg.acc_bin_width_ms2 == 0.2
        assert cfg.acc_range_ms2 == 1.5
        assert cfg.markov_lambda == 1.0

    def test_selection_config_defaults_validate(self):
        """SynthesisSelectionConfig instantiates with defaults."""
        cfg = SynthesisSelectionConfig()
        assert cfg.n_trials == 1000
        assert cfg.random_seed == 42
        assert "mean_speed_kmh" in cfg.metric_weights

    def test_wltp_config_defaults_validate(self):
        """WLTPSynthesisConfig instantiates with defaults and no JSON input."""
        cfg = WLTPSynthesisConfig()
        assert cfg.inter_phase_idle_s == 20
        assert "Low" in cfg.phase_min_distance_m
        assert isinstance(cfg.markov, MarkovConfig)
        assert isinstance(cfg.selection, SynthesisSelectionConfig)

    def test_cluster_config_defaults_validate(self):
        """ClusterSynthesisConfig instantiates with defaults and no JSON input."""
        cfg = ClusterSynthesisConfig()
        assert cfg.inter_cluster_idle_s == 20
        assert cfg.cluster_min_distance_m == 600.0
        assert isinstance(cfg.markov, MarkovConfig)
        assert isinstance(cfg.selection, SynthesisSelectionConfig)

    def test_wltp_roundtrip_preserves_all_fields(self):
        """WLTPSynthesisConfig: JSON → model → JSON preserves all field values."""
        original = WLTPSynthesisConfig(
            markov=MarkovConfig(speed_bin_width_kmh=5.0),
            inter_phase_idle_s=30,
            phase_min_distance_m={"Low": 1000.0, "Med": 2000.0, "High": 3000.0, "xHigh": 4000.0},
        )
        recovered = WLTPSynthesisConfig.model_validate_json(original.model_dump_json())
        assert recovered.markov.speed_bin_width_kmh == 5.0
        assert recovered.inter_phase_idle_s == 30
        assert recovered.phase_min_distance_m["Low"] == 1000.0

    def test_cluster_roundtrip_preserves_all_fields(self):
        """ClusterSynthesisConfig: JSON → model → JSON preserves all field values."""
        original = ClusterSynthesisConfig(
            cluster_min_distance_m=1500.0,
            selection=SynthesisSelectionConfig(n_trials=500),
        )
        recovered = ClusterSynthesisConfig.model_validate_json(original.model_dump_json())
        assert recovered.cluster_min_distance_m == 1500.0
        assert recovered.selection.n_trials == 500

    def test_unknown_fields_raise_validation_error(self):
        """Extra fields in JSON that are not in the model raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WLTPSynthesisConfig.model_validate_json('{"unexpected_field": 99}')
        with pytest.raises(ValidationError):
            ClusterSynthesisConfig.model_validate_json('{"unexpected_field": 99}')

    def test_config_wltp_json_parses_cleanly(self):
        """examples/workflow/config_wltp.json loads into WLTPSynthesisConfig without error."""
        path = _WORKFLOW_DIR / "config_wltp.json"
        cfg = WLTPSynthesisConfig.model_validate_json(path.read_text(encoding="utf-8"))
        assert cfg.markov.speed_bin_width_kmh == 10.0
        assert cfg.markov.markov_lambda == 1.0
        assert cfg.selection.n_trials == 1000
        assert cfg.selection.metric_weights["rpa"] == 2.0
        assert cfg.inter_phase_idle_s == 20
        assert cfg.phase_min_distance_m["Low"] == 800.0

    def test_config_syn_cluster_json_parses_cleanly(self):
        """examples/workflow/config_syn_cluster.json loads into ClusterSynthesisConfig."""
        path = _WORKFLOW_DIR / "config_syn_cluster.json"
        cfg = ClusterSynthesisConfig.model_validate_json(path.read_text(encoding="utf-8"))
        assert cfg.markov.speed_bin_width_kmh == 10.0
        assert cfg.selection.max_reuse_fraction == pytest.approx(0.30)
        assert cfg.inter_cluster_idle_s == 20
        assert cfg.cluster_min_distance_m == 600.0

    def test_markov_config_unknown_fields_raise(self):
        """MarkovConfig rejects unknown fields."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MarkovConfig(speed_bin_width_kmh=5.0, unknown=99)

    def test_selection_config_unknown_fields_raise(self):
        """SynthesisSelectionConfig rejects unknown fields."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SynthesisSelectionConfig(n_trials=100, unknown=99)
