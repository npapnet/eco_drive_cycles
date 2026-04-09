---
status: ACTIVE
promoted_from: ~/.gstack/projects/npapnet-eco_drive_cycles/ceo-plans/2026-04-07-obd-file-processing-config.md
---
# Design: OBDFile + ProcessingConfig Pipeline

> This document describes the **current implementation** of the drive cycle data pipeline.
> It is kept up to date with the source code in `src/drive_cycle_calculator/`.

---

## Overview

The pipeline is split into two stages:

```
Stage 1 — ARCHIVE  (write once, replaces raw xlsx as source of truth)
  *.xlsx / *.csv
    → OBDFile.from_xlsx() / from_csv()
    → ALL columns preserved, dash → NaN coerced
    → OBDFile.to_parquet()
    → *.parquet  ← permanent archive

Stage 2 — ANALYSIS  (derived on demand from archive)
  *.parquet
    → OBDFile.from_parquet()
    → OBDFile.curated_df  (CURATED_COLS subset)
    → ProcessingConfig.apply()
    → Trip(processed_df, name)
    → TripCollection.similarity_scores(), find_representative()
    → DuckDB: trip_metadata (metrics + config_hash + parquet_path)
```

Raw xlsx/csv files are never re-read after archiving. The archive Parquet is
the permanent source of truth; processed DataFrames are always derived from it.

---

## File Structure

```
src/drive_cycle_calculator/
├── __init__.py              — version string only
├── _schema.py               — OBD_COLUMN_MAP, CURATED_COLS  (no package imports)
├── gps_time_parser.py       — Converts GPS time in various forms to datetime objects and duration seconds
├── obd_file.py              — OBDFile
├── processing_config.py     — ProcessingConfig, DEFAULT_CONFIG
├── trip.py                  — Trip
└── trip_collection.py       — TripCollection, similarity()
```

---

## Schema (`_schema.py`)

Dependency-free constants imported by both `obd_file.py` and `processing_config.py`.

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

## `OBDFile` (`obd_file.py`)

Wraps a single raw OBD recording. Holds the **complete unprocessed** DataFrame
(all columns, dash → NaN coerced). Processing is done on demand via `to_trip()`.

### Constructors

| Method | Source |
|--------|--------|
| `OBDFile.from_xlsx(path)` | Raw xlsx from Torque app. All columns preserved. Dash → NaN coerced for numeric columns. |
| `OBDFile.from_csv(path, sep=None, decimal=None)` | Raw CSV. Separator auto-detected via `csv.Sniffer` on first 20 lines. Decimal separator inferred by scanning first non-null numeric cell for `,`. |
| `OBDFile.from_parquet(path)` | v2 archive Parquet. Raises `ValueError` if `smooth_speed_kmh` is present (indicates old v1 processed format). |

### Methods / Properties

| Name | Description |
|------|-------------|
| `to_parquet(path)` | Writes full archive with PyArrow schema metadata `format_version="2"`. |
| `curated_df` | Property: returns `CURATED_COLS` subset of raw DataFrame. Missing cols silently omitted. |
| `full_df` | Property: returns full raw DataFrame copy. |
| `quality_report()` | Returns dict with 8 keys: `row_count`, `missing_pct`, `dash_count`, `gps_gap_count`, `speed_outlier_count`, `speed_min_kmh`, `speed_max_kmh`, `missing_curated_cols`. |
| `to_trip(config=DEFAULT_CONFIG)` | Raises `ValueError` if any `CURATED_COL` is absent. Calls `config.apply(self.curated_df)` and returns `Trip(processed_df, self.name, stop_threshold_kmh=config.stop_threshold_kmh)`. |
| `name` | Inferred from filename stem (e.g. `"trackLog-2019-Sep-16_10-58-16"`). |

### Parquet format versioning

