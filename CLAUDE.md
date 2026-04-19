# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Antigravity when working with code in this repository.

## Project Overview

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data to compute eco-driving scores and synthesize representative drive cycles.

This repo is a **research and prototype repository**. Its primary purpose is to process real-world driving data collected via the Torque app (OBD-II), compute trip metrics, identify representative drive cycles, and ultimately support WLTP-style candidate cycle synthesis.

Raw driving-cycle data (`_data/`, `raw_data/`) was collected via the Torque app and exported as CSV/XLSX. Archived v2 Parquets are in `data/trips/`.

## Running the Code

```bash
# Run the full test suite
uv run pytest

# Ingest raw .xlsx/.csv files → v2 archive Parquets (no DuckDB)
uv run dcc ingest <raw_dir> <out_dir>

# Generate metadata template for a folder before ingesting
uv run dcc config-init <raw_dir>

# Extract metrics from archive Parquets → DuckDB / CSV / XLSX
uv run dcc extract <data_dir>

# Analyze trips from DuckDB (similarity scores, representative trip)
uv run dcc analyze <data_dir>

# Launch the GUI
uv run dcc gui
```

The project uses a **uv workspace** with `ruff` for linting and `pytest` for tests.
Run `uv sync` from the root to install all dependencies.

## Development Priorities

See `TODOS.md` for the full backlog. Current top items:

1. **v0.3 refactor** — see `docs/designs/refactor_v0.3.md` for the full design doc.
   Key changes: metadata schema (Pydantic), ingest/extract decoupling, canonical trip
   identity, `OBDFile` strictness. This is the active sprint.
2. **Microtrip segmentation** (`Trip.microtrips`) — core unit for WLTP-style cycle construction.
3. **Representative microtrip selection** and **candidate cycle assembly** — downstream of segmentation.

When suggesting or making changes: does it belong in `src/drive_cycle_calculator/`
(calculation) or `examples/` (thin wrapper)? Never add business logic to `students/DriveGUI/`.

## Architecture

### Package (`src/drive_cycle_calculator/`)

The active calculation layer. All business logic lives here.

**Target pipeline (post v0.3 refactor):**

```
Raw .xlsx / .csv (OBD-II)
  → dcc config-init <folder>              # generate metadata-<folder>.yaml template
  [user fills in metadata-<folder>.yaml]
  → dcc ingest <raw_dir> <out_dir>        # raw file → v2 archive Parquet with embedded metadata
                                          # NO DuckDB created here

Archive Parquet (self-contained: raw data + ParquetMetadata)
  → dcc extract <data_dir>               # read parquets → apply ProcessingConfig → output
  → DuckDB / CSV / XLSX (trip_metrics)   # metrics + metadata + config snapshot

DuckDB (trip_metrics table)
  → dcc analyze <data_dir>               # similarity scores, representative trip
```

**File structure:**
```
src/drive_cycle_calculator/
├── __init__.py              — version string only
├── _schema.py               — OBD_COLUMN_MAP, CURATED_COLS
├── schema.py                — Pydantic models (NEW in v0.3): FuelType, VehicleCategory,
│                              UserMetadata, IngestProvenance, ComputedTripStats,
│                              ParquetMetadata, ProcessingConfig (migrated from dataclass)
├── gps_time_parser.py       — GpsTimeParser
├── obd_file.py              — OBDFile
├── processing_config.py     — DEFAULT_CONFIG (ProcessingConfig class moved to schema.py)
├── trip.py                  — Trip
└── trip_collection.py       — TripCollection, similarity(), _SEVEN_METRIC_KEYS
```

**Key classes:**

- **`OBDFile(df, name, strict=True)`** — wraps one raw OBD recording.
  Constructors: `from_xlsx`, `from_csv`, `from_parquet` — all accept `strict: bool = True`.
  - Strict mode (default, always used by CLI): missing curated columns → `ValueError`.
  - Permissive mode (`strict=False`, library/debug use only): missing columns → NaN injected.
  Key methods: `to_parquet(path, user_metadata)` (v2 format with embedded `ParquetMetadata`),
  `curated_df`, `quality_report`, `to_trip(config)`, `parquet_name` (canonical filename stem).

- **`ProcessingConfig(window=4, stop_threshold_kmh=2.0)`** — Pydantic `BaseModel` (was dataclass).
  `config_hash` property: md5 of sorted JSON fields.
  `config_snapshot` property: `model_dump_json()` — full field values as JSON string.
  Stored in DuckDB `trip_metrics` table alongside computed metrics.

- **`Trip(df, name, stop_threshold_kmh)`** — one processed session. `@cached_property`
  metrics: `mean_speed`, `mean_acceleration`, `mean_deceleration`, `stop_pct`,
  `stop_count`, `duration`, `mean_speed_no_stops`, `max_speed`.

- **`TripCollection`** — groups multiple trips. Constructors: `from_folder`,
  `from_archive_parquets`. Methods: `similarity_scores`, `find_representative`.
  `to_duckdb_catalog` is **removed** — DuckDB is now produced by `dcc extract`.

**Pydantic metadata models (all in `schema.py`):**

Grouped by provenance — each model reflects *who or what is responsible* for its fields:

- **`UserMetadata`** — declared by the user via `metadata-<folder>.yaml`. All fields
  `Optional`. Enum-validated fields: `fuel_type` (`FuelType`), `vehicle_category`
  (`VehicleCategory`). Free-form: `user`, `vehicle_make`, `vehicle_model`,
  `engine_size_cc`, `year`, `misc`.
- **`IngestProvenance`** — recorded by the ingest process: `ingest_timestamp`,
  `source_filename`.
- **`ComputedTripStats`** — derived from raw GPS signal: `start_time`, `end_time`,
  `gps_lat_mean`, `gps_lat_std`, `gps_lon_mean`, `gps_lon_std`.
- **`ParquetMetadata`** — root container: `schema_version`, `software_version`,
  `parquet_id` (6-char GPS hash), plus the three sub-models above.
  Embedded in every archive Parquet under PyArrow key `"dcc_metadata"` as JSON.

**Parquet filename convention:**
`t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>.parquet`
where `hash6 = sha256(lat_bytes + lon_bytes)[:6]`.
Use `obd.parquet_name` everywhere. `obd.name` (raw filename stem) is NOT used for
Parquet filenames or DuckDB keys.

**DuckDB table:** `trip_metrics` (produced by `dcc extract`, not by ingest).
One row per trip. Columns: `trip_id`, `parquet_path`, `parquet_id`, `start_time`,
`end_time`, all `UserMetadata` fields flattened, GPS stats, trip scalar metrics,
`config_hash`, `config_snapshot`.

**Processed DataFrame columns** (output of `ProcessingConfig.apply()`):
`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, `co2_g_per_km`,
`engine_load_pct`, `fuel_flow_lph`.

> Note: `speed_ms`, `acceleration_ms2`, `deceleration_ms2` no longer exist in the
> processed output. No new code should produce those columns.

**Required OBD-II columns (CURATED_COLS):**
`GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km (Average)(g/km)`, `Engine Load(%)`,
`Fuel flow rate/hour(l/hr)`

### CLI Subcommands

| Subcommand | Status | Description |
|------------|--------|-------------|
| `dcc config-init <folder>` | New (v0.3) | Write `metadata-<folder>.yaml` template |
| `dcc ingest <raw_dir> <out_dir>` | Revised (v0.3) | Raw → archive Parquet. No DuckDB. |
| `dcc extract <data_dir>` | New (v0.3) | Parquets → DuckDB / CSV / XLSX with metrics |
| `dcc analyze <data_dir>` | Unchanged | Similarity analysis from DuckDB |
| `dcc gui` | Bug-fix (v0.3) | Uses `parquet_name` scheme |

### Frozen Historical Reference (`students/DriveGUI/`)

⚠️ **FROZEN** — do not add package imports or new features or change something here
unless explicitly asked. Self-contained historical reference. Must run standalone
forever regardless of package API changes.

```
Raw .xlsx (OBD-II)
  → calculations.py          # Cleans & derives metrics → writes calculations_log_*.xlsx
  → <metric>_chart.py (×13)  # Each reads the log and renders a Matplotlib chart
```

### Examples (`examples/`)

Thin wrappers and scratchpads. Not guaranteed to be up to date with the current CLI.

The examples folder contains scripts that act as tutorials for new users, or they are
used as proof-of-concept scripts for testing new ideas. They are not part of the core
package and may not be maintained rigorously.

If a script in the docstring is marked as "OBSOLETE", it means that the functionality it provided has been replaced by a more robust or integrated solution within the package. 
In that case,offer to update the example scripts to use a similar approach as the new CLI subcommands instead of the old workflow.

### Data (`_data/`, `raw_data/`, `data/`)

- `raw_data/` — raw xlsx/csv files from Torque app (source of truth before archiving)
- `data/trips/` — v2 archive Parquets (permanent source of truth after archiving)
- `data/metrics.duckdb` — DuckDB metrics output (`trip_metrics` table), produced by
  `dcc extract`
- `_data/complete_extract/` — older CSVs organised by driver name

**Known data-quality issues:**
- Galatas file: repeated header rows (potential corruption)
- Stefanakis dataset: inconsistent column names across files
- Kalyvas/9.9.24: different format than other sessions
- Separator (`,`, `;`, `\t`) and decimal separator (`,` vs `.`) vary across folders (usually)

## Language convention

**Package (`src/`):** all internal column names are **English** (`elapsed_s`,
`smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, etc.). Mapping from raw OBD names happens
in `_schema.OBD_COLUMN_MAP` via `ProcessingConfig.apply()`.

**DriveGUI (`students/DriveGUI/`):** FROZEN — DO NOT CHANGE.

## Key Documentation

- `docs/designs/refactor_v0.3.md` — **ACTIVE**: authoritative design doc for the
  current v0.3 sprint. Treat this as ground truth for the refactor.
- `brainstorming/refactor-proposals/clarification-v0.3.md` — codebase audit report
  produced before the v0.3 refactor; documents the pre-refactor architecture and
  known inconsistencies. Useful context but describes the old state.
- `brainstorming/` — contains future work and design ideas which are not yet mature.
  Do not rely on these being up to date or accurate, but they may provide useful
  context or inspiration.
- `docs/designs/` — design docs; may be stale after each version iteration except
  the currently active one.
- `DATA.md` — data collection notes and Google Drive link
- `TODOS.md` — prioritised backlog

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health