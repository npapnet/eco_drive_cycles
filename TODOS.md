# Immediate steps

## P2 — GUI Parquet path fix
- **Domain:** GUI / UX
- **Effort:** S | **Impact:** H | **ROI:** High
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** The GUI's Parquet path loading is currently broken (`FileNotFoundError`) due to incorrect path resolution of `parquet_name` under the new layout convention. We need to fix it so that trips can be loaded and viewed in the interactive GUI.
* **The 'What' (Execution):** Update GUI file loader in `src/drive_cycle_calculator/cli/gui.py` to resolve Parquet paths using the `ProjectLayout` or `parquet_name` scheme correctly.
* **Targets:** `src/drive_cycle_calculator/cli/gui.py`.

---

## P2 — DBSCANClusterer + additional clustering algorithms
- **Domain:** Analysis / Package API
- **Effort:** M | **Impact:** H | **ROI:** High
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** Users want alternative clustering methods like DBSCAN that don't require pre-specifying the number of clusters (which K-Means does).
* **The 'What' (Execution):** Implement `DBSCANClusterer` (under `clustering.py` satisfying `Clusterer` Protocol) and support additional clustering options like `AgglomerativeClusterer`.
* **Targets:** `src/drive_cycle_calculator/clustering.py`.

---

# ✅ Done in this sprint

## P1 — Candidate Cycle Assembly
- **Domain:** Analysis / Cycle Synthesis
- **Status:** ✅ Done
- **Dependencies:** Representative microtrip selection ✓ prototyped in workflow (`060`/`062`)

* **The 'Why' (Value):** This is the project's primary research deliverable — a synthetic representative driving cycle assembled from microtrip building blocks that statistically matches fleet-level metrics.
* **The 'What' (Execution):** Defined a modular transition-matrix and Frobenius distance-driven cycle synthesis algorithm. Integrated WLTP phase-based and cluster-based paths into a unified `synthesis/` subpackage.
* **Targets:** `src/drive_cycle_calculator/synthesis/`.

## P1 — Modular In-Place Workflow (Single-Argument Ingest)
**Domain:** CLI / UX
**Status:** ✅ Done
**Dependencies:** None

* **The 'Why' (Value):** The two-argument `dcc ingest <raw_dir> <out_dir>` is a legacy of a centralized repository model. Researchers expect to keep processed artifacts alongside their raw data.
* **The 'What' (Execution):** If `dcc ingest` (or other CLI subcommands) receives a single directory argument, it acts on it as a project directory with standard subdirectories (`raw/`, `trips/`, `microtrips/`, `reports/`, `analyses/`).
* **Targets:** `src/drive_cycle_calculator/cli/`.

## P2 — Representative Microtrip Selection (Promote to Package)
- **Domain:** Analysis / Package API
- **Status:** ✅ Done
- **Dependencies:** v0.4 refactor ✓ shipped. Workflow prototype ✓ `060`/`062` scripts.

* **The 'Why' (Value):** Promoting to the package makes representative microtrip selection testable, importable, and reusable across datasets.
* **The 'What' (Execution):** Implemented `MicrotripCollection.rank()` supporting pluggable similarity measures (`pct_deviation`, `z_score_distance`, `cosine_similarity`).
* **Targets:** `src/drive_cycle_calculator/microtrip_collection.py`.

## P3 — Microtrip Export to Parquet (Promote to Package)
- **Domain:** Package API / Persistence
- **Status:** ✅ Done
- **Dependencies:** v0.4 refactor ✓ shipped. Workflow prototype ✓ `03_build_microtrips.py`.

* **The 'Why' (Value):** Writes per-microtrip Parquets (processed columns only) and `summary.csv`.
* **The 'What' (Execution):** Added `Microtrip.to_parquet()`, `from_parquet()`, and `export_collection()` to encapsulate persistence.
* **Targets:** `src/drive_cycle_calculator/microtrip.py`, `segmentation.py`.

## v-a Density Cloud and Canonical Profile Visualisation
- **Domain:** Visualisation / Cluster Validation
- **Status:** ✅ Done
- **Dependencies:** None

* **The 'Why' (Value):** Joint velocity-acceleration (v-a) probability density matrices are the industry standard for drive cycle fingerprinting.
* **The 'What' (Execution):** Developed custom hexbin and comparison visualizations (`050_*.py`, `051_*.py`, `062_*.py`).
* **Targets:** `examples/workflow/050_*.py`, `051_*.py`, `062_*.py`.


# 📥 Triage & Next Steps

## P2 — First-Batch Data Quality Audit
- **Domain:** Data Engineering / Quality
- **Effort:** S | **Impact:** M | **ROI:** Medium
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** The first batch (Galatas, Stefanakis, Kalyvas, Ladikas) was collected without standardized specs. Without an audit, the same quality issues (missing columns, format mismatches, separator/decimal inconsistencies) will recur with each new batch.
* **The 'What' (Execution):**
  - Run `scripts/migrate_to_archive.py` against `raw_data/`. Document which files fail, which columns are missing/malformed, and the spread per driver.
  - Write `notes/data_acquisition_spec.md`: required OBD-II channels, expected dtypes, known Torque export quirks. Reference `CURATED_COLS` as the minimum viable set.
* **Targets:** `scripts/migrate_to_archive.py`, `raw_data/`, new `notes/data_acquisition_spec.md`.

---

## P2 — Smoothing Window Comparison Utility
- **Domain:** Analysis / Signal Processing
- **Effort:** S | **Impact:** L | **ROI:** Medium
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** The `window=4` default was inherited from the student DriveGUI with no empirical basis. Researchers need a quick way to see how metric stability (mean_speed, mean_acc, stop_pct) changes with window size before committing to a `ProcessingConfig`.
* **The 'What' (Execution):**
  - Add `OBDFile.compare_smoothing(windows=[2, 4, 8]) -> pd.DataFrame` that applies `ProcessingConfig(window=w)` for each window and returns a metrics comparison table.
* **Targets:** `src/drive_cycle_calculator/obd_file.py`.

---


## P3 — TripCollection Constructor-Level Filtering
- **Domain:** Package API / Data Loading
- **Effort:** S | **Impact:** L | **ROI:** Low
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** `TripCollection` is a result/container type — filtering belongs at load time, not post-hoc. Not needed for single-driver datasets, but becomes important when the archive contains multiple drivers.
* **The 'What' (Execution):**
  - Add optional filter kwargs to `TripCollection.from_archive_parquets()` (e.g. `user="John"`).
  - Read embedded `ParquetMetadata.user_metadata` to filter before full DataFrame load.
* **Targets:** `src/drive_cycle_calculator/trip_collection.py`.

---

## P3 — Trip Listbox in GUI
- **Domain:** GUI / UX
- **Effort:** S | **Impact:** L | **ROI:** Low
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** The current GUI has no interactive trip selection. A scrollable listbox with click-to-load and representative-trip highlighting would make exploratory analysis more accessible.
* **The 'What' (Execution):**
  - Add a trip listbox panel to `examples/gui/main.py`.
  - Clicking a trip loads its speed profile. Representative trip is visually highlighted.
* **Targets:** `examples/gui/main.py`.

---

# 🧊 Backlog / Architectural Epics

## P2 — Reassess the Role of DuckDB in the Pipeline
- **Domain:** Data Engineering / Persistence Architecture
- **Effort:** M | **Impact:** M | **ROI:** Medium
- **Status:** 🔍 Investigating
- **Dependencies:** Outcome influences Supabase migration (below)

* **The 'Why' (Value):** DuckDB was introduced as a persistent metrics catalog for fast querying without reprocessing Parquets. In practice, its role has eroded:
  - `dcc extract` already exports to CSV/XLSX — metrics are available in open formats without a database.
  - `dcc analyze` uses DuckDB only as a lookup table for Parquet paths, then re-reads Parquets anyway — a round-trip with no benefit at current scale.
  - `dcc ingest` was explicitly decoupled from DuckDB (no catalog write at ingest time).
  - Workflow scripts `03`→`062` never touch the database — they operate entirely on Parquet files and CSV summaries.