- **v1** (old): processed format — contains `smooth_speed_kmh`, `speed_ms`, `acceleration_ms2`, etc. `from_parquet()` raises `ValueError` on detection.
- **v2** (current): raw archive — all original OBD columns. PyArrow schema metadata includes `format_version=b"2"`.

---

## `ProcessingConfig` (`processing_config.py`)

```python
@dataclasses.dataclass
class ProcessingConfig:
    window: int = 4                  # rolling window for speed smoothing (samples)
    stop_threshold_kmh: float = 2.0  # speed below which a sample is "stopped"
```

### `apply(curated_df) → pd.DataFrame`

Transforms a `CURATED_COLS` DataFrame (from `OBDFile.curated_df`) into a
processed DataFrame with exactly these columns:

| Column | Source |
|--------|--------|
| `elapsed_s` | GPS Time → `_gps_to_duration_seconds()` → elapsed seconds from first valid timestamp |
| `smooth_speed_kmh` | `Speed (OBD)(km/h)` → `rolling(window, center=True, min_periods=window).mean()` |
| `acc_ms2` | Full signed acceleration: `(smooth_speed_kmh / 3.6).diff() / dt`. Duplicate/reversed timestamps masked to NaN. |
| `speed_kmh` | `Speed (OBD)(km/h)` renamed via `OBD_COLUMN_MAP` (raw, unsmoothed) |
| `co2_g_per_km` | `CO₂ in g/km (Average)(g/km)` renamed, `pd.to_numeric(..., errors="coerce")` |
| `engine_load_pct` | `Engine Load(%)` renamed + coerced |
| `fuel_flow_lph` | `Fuel flow rate/hour(l/hr)` renamed + coerced |

> **Note:** `speed_ms`, `acceleration_ms2`, and `deceleration_ms2` are **not produced**.
> They were redundant columns from the v1 pipeline and have been removed.
> Acceleration is a single signed `acc_ms2` column (positive = acceleration, negative = braking).

### `config_hash`

`cached_property` — first 8 hex chars of `md5(json.dumps(dataclasses.asdict(self), sort_keys=True))`.
Stored in the DuckDB catalog for reproducibility auditing.

```python
DEFAULT_CONFIG = ProcessingConfig()   # window=4, stop_threshold_kmh=2.0
```

---

## `Trip` (`trip.py`)

One processed driving session.

```python
Trip(df: pd.DataFrame | None, name: str, stop_threshold_kmh: float = 2.0)
```

`df` may be `None` if `_path` is set — lazy-loaded from Parquet on first access
(used by `from_archive_parquets()` and `from_duckdb_catalog()` to set `trip._path`).

### Computed columns expected

`Trip` reads the columns produced by `ProcessingConfig.apply()`:

| Property | Column read | Fallback |
|----------|-------------|---------|
| `mean_speed` | `smooth_speed_kmh` | `speed_ms * 3.6` (old pipeline compat) |
| `mean_acceleration` | `acc_ms2.where(> 0).mean()` | `acceleration_ms2` (old pipeline compat) |
| `mean_deceleration` | `acc_ms2.where(< 0).mean()` | `deceleration_ms2` (old pipeline compat) |
| `max_speed` | `smooth_speed_kmh.max()` | `NaN` if column absent |
| `speed_profile` | `(elapsed_s, smooth_speed_kmh)` | raises `RuntimeError` if absent |
| `duration` | `elapsed_s.max()` | `NaN` |

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
| `TripCollection.from_archive_parquets(directory, config=DEFAULT_CONFIG)` | Loads each `*.parquet` via `OBDFile.from_parquet() → to_trip(config)`. Sets `trip._path` for DuckDB catalog use. |
| `TripCollection.from_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` | Reads `trip_metadata` table; loads each trip via `OBDFile.from_parquet(parquet_path) → to_trip(config)`. Eagerly loads all trips at construction time. |
| `TripCollection.from_parquet(directory)` ⚠️ | **Deprecated** — loads old v1 processed Parquets directly into `Trip` objects. Use `from_archive_parquets()` instead. |

