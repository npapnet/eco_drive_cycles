# schema.py
# ---------
# Pydantic models for the v0.3 metadata schema, and ProcessingConfig (migrated
# from @dataclass).  All business logic for OBD processing also lives here so
# that downstream code only needs one import for both schema and computation.

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Optional, Union, get_args, get_origin

import pandas as pd
from pydantic import BaseModel, Field, field_validator


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


# ── ProcessingConfig (migrated from @dataclass) ───────────────────────────────


class ProcessingConfig(BaseModel):
    """Parameters for the OBD data processing pipeline.

    Attributes
    ----------
    window : int
        Rolling window size for speed smoothing (samples). Default 4.
    stop_threshold_kmh : float
        Speed below which a sample is classified as stopped (km/h).
    """

    window: int = 4
    stop_threshold_kmh: float = 2.0

    @property
    def config_hash(self) -> str:
        """First 8 characters of the md5 of the sorted JSON of config fields.

        Deterministic across instances with identical field values.
        Stored in the DuckDB catalog for reproducibility auditing.
        """
        payload = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.md5(payload.encode()).hexdigest()[:8]

    @property
    def config_snapshot(self) -> str:
        """Full field values as a compact JSON string.

        Suitable for storing in DuckDB so past configs are recoverable
        without access to the source code.
        """
        return self.model_dump_json()

    def apply(self, curated_df: pd.DataFrame) -> pd.DataFrame:
        """Transform a curated OBD DataFrame into a processed DataFrame.

        Parameters
        ----------
        curated_df : pd.DataFrame
            DataFrame with raw OBD column names (CURATED_COLS subset).
            Produced by ``OBDFile.curated_df``.

        Returns
        -------
        pd.DataFrame
            Processed DataFrame with columns:
            elapsed_s, smooth_speed_kmh, acc_ms2, speed_kmh,
            co2_g_per_km, engine_load_pct, fuel_flow_lph.

        Raises
        ------
        ValueError
            If any column required by this pipeline is absent from *curated_df*.
        """
        from drive_cycle_calculator._schema import CURATED_COLS, OBD_COLUMN_MAP

        missing = [c for c in CURATED_COLS if c not in curated_df.columns]
        if missing:
            raise ValueError(
                f"ProcessingConfig.apply() received a DataFrame missing required "
                f"column(s): {missing}. Pass a DataFrame produced by OBDFile.curated_df."
            )

        gps_dt = curated_df["GPS Time"]
        if not pd.api.types.is_datetime64_any_dtype(gps_dt):
            gps_dt = pd.to_datetime(gps_dt, errors="coerce", utc=True)
        elapsed_s = (gps_dt - gps_dt.dropna().iloc[0]).dt.total_seconds()

        speed_raw = pd.to_numeric(curated_df["Speed (OBD)(km/h)"], errors="coerce")
        smooth_speed = speed_raw.rolling(
            window=self.window, center=True, min_periods=self.window
        ).mean()
        dt = elapsed_s.diff()
        dt = dt.where(dt > 0)
        acc_ms2 = (smooth_speed / 3.6).diff() / dt

        passthrough = curated_df.rename(columns=OBD_COLUMN_MAP)

        return pd.DataFrame(
            {
                "elapsed_s": elapsed_s,
                "smooth_speed_kmh": smooth_speed,
                "acc_ms2": acc_ms2,
                "speed_kmh": passthrough["speed_kmh"],
                "co2_g_per_km": pd.to_numeric(passthrough["co2_g_per_km"], errors="coerce"),
                "engine_load_pct": pd.to_numeric(passthrough["engine_load_pct"], errors="coerce"),
                "fuel_flow_lph": pd.to_numeric(passthrough["fuel_flow_lph"], errors="coerce"),
            }
        )


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