* **The 'What' (Execution):**
  1. Determine if any scenario at current or expected scale benefits from DuckDB over loading Parquets directly.
  2. Evaluate whether `dcc analyze` should accept a `trips/` folder directly instead of requiring `metrics.duckdb`.
  3. Consider demoting DuckDB to an optional output format of `dcc extract` (alongside CSV/XLSX) rather than a mandatory intermediate.
  4. Assess whether the planned Supabase migration changes the answer.
* **Targets:** `src/drive_cycle_calculator/cli/extract.py`, `cli/analyze.py`, `trip_collection.py`.

---

## P2 — Revisit CLI Commands Workflow
- **Domain:** CLI / UX / Architecture
- **Effort:** M | **Impact:** H | **ROI:** Medium
- **Status:** 🔍 Investigating
- **Dependencies:** DuckDB reassessment (above)

* **The 'Why' (Value):** Ladikas data processing exposed friction in the `dcc ingest` → `extract` → `analyze` → `gui` pipeline:
  - `extract`: no user-level filtering.
  - `analyze`: output is console-only, unclear which DB/dataset is being used.
  - `gui`: broken Parquet path resolution (`FileNotFoundError`), no data export, no similarity reporting, no filters.
* **The 'What' (Execution):**
  - Converge CLI towards the `examples/workflow/` model: timestamped analysis folders (`dcca-<YYYYMMDD-HHMM>/`), file-based reports (Markdown + CSV), config-driven design.
  - The workflow pipeline (`01`→`062`) is the de-facto reference implementation. CLI commands should adopt its patterns.
  - Fix `gui.py` Parquet path resolution bug.
  - Add `--output-dir` and `--user` filter flags to relevant commands.
* **Targets:** `src/drive_cycle_calculator/cli/` (all subcommands), `examples/workflow/` (reference).

---

## P2 — Supabase Migration Script
- **Domain:** Data Engineering / Cloud Persistence
- **Effort:** M | **Impact:** M | **ROI:** Low
- **Status:** 🏗️ Todo
- **Dependencies:** ~~Parquet + DuckDB persistence~~ ✓ proven. Blocked by DuckDB reassessment outcome.

* **The 'Why' (Value):** Cloud persistence enables multi-user, multi-device access to the trip catalog. Prerequisite for any future web-based dashboard.
* **The 'What' (Execution):**
  - Write `scripts/migrate_to_postgres.py`: read `metadata.duckdb` → write to a Supabase/PostgreSQL `trips` table.
* **Targets:** New `scripts/migrate_to_postgres.py`.

---

## P3 — SQL-Backed Similarity Scoring (Fast Path)
- **Domain:** Analysis / Performance
- **Effort:** S | **Impact:** L | **ROI:** Low
- **Status:** 🏗️ Todo
- **Dependencies:** ~~Parquet + DuckDB persistence~~ ✓. Blocked by DuckDB reassessment — if DuckDB is removed, this task is moot.

* **The 'Why' (Value):** Current `TripCollection.similarity_scores()` triggers N `pd.read_parquet()` calls on first invocation. Fine at 5–20 trips; at 500+ trips this is slow. The 7 metrics are already stored in the DuckDB catalog.
* **The 'What' (Execution):**
  - Add an optional fast path that reads pre-computed metrics directly from the DuckDB catalog instead of loading all DataFrames.
* **Targets:** `src/drive_cycle_calculator/trip_collection.py`.

---

## P2 — Handle Different Column Names Across OS and Apps
- **Domain:** Data Engineering / Ingestion
- **Effort:** M | **Impact:** H | **ROI:** High
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** Different OSes (iOS vs Android) and different apps (Torque vs others) export different column headers. For instance, Fytros iPhone data has `time`, `Vehicle speed (km/h)`, `Longtitude` instead of `GPS Time`, `Speed (OBD)(km/h)`, `Longitude`. We need a robust translation layer to map incoming data formats to the standardized `CURATED_COLS` expected by `OBDFile` to avoid manual pre-processing.
* **The 'What' (Execution):**
  - Implement a mapping mechanism (e.g., a dictionary or configuration file) that defines aliases for core columns.
  - Apply this mapping automatically in `OBDFile` constructors (`from_csv`, `from_xlsx`) before validating columns.
* **Targets:** `src/drive_cycle_calculator/obd_file.py`, `src/drive_cycle_calculator/schema.py`.

---

