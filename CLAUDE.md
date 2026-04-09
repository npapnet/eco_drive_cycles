# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Antigravity when working with code in this repository.

## Project Overview

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data to compute eco-driving scores and synthesize representative drive cycles.

This repo is a **research and prototype repository**. Its primary purpose is to process real-world driving data collected via the Torque app (OBD-II), compute trip metrics, identify representative drive cycles, and ultimately support WLTP-style candidate cycle synthesis.

Raw driving-cycle data (`_data/`, `raw_data/`) was collected via the Torque app and exported as CSV/XLSX. Archived v2 Parquets are in `data/trips/`.

## Running the Code

```bash
# Run the full test suite (129 tests)
uv run pytest

# Launch the GUI example (three modes: import xlsx, load archive, reload catalog)
uv run python examples/gui/main.py

# Ingest raw .xlsx files → v2 archive Parquets + DuckDB catalog
uv run python examples/cli/ingest.py <raw_xlsx_dir> <archive_dir>

# Analyze trips from catalog (similarity scores, representative trip)
uv run python examples/cli/analyze.py <archive_dir>

# Launch the frozen historical DriveGUI (standalone, no package dependencies)
cd students/DriveGUI
python driving_cycles_calculatorV1.py
```

The project uses a **uv workspace** with `ruff` for linting and `pytest` for tests.
Run `uv sync` from the root to install all dependencies.

## Development Priorities

See `TODOS.md` for the full backlog. Current top items:

1. **Clean up remaining legacy code** — `smooth_and_derive()` in `processing_config.py` (marked TODO), `TripCollection.from_parquet()` (deprecated), `OBDFile.to_parquet_optimised()` (broken hardcoded path), duplicate GPS helper functions.
2. **Microtrip segmentation** (`Trip.microtrips`) — the core unit for WLTP-style driving-cycle construction.
3. **Representative microtrip selection** and **candidate cycle assembly** — downstream of segmentation.

When suggesting or making changes: does it belong in `src/drive_cycle_calculator/` (calculation) or `examples/` (thin wrapper)? Never add business logic to `students/DriveGUI/`.

## Architecture

### Package (`src/drive_cycle_calculator/`)

The active calculation layer. All business logic lives here.

```
Raw .xlsx / .csv (OBD-II)
  → OBDFile.from_xlsx() / from_csv()    # load and coerce types
  → OBDFile.to_parquet(path)            # write v2 archive Parquet (permanent)

Archive Parquet
  → TripCollection.from_archive_parquets(dir)   # load + process all trips
  → TripCollection.to_duckdb_catalog(db_path)   # upsert metadata catalog

Catalog
  → TripCollection.from_duckdb_catalog(db_path) # reload instantly
  → tc.similarity_scores()                       # 7-metric scoring
  → tc.find_representative()                     # highest similarity score
  → trip.speed_profile                           # (elapsed_s, smooth_speed_kmh)
```

**File structure:**
```
src/drive_cycle_calculator/
├── __init__.py              — version string only
├── _schema.py               — OBD_COLUMN_MAP, CURATED_COLS
├── gps_time_parser.py       — GpsTimeParser
├── obd_file.py              — OBDFile
├── processing_config.py     — ProcessingConfig, DEFAULT_CONFIG
├── trip.py                  — Trip
└── trip_collection.py       — TripCollection, similarity(), _SEVEN_METRIC_KEYS
```

**Key classes:**
- **`OBDFile(df, name)`** — wraps one raw OBD recording. Constructors: `from_xlsx`, `from_csv`, `from_parquet`. Key methods: `to_parquet` (v2 format), `curated_df`, `quality_report`, `to_trip(config)`.
- **`ProcessingConfig(window=4, stop_threshold_kmh=2.0)`** — controls the processing pipeline. `apply(curated_df)` produces processed DataFrame. `config_hash` stored in DuckDB for reproducibility.
- **`Trip(df, name, stop_threshold_kmh)`** — one processed session. `@cached_property` metrics: `mean_speed`, `mean_acceleration`, `mean_deceleration`, `stop_pct`, `stop_count`, `duration`, `mean_speed_no_stops`, `max_speed`. `_path` set by constructors for lazy loading.
- **`TripCollection`** — groups multiple trips. Constructors: `from_folder`, `from_folder_raw`, `from_archive_parquets`, `from_duckdb_catalog`. Methods: `to_duckdb_catalog`, `similarity_scores`, `find_representative`.

