---
status: ACTIVE
promoted_from: ~/.gstack/projects/npapnet-eco_drive_cycles/ceo-plans/2026-04-07-obd-file-processing-config.md
last_updated: 2026-04-19
---
# Design: OBDFile + ProcessingConfig Pipeline (v0.3 / package v0.1.0)

> This document describes the **current implementation** of the drive cycle data pipeline.
> It is kept up to date with the source code in `src/drive_cycle_calculator/`.

---

## Overview

The pipeline is split into two stages:

```
Stage 1 — ARCHIVE  (write once, replaces raw xlsx as source of truth)
  *.xlsx / *.csv
    → OBDFile.from_file() / from_xlsx() / from_csv()
    → ALL columns preserved, dash → NaN coerced
    → OBDFile.to_parquet(path, user_metadata)
    → *.parquet  ← permanent archive (v2, with embedded ParquetMetadata JSON)

Stage 2 — ANALYSIS  (derived on demand from archive)
  *.parquet
    → OBDFile.from_parquet()
    → OBDFile.to_trip(config)  (uses curated_df internally)
    → Trip(processed_df, name)
    → TripCollection.similarity_scores(), find_representative()
    → dcc extract: trip_metrics table (DuckDB / CSV / XLSX)
```

Raw xlsx/csv files are never re-read after archiving. The archive Parquet is
the permanent source of truth; processed DataFrames are always derived from it.
`dcc ingest` never touches DuckDB. `dcc extract` reads Parquets and writes metrics.

---

## File Structure

```
src/drive_cycle_calculator/
├── __init__.py              — version string + re-exports (OBDFile, Trip, TripCollection)
├── _schema.py               — OBD_COLUMN_MAP, CURATED_COLS  (no package imports)
├── schema.py                — Pydantic models: FuelType, VehicleCategory, UserMetadata,
│                              IngestProvenance, ComputedTripStats, ParquetMetadata,
│                              ProcessingConfig (migrated from @dataclass),
│                              generate_yaml_template()
├── gps_time_parser.py       — GpsTimeParser
├── obd_file.py              — OBDFile
├── processing_config.py     — re-export shim: ProcessingConfig + DEFAULT_CONFIG
├── trip.py                  — Trip
├── trip_collection.py       — TripCollection, similarity(), _SEVEN_METRIC_KEYS
└── cli/
    ├── main.py              — Typer root app; registers all subcommands
    ├── config_init.py       — dcc config-init
    ├── ingest.py            — dcc ingest
    ├── extract.py           — dcc extract
    ├── analyze.py           — dcc analyze
    └── gui.py               — dcc gui
```

---

## Schema (`_schema.py`)

Dependency-free constants imported by both `obd_file.py` and `schema.py`.

```python
CURATED_COLS = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO₂ in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]

OBD_COLUMN_MAP = {
    "Speed (OBD)(km/h)":              "speed_kmh",
    "CO₂ in g/km (Average)(g/km)":   "co2_g_per_km",
    "Engine Load(%)":                 "engine_load_pct",
    "Fuel flow rate/hour(l/hr)":      "fuel_flow_lph",
}
# Note: "GPS Time" is consumed → elapsed_s, not renamed.
```

---

## Pydantic Models (`schema.py`)

All metadata models live in `schema.py`. Grouped by provenance — each model reflects
*who or what is responsible* for its fields.

### Enums

```python
class FuelType(str, Enum):
    PETROL | DIESEL | E10 | E85 | HYBRID | ELECTRIC | LPG | OTHER

class VehicleCategory(str, Enum):
    SEDAN | SUV | HATCHBACK | VAN | TRUCK | MOTORCYCLE | OTHER
```

### `UserMetadata`

Declared by the user via `metadata-<folder>.yaml`. All fields `Optional`.

| Field | Type | Description |
|-------|------|-------------|
| `fuel_type` | `FuelType \| None` | Enum-validated fuel type |
| `vehicle_category` | `VehicleCategory \| None` | Body style enum |
| `user` | `str \| None` | Driver identifier |
| `vehicle_make` | `str \| None` | e.g. Toyota |
| `vehicle_model` | `str \| None` | e.g. Yaris |
| `engine_size_cc` | `int \| None` | Engine displacement |
| `year` | `int \| None` | Model year |
| `misc` | `dict \| None` | Any additional key-value pairs |

### `IngestProvenance`

Recorded by `dcc ingest`. Not user-supplied.

| Field | Type |
|-------|------|
| `ingest_timestamp` | `datetime` (UTC) |
| `source_filename` | `str` |

### `ComputedTripStats`

Derived from the raw GPS signal during ingest.

| Field | Type |
|-------|------|
| `start_time` | `datetime \| None` |
| `end_time` | `datetime \| None` |
| `gps_lat_mean` | `float` |
| `gps_lat_std` | `float` |
| `gps_lon_mean` | `float` |
| `gps_lon_std` | `float` |

### `ParquetMetadata`

Root container embedded in every archive Parquet under PyArrow key `b"dcc_metadata"` as JSON.

| Field | Type |
|-------|------|
| `schema_version` | `str` (currently `"1.0"`) |
| `software_version` | `str` (package `__version__`) |
| `parquet_id` | `str` (6-char sha256 of GPS lat+lon bytes; falls back to sha256 of `name`) |
| `ingest_provenance` | `IngestProvenance` |
| `computed_trip_stats` | `ComputedTripStats` |
| `user_metadata` | `UserMetadata` |

### `generate_yaml_template(model_class)`

Utility in `schema.py`. Generates a commented YAML template from a Pydantic model's
field descriptions. Used by `dcc config-init`.

---

## `OBDFile` (`obd_file.py`)

Wraps a single raw OBD recording. Holds the **complete unprocessed** DataFrame
(all columns, dash → NaN coercion). Processing is done on demand via `to_trip()`.

### Constructor parameters

```python
OBDFile(df, name, strict=True)
```

Column names are stripped of surrounding whitespace at construction time.

`strict=True` (default, always used by CLI): missing `CURATED_COLS` → `ValueError`.
`strict=False` (library/debug only): missing columns → NaN injected, warning emitted.

### Fuel unit fallback (in `__init__`)

If `"Fuel flow rate/hour(l/hr)"` is absent, `__init__` attempts in order:
1. `"Fuel Rate (direct from ECU)(L/m)"` × 60 → synthesizes `l/hr` column
2. `"Fuel flow rate/hour(gal/hr)"` × 3.78541 → synthesizes `l/hr` column
3. Else: strict mode raises `ValueError`, permissive mode injects NaN.

### Constructors

| Method | Source |
|--------|--------|
| `OBDFile.from_xlsx(path, strict=True)` | Raw xlsx from Torque app. All columns preserved. |
| `OBDFile.from_csv(path, sep=None, decimal=None, strict=True)` | Raw CSV. Sep auto-detected via `csv.Sniffer` on first 20 lines. Decimal inferred by scanning for `\d+,\d+` pattern. |
| `OBDFile.from_parquet(path, strict=True)` | v2 archive Parquet. Raises `ValueError` if `smooth_speed_kmh` is present (v1 processed format). |
| `OBDFile.from_file(path, strict=True, **kwargs)` | Dispatches by extension (`.xlsx`/`.xls` → `from_xlsx`; `.csv` → `from_csv`). |

### Methods / Properties

| Name | Description |
|------|-------------|
| `to_parquet(path, user_metadata=None, use_dictionary=False)` | Writes full archive with PyArrow schema metadata `format_version=b"2"` and `b"dcc_metadata"=<ParquetMetadata JSON>`. Compression: zstd, Parquet version 2.6. |
| `parquet_name` | Property: canonical stem `t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>`. Falls back to `self.name` if GPS Time absent/unparseable. |
| `curated_df` | Property: `CURATED_COLS` subset of raw DataFrame. |
| `full_df` | Property: full raw DataFrame copy. |
| `quality_report()` | Returns dict: `row_count`, `missing_pct` (per column), `dash_count` (per column), `gps_gap_count`, `speed_outlier_count`, `speed_min_kmh`, `speed_max_kmh`, `missing_curated_cols`. |
| `to_trip(config=DEFAULT_CONFIG)` | Raises `ValueError` if any `CURATED_COL` absent. Calls `config.apply(self.curated_df)`. `Trip.name` is set to `self.parquet_name`. |
| `get_metrics(config=None)` | Convenience: `to_trip(config).metrics` merged with spatial metadata dict. |
| `name` | Raw filename stem (e.g. `"trackLog-2019-Sep-16_10-58-16"`). Used for display only — not for Parquet filenames or DuckDB keys. |

### Parquet format versioning

