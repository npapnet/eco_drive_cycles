# schema.py
# ---------
# OBD column constants and Pydantic metadata models for the v0.3 schema.
# ProcessingConfig lives in processing_config.py.

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── OBD column constants ──────────────────────────────────────────────────────

# Maps raw OBD column names (as exported by Torque) to short English names
# used in the processed DataFrame produced by ProcessingConfig.apply().
# Note: "GPS Time" is NOT here — it is consumed to produce elapsed_s, not renamed.
OBD_COLUMN_MAP: dict[str, str] = {
    "Speed (OBD)(km/h)": "speed_kmh",
    "CO₂ in g/km (Average)(g/km)": "co2_g_per_km",
    "Engine Load(%)": "engine_load_pct",
    "Fuel flow rate/hour(l/hr)": "fuel_flow_lph",
}

# The minimum set of OBD columns required for analysis.
# OBDFile.curated_df returns only these columns.
# OBDFile.to_trip() raises ValueError if any are absent.
CURATED_COLS: list[str] = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO₂ in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]


# ── Enums ────────────────────────────────────────────────────────────────────


class FuelType(str, Enum):
    PETROL = "petrol"
    DIESEL = "diesel"
    E10 = "e10"
    E85 = "e85"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"
    OTHER = "other"


class VehicleCategory(str, Enum):
    SEDAN = "sedan"
    SUV = "suv"
    HATCHBACK = "hatchback"
    VAN = "van"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    OTHER = "other"


# ── Sub-models (provenance-grouped) ──────────────────────────────────────────


class UserMetadata(BaseModel):
    """Declared by the user via metadata-<folder>.yaml. All fields optional."""

    fuel_type: Optional[FuelType] = Field(None, description="Fuel type used. Valid values: petrol, diesel, e10, e85, hybrid, electric, lpg, other")
    vehicle_category: Optional[VehicleCategory] = Field(None, description="Body style. Valid values: sedan, suv, hatchback, van, truck, motorcycle, other")
    user: Optional[str] = Field(None, description="Identifier for the driver/user")
    vehicle_make: Optional[str] = Field(None, description="Manufacturer, e.g. Toyota")
    vehicle_model: Optional[str] = Field(None, description="Model name, e.g. Yaris")
    engine_size_cc: Optional[int] = Field(None, description="Engine displacement in cc (integer)")
    year: Optional[int] = Field(None, description="Vehicle model year (integer)")
    misc: Optional[dict] = Field(None, description="Any additional key-value pairs not covered above")

    model_config = {"use_enum_values": True}


class IngestProvenance(BaseModel):
    """Recorded by the ingest process. Describes the software action."""

    ingest_timestamp: datetime = Field(description="UTC timestamp when ingest was run")
    source_filename: str = Field(description="Original filename of the raw OBD export")


class ComputedTripStats(BaseModel):
    """Derived from the raw signal during ingest. Never user-supplied."""

    start_time: Optional[datetime] = Field(None, description="UTC timestamp of first valid GPS row")
    end_time: Optional[datetime] = Field(None, description="UTC timestamp of last valid GPS row")
    gps_lat_mean: float = Field(0.0, description="Mean latitude over the trip")
    gps_lat_std: float = Field(0.0, description="Std deviation of latitude")
    gps_lon_mean: float = Field(0.0, description="Mean longitude over the trip")
    gps_lon_std: float = Field(0.0, description="Std deviation of longitude")


# ── Top-level container ───────────────────────────────────────────────────────


class ParquetMetadata(BaseModel):
    """Root metadata object embedded in every archive Parquet under 'dcc_metadata'."""

    schema_version: str = Field(description="dcc_metadata schema version")
    software_version: str = Field(description="drive_cycle_calculator package version")
    parquet_id: str = Field(description="6-char sha256 hash of raw GPS lat+lon data")

    ingest_provenance: IngestProvenance
    computed_trip_stats: ComputedTripStats
    user_metadata: UserMetadata


# ── SegmentationConfig ────────────────────────────────────────────────────────


class SegmentationConfig(BaseModel):
    """Parameters for microtrip segmentation.

    Independent of ProcessingConfig — smoothing and segmentation are separate
    pipeline stages with separate sensitivity profiles.

    See microtrip_design_spec.md §3.2.
    """

    stop_threshold_kmh: float = 2.0
    stop_min_duration_s: float = 1.0
    microtrip_min_duration_s: float = 15.0
    microtrip_min_distance_m: float = 50.0

    @field_validator("microtrip_min_duration_s")
    @classmethod
    def _min_above_floor(cls, v: float) -> float:
        """Enforce the 5 s hard floor derived from sensor noise literature.

        See microtrip_design_spec.md §3.2.
        """
        if v < 5.0:
            raise ValueError("microtrip_min_duration_s cannot be below the 5 s floor")
        return v


# ── YAML template generator ───────────────────────────────────────────────────


def generate_yaml_template(model_class: type[BaseModel]) -> str:
    """Produce a YAML template string from a Pydantic model's field metadata.

    Each field becomes a ``field_name: null`` line preceded by a ``# comment``
    line drawn from the field's ``description``. Enum fields have their valid
    values listed in the comment.  The header block is prepended automatically.
    """
    lines = [
        "# Drive Cycle Calculator — folder metadata",
        "# Fill in the fields below. Leave as null if unknown.",
        "# This file applies to ALL raw OBD files in this folder.",
        "",
    ]

    for field_name, field_info in model_class.model_fields.items():
        description = field_info.description or field_name
        lines.append(f"# {description}")
        lines.append(f"{field_name}: null")
        lines.append("")

    return "\n".join(lines)