**Processed DataFrame columns** (output of `ProcessingConfig.apply()`):
`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, `co2_g_per_km`, `engine_load_pct`, `fuel_flow_lph`.

> Note: `speed_ms`, `acceleration_ms2`, `deceleration_ms2` no longer exist in the processed output. `Trip.metrics` still has a fallback for old v1 data, but no new code should produce those columns.

**Required OBD-II columns (CURATED_COLS):**
`GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km (Average)(g/km)`, `Engine Load(%)`, `Fuel flow rate/hour(l/hr)`

### Frozen Historical Reference (`students/DriveGUI/`)

⚠️ **FROZEN** — do not add package imports or new features here. This is a self-contained historical reference implementation. It must run standalone forever regardless of package API changes.

```
Raw .xlsx (OBD-II)
  → calculations.py          # Cleans & derives metrics → writes calculations_log_*.xlsx
  → <metric>_chart.py (×13)  # Each reads the log and renders a Matplotlib chart
```

Output column names stay Greek (`Διάρκεια (sec)`, `Ταχ m/s`, etc.) as expected by the 13 visualization modules.

### Examples (`examples/`)

Thin wrappers over `TripCollection`. No business logic.

- `examples/cli/ingest.py` — two-stage ingest: `from_folder_raw` → `OBDFile.to_parquet` per file → `from_archive_parquets` → `to_duckdb_catalog`
- `examples/cli/analyze.py` — load from catalog → print similarity scores + representative trip
- `examples/gui/main.py` — Tkinter + Matplotlib GUI with scrollable log pane. Three modes:
  1. **Import raw xlsx → write archive** (new data)
  2. **Load existing archive parquets** (already-archived data)
  3. **Reload from catalog** (instant, no file I/O)

### Data (`_data/`, `raw_data/`, `data/`)

- `raw_data/` — raw xlsx files from Torque app (source of truth before archiving)
- `data/trips/` — v2 archive Parquets (permanent source of truth after archiving)
- `data/metadata.duckdb` — DuckDB catalog (`trip_metadata` table)
- `_data/complete_extract/` — older CSVs organised by driver name

**Known data-quality issues:**
- Galatas file: repeated header rows (potential corruption)
- Stefanakis dataset: inconsistent column names across files
- Kalyvas/9.9.24: different format than other sessions
- Separator (`,`, `;`, `\t`) and decimal separator (`,` vs `.`) vary across files

## Language convention

**Package (`src/`):** all internal column names are **English** (`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, etc.). Mapping from raw OBD names happens in `_schema.OBD_COLUMN_MAP` via `ProcessingConfig.apply()`.

**DriveGUI (`students/DriveGUI/`):** all column names remain **Greek** (`Διάρκεια (sec)`, `Ταχ m/s`, etc.) because the 13 visualization modules depend on them. Do not change these.

## Key Documentation

- `docs/designs/obd-file-processing-config.md` — current pipeline design (classes, columns, DuckDB schema)
- `students/DriveGUI/ARCHITECTURE.md` — module-by-module documentation for the frozen DriveGUI
- `students/DriveGUI/PROCESSING_LOGIC.md` — mathematical formulas and filtering details
- `brainstorming/data_schema/data_schema.md` — Entity-Relationship Diagram for the full system
- `brainstorming/data_schema/FUEL_EKO_wars.dbml` — DBML schema (target PostgreSQL/Supabase)
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
