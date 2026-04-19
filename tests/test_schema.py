"""Tests for Pydantic models in schema.py (N8, N9, N10)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from drive_cycle_calculator.schema import (
    ComputedTripStats,
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