### Methods

| Method | Description |
|--------|-------------|
| `to_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` | Creates/upserts `trip_metadata` table. Keyed on sanitised trip name. Migrates existing catalogs lacking `config_hash` column via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. |
| `similarity_scores() → dict[str, float]` | Mean similarity score (0–100) per trip name versus the collection average across all 7 metrics. |
| `find_representative() → Trip` | Returns the trip with the highest similarity score. |
| `_sanitise_name(name) → str` | Replaces filesystem-unsafe characters with `_`. Used by `to_duckdb_catalog()`. |

### DuckDB catalog schema (`trip_metadata`)

```sql
CREATE TABLE IF NOT EXISTS trip_metadata (
    trip_id               VARCHAR PRIMARY KEY,
    parquet_path          VARCHAR NOT NULL,
    start_time            TIMESTAMP,
    end_time              TIMESTAMP,
    duration_s            DOUBLE,
    avg_velocity_kmh      DOUBLE,
    max_velocity_kmh      DOUBLE,
    avg_acceleration_ms2  DOUBLE,
    avg_deceleration_ms2  DOUBLE,
    idle_time_pct         DOUBLE,
    stop_count            INTEGER,
    estimated_fuel_liters DOUBLE,
    wavelet_anomaly_count INTEGER,
    markov_matrix_uri     VARCHAR,
    pla_trajectory_uri    VARCHAR,
    config_hash           VARCHAR
)
```

---


## Interactive Research Usage

```python
from drive_cycle_calculator.metrics import TripCollection
from drive_cycle_calculator.processing_config import ProcessingConfig

# ── Inspect raw files before archiving ───────────────────────────────────────
raw_files = TripCollection.from_folder_raw("./raw_data/")  # list[OBDFile]
for f in raw_files:
    report = f.quality_report()
    print(f.name, report["missing_curated_cols"], report["speed_outlier_count"])
    f.to_parquet(f"./data/archive/{f.name}.parquet")

# ── Build trip collection from archives ───────────────────────────────────────
tc = TripCollection.from_archive_parquets("./data/archive/")
print(tc.find_representative())
tc.to_duckdb_catalog("./data/metadata.duckdb")

# ── Reload instantly from catalog ─────────────────────────────────────────────
tc = TripCollection.from_duckdb_catalog("./data/metadata.duckdb")

# ── Try different smoothing windows ───────────────────────────────────────────
config_8 = ProcessingConfig(window=8)
tc_smooth = TripCollection.from_archive_parquets("./data/archive/", config=config_8)
```

---

## `examples/` CLI and GUI

### `examples/gui/main.py`

Three-button tkinter GUI with a scrollable log pane:

1. **Import raw xlsx → write archive** — `from_folder_raw()` → `OBDFile.to_parquet()` per file → `from_archive_parquets()` → `to_duckdb_catalog()`
2. **Load existing archive parquets** — picks a folder of v2 Parquets → `from_archive_parquets()` → `to_duckdb_catalog()`
3. **Reload from catalog** — `from_duckdb_catalog()` (instant, no file reprocessing)

Progress is streamed to a `scrolledtext.ScrolledText` log pane and to stdout
via Python `logging`. Paths are resolved relative to `__file__`, not cwd.

### `examples/cli/ingest.py`

```python
raw_files = TripCollection.from_folder_raw(raw_dir)
for f in raw_files:
    f.to_parquet(archive_dir / f"{f.name}.parquet")
tc = TripCollection.from_archive_parquets(archive_dir)
tc.to_duckdb_catalog(db_path)
```

---

## Known Gaps / TODOs

| # | Item | Location |
|---|------|----------|
| 1 | `OBDFile.to_parquet_optimised()` is incomplete (hardcoded output path, TODO comment) | `obd_file.py` |
| 2 | `Trip.microtrips` raises `NotImplementedError` — P1 in TODOS.md | `trip.py` |