- **v1** (old): processed format — contains `smooth_speed_kmh`. `from_parquet()` raises `ValueError` on detection.
- **v2** (current): raw archive — all original OBD columns. PyArrow schema metadata: `format_version=b"2"` + `b"dcc_metadata"=<JSON>`.

---

## `ProcessingConfig` (`schema.py`, re-exported from `processing_config.py`)

Migrated from `@dataclass` to Pydantic `BaseModel` in v0.3.

```python
class ProcessingConfig(BaseModel):
    window: int = 4                  # rolling window for speed smoothing (samples)
    stop_threshold_kmh: float = 2.0  # speed below which a sample is "stopped"
```

### Properties

| Property | Description |
|----------|-------------|
| `config_hash` | First 8 hex chars of `md5(json.dumps(model_dump(), sort_keys=True))`. Stored in DuckDB for reproducibility auditing. |
| `config_snapshot` | `model_dump_json()` — full field values as compact JSON. Stored in DuckDB alongside hash. |

### `apply(curated_df) → pd.DataFrame`

Transforms a `CURATED_COLS` DataFrame into a processed DataFrame:

| Column | Source |
|--------|--------|
| `elapsed_s` | GPS Time → UTC datetime → seconds from first valid timestamp |
| `smooth_speed_kmh` | `Speed (OBD)(km/h)` → `rolling(window, center=True, min_periods=window).mean()` |
| `acc_ms2` | `(smooth_speed_kmh / 3.6).diff() / dt`. `dt ≤ 0` masked to NaN (guards duplicate/reversed timestamps). |
| `speed_kmh` | `Speed (OBD)(km/h)` renamed (raw, unsmoothed) |
| `co2_g_per_km` | `CO₂ in g/km (Average)(g/km)` renamed + `pd.to_numeric(..., errors="coerce")` |
| `engine_load_pct` | `Engine Load(%)` renamed + coerced |
| `fuel_flow_lph` | `Fuel flow rate/hour(l/hr)` renamed + coerced |

> `speed_ms`, `acceleration_ms2`, and `deceleration_ms2` do not exist. Acceleration is a single signed `acc_ms2`.

```python
DEFAULT_CONFIG = ProcessingConfig()   # window=4, stop_threshold_kmh=2.0
# Lives in processing_config.py (re-export shim)
```

---

## `Trip` (`trip.py`)

One processed driving session.

```python
Trip(df: pd.DataFrame | None, name: str, stop_threshold_kmh: float = 2.0)
```

`df` may be `None` if `_path` is set — lazy-loaded from Parquet on first access.
`Trip.name` is set to `OBDFile.parquet_name` so DuckDB `trip_id` values align with archive Parquet filenames.

### Computed columns expected

`Trip` reads the columns produced by `ProcessingConfig.apply()`:

| Property | Column read |
|----------|-------------|
| `mean_speed` | `smooth_speed_kmh.mean()` |
| `mean_acceleration` | `acc_ms2.where(> 0).mean()` |
| `mean_deceleration` | `acc_ms2.where(< 0).mean()` |
| `max_speed` | `smooth_speed_kmh.max()` |
| `speed_profile` | `(elapsed_s, smooth_speed_kmh)` |
| `duration` | `elapsed_s.max()` |

### Seven metrics (used for similarity scoring)

```python
trip.metrics  # → dict with keys:
{
    "duration":   float,   # seconds
    "mean_speed": float,   # km/h (including stops)
    "mean_ns":    float,   # km/h (moving only, speed > stop_threshold_kmh)
    "stops":      int,     # row count at or below stop threshold
    "stop_pct":   float,   # % of rows that are stops
    "mean_acc":   float,   # mean positive acc_ms2 (m/s²)
    "mean_dec":   float,   # mean negative acc_ms2 (m/s²)
}
```

---

## `TripCollection` (`trip_collection.py`)

Groups multiple `Trip` objects. Canonical entry point for multi-trip analysis.

### Constructors

| Method | Description |
|--------|-------------|
| `TripCollection([trip1, trip2, …])` | Direct construction from existing `Trip` objects. |
| `TripCollection.from_folder(folder, config=DEFAULT_CONFIG)` | Loads each `*.xlsx` via `OBDFile.from_xlsx() → to_trip(config)`. Skips unreadable files with `warnings.warn()`. |
| `TripCollection.from_folder_raw(folder) → list[OBDFile]` | Returns plain `list[OBDFile]` (not a `TripCollection`). Use for data-quality inspection before archiving. |
| `TripCollection.from_archive_parquets(directory, config=DEFAULT_CONFIG)` | Loads each `*.parquet` via `OBDFile.from_parquet() → to_trip(config)`. Sets `trip._path`. |
| `TripCollection.from_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` | Reads `trip_metrics` (or legacy `trip_metadata`) table; loads each trip eagerly. |

### Methods

| Method | Description |
|--------|-------------|
| `to_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` | **Legacy path** — creates/upserts `trip_metadata` table. Prefer `dcc extract` (writes `trip_metrics` with full `UserMetadata` columns). |
| `similarity_scores() → dict[str, float]` | Mean similarity score (0–100) per trip name versus collection average across all 7 metrics. |
| `find_representative() → Trip` | Returns the trip with the highest similarity score. |

### DuckDB table: `trip_metrics` (produced by `dcc extract`)

```sql
CREATE TABLE IF NOT EXISTS trip_metrics (
    trip_id              VARCHAR PRIMARY KEY,
    parquet_path         VARCHAR,
    parquet_id           VARCHAR,
    start_time           TIMESTAMPTZ,
    end_time             TIMESTAMPTZ,
    user                 VARCHAR,
    fuel_type            VARCHAR,
    vehicle_category     VARCHAR,
    vehicle_make         VARCHAR,
    vehicle_model        VARCHAR,
    engine_size_cc       INTEGER,
    year                 INTEGER,
    gps_lat_mean         DOUBLE,
    gps_lon_mean         DOUBLE,
    duration_s           DOUBLE,
    avg_velocity_kmh     DOUBLE,
    max_velocity_kmh     DOUBLE,
    avg_acceleration_ms2 DOUBLE,
    avg_deceleration_ms2 DOUBLE,
    idle_time_pct        DOUBLE,
    stop_count           INTEGER,
    config_hash          VARCHAR,
    config_snapshot      VARCHAR
)
```

> The legacy `trip_metadata` table (written by `TripCollection.to_duckdb_catalog()`) has a different schema — no `UserMetadata` columns, no `config_snapshot`, no `parquet_id`. `from_duckdb_catalog()` detects the table name automatically.

---

## Interactive Research Usage

```python
from drive_cycle_calculator import OBDFile, TripCollection
from drive_cycle_calculator.schema import ProcessingConfig

# ── Inspect raw files before archiving ───────────────────────────────────────
raw_files = TripCollection.from_folder_raw("./raw_data/")  # list[OBDFile]
for f in raw_files:
    report = f.quality_report()
    print(f.name, report["missing_curated_cols"], report["speed_outlier_count"])
    f.to_parquet(f"./data/trips/{f.parquet_name}.parquet")

# ── Build trip collection from archives ───────────────────────────────────────
tc = TripCollection.from_archive_parquets("./data/trips/")
print(tc.find_representative())

# ── Try different smoothing windows ───────────────────────────────────────────
config_8 = ProcessingConfig(window=8)
tc_smooth = TripCollection.from_archive_parquets("./data/trips/", config=config_8)
```

---

## `examples/` CLI and GUI

### `examples/gui/main.py`

Three-button tkinter GUI with a scrollable log pane:

1. **Import raw xlsx → write archive** — `from_folder_raw()` → `OBDFile.to_parquet()` per file
2. **Load existing archive parquets** — picks a folder of v2 Parquets → `from_archive_parquets()`
3. **Reload from catalog** — `from_duckdb_catalog()` (instant, no file reprocessing)

### `examples/cli/ingest.py`

Thin wrapper demonstrating the two-stage workflow:

```python
raw_files = TripCollection.from_folder_raw(raw_dir)
for f in raw_files:
    f.to_parquet(archive_dir / f"{f.parquet_name}.parquet")
tc = TripCollection.from_archive_parquets(archive_dir)
```

> **Note:** These example scripts may lag behind the CLI. The canonical workflow is `dcc ingest` → `dcc extract` → `dcc analyze`.

---

## Known Gaps / TODOs

| # | Item | Location |
|---|------|----------|
| 1 | `Trip.microtrips` raises `NotImplementedError` — P1 in TODOS.md | `trip.py` |
| 2 | `Trip.date` / `Trip.session` parse by splitting on `"_"`, which breaks with the new `t<YYYYMMDD-...>` `parquet_name` scheme | `trip.py` |
