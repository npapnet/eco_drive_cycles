# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data to compute eco-driving scores.

This repo is a **knowledge base**, not a product repo. Its primary purpose is to consolidate, understand, and refine early-stage student work related to the Fuel Eco Wars concept. The student contributions (mainly `students/DriveGUI/`) represent a first working prototype that needs significant refinement before it can serve as a reliable foundation for further development.

Raw driving-cycle data (`_data/`) was collected via the Torque app and exported as CSV/XLSX.

## Running the Code

```bash
# Run the full test suite (124 tests)
uv run pytest

# Launch the new GUI example (ingest → catalog → speed profile chart)
python examples/gui/main.py

# Ingest raw .xlsx files into Parquet + DuckDB catalog
python examples/cli/ingest.py <raw_xlsx_dir> <output_dir>

# Analyze trips from catalog (similarity scores, representative trip)
python examples/cli/analyze.py <output_dir>

# Launch the frozen historical DriveGUI (standalone, no package dependencies)
cd students/DriveGUI
python driving_cycles_calculatorV1.py
```

The project uses a **uv workspace** with `ruff` for linting and `pytest` for tests. Run `uv sync` from the root to install all dependencies.

## Development Priorities

The separation of calculation from presentation is complete. The package (`src/drive_cycle_calculator/`) holds all computation logic. `students/DriveGUI/` is frozen as a historical reference.

Current priorities (see `TODOS.md` for full backlog):

1. **OBDFile + ProcessingConfig refactor** — two-stage archive pipeline. Design finalized at `docs/designs/obd-file-processing-config.md`. Implementation next.
2. **Microtrip segmentation** (`Trip.microtrips`) — the core unit for WLTP-style driving-cycle construction.
3. **Representative microtrip selection** and **candidate cycle assembly** — downstream of segmentation.
4. **Fix stop_percentage heuristic** — silent wrong-result bug in `students/DriveGUI/stop_percentage.py:72` and `total_stop_percentage.py:85`.

When suggesting or making changes: does it belong in `src/drive_cycle_calculator/` (calculation) or `examples/` (presentation)? Never add business logic to `students/DriveGUI/`.

## Architecture

### Package (`src/drive_cycle_calculator/`)

The active calculation layer. All business logic lives here.

```
Raw .xlsx (OBD-II)
  → TripCollection.from_folder(dir)   # processes all .xlsx in a directory
  → TripCollection.to_parquet(dir)    # writes one .parquet per trip
  → TripCollection.to_duckdb_catalog(db_path)  # upserts metadata catalog

Later:
  → TripCollection.from_duckdb_catalog(db_path)  # lazy-load trip stubs
  → tc.similarity_scores()            # 7-metric scoring (all trips vs fleet avg)
  → tc.find_representative()          # argmax of similarity scores
  → trip.speed_profile()              # DataFrame: elapsed_s + smooth_speed_kmh
```

Key classes:
- **`Trip(df, name)`** — wraps one processed DataFrame. `_df` is lazy-loaded from `_path` if `df=None`. `@cached_property` metrics: `mean_speed`, `mean_acc`, `mean_dec`, `stop_pct`, `duration`, `num_stops`, `mean_speed_moving`, `max_speed`.
- **`TripCollection`** — spans multiple trips. `from_folder()`, `from_excel()`, `from_parquet()`, `from_duckdb_catalog()` constructors. `to_parquet()` and `to_duckdb_catalog()` persistence.

Internal column names are English: `elapsed_s`, `speed_ms`, `smooth_speed_kmh`, `acceleration_ms2`, `deceleration_ms2`.

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

- `examples/cli/ingest.py` — ingest raw .xlsx → Parquet + DuckDB
- `examples/cli/analyze.py` — load from catalog → print similarity scores + representative trip
- `examples/gui/main.py` — Tkinter + Matplotlib GUI: folder picker → ingest → catalog → speed profile

### Data (`_data/`)

- `complete_extract/` — CSVs organised by driver name (ladikas, kalyvas, stefanakis, galatas, …)
- `load_file.py` — CSV parsing helpers
- Primary dataset is on Google Drive (see `DATA.md` for link); local files are a subset

**Known data-quality issues**:
- Galatas file: repeated header rows (potential corruption)
- Stefanakis dataset: inconsistent column names across files
- Kalyvas/9.9.24: different format than other sessions
- Separator (``,``, `;``, ``\t``) and decimal separator (``,`` vs ``.``) vary across files

### Required OBD-II columns (input XLSX)

`GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km (Average)(g/km)`, `Engine Load(%)`, `Fuel flow rate/hour(l/hr)`

## Key Documentation

- `students/DriveGUI/ARCHITECTURE.md` — module-by-module documentation for the frozen DriveGUI
- `students/DriveGUI/PROCESSING_LOGIC.md` — mathematical formulas and filtering details
- `brainstorming/data_schema/data_schema.md` — Entity-Relationship Diagram for the full system
- `brainstorming/data_schema/FUEL_EKO_wars.dbml` — DBML schema (target PostgreSQL/Supabase)
- `DATA.md` — data collection notes and Google Drive link
- `examples/README.md` — how to use the CLI and GUI examples
- `TODOS.md` — prioritised backlog

## Language Note

**Package (`src/`):** all internal column names are **English** (`elapsed_s`, `speed_ms`, `smooth_speed_kmh`, `acceleration_ms2`, `deceleration_ms2`). Renaming happens at entry points via `COLUMN_MAP` in `_computations.py`.

**DriveGUI (`students/DriveGUI/`):** all column names remain **Greek** (`Διάρκεια (sec)`, `Ταχ m/s`, etc.) because the 13 visualization modules depend on them. Do not change these.

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
