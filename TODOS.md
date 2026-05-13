# Immediate steps

## P1 — Resampling and Gap-Check During Ingestion
- **Domain:** Data Ingestion / Signal Quality
- **Effort:** S | **Impact:** H | **ROI:** High (Low-Hanging Fruit)
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** Raw OBD data has irregular sampling. A uniform 1 s time base is assumed by all downstream calculations (segmentation uses sample count as a duration proxy at ~1 Hz). Gaps indicate sensor loss or engine restarts and must be flagged.
* **The 'What' (Execution):**
  - Resample raw data to a fixed 1 s frequency in `OBDFile.to_parquet()` before writing the archive Parquet.
  - Add a configurable `max_gap_s` parameter (default 5 s). If exceeded: warn or abort based on a `--strict-gaps` CLI flag.
  - Propagate the parameter through `dcc ingest`.
* **Targets:** `src/drive_cycle_calculator/obd_file.py`, `src/drive_cycle_calculator/cli/ingest.py`.

---

# ✅ Done in this sprint

## v-a Density Cloud and Canonical Profile Visualisation
- **Domain:** Visualisation / Cluster Validation
- **Effort:** M | **Impact:** H | **ROI:** High
- **Status:** ✅ Done
- **Dependencies:** None

* **The 'Why' (Value):** Joint velocity-acceleration (v-a) probability density matrices are the industry standard for drive cycle fingerprinting and representativeness validation (André 2004, Ericsson 2001). Unlike v-t profiles which show individual events, v-a clouds capture aggregate statistical signatures. Standard scatter plots become unreadable with large datasets.
* **The 'What' (Execution):**
  - v-a density hexbin (`050_microtrip_visualisation.py`) — per-cluster hexbin of speed vs. acceleration, with scalability notes for datashader/KDE2D at fleet scale.
  - v-t scatter cloud (`050_microtrip_visualisation.py`) — per-cluster point cloud of (relative time, speed).
  - v-t comparison overlay (`051_microtrip_vis_comparison_vt.py`) — multi-cluster overlay on a single figure.
  - Canonical representative profiles (`062_plot_representatives.py`) — faceted top-N speed profiles per cluster per similarity metric.
* **Targets:** `examples/workflow/050_*.py`, `051_*.py`, `062_*.py`.


# 📥 Triage & Next Steps

## P1 — Candidate Cycle Assembly
- **Domain:** Analysis / Cycle Synthesis
- **Effort:** M | **Impact:** H | **ROI:** High
- **Status:** 🏗️ Todo
- **Dependencies:** ~~Representative microtrip selection~~ ✓ prototyped in workflow (`060`/`062`)

* **The 'Why' (Value):** This is the project's primary research deliverable — a synthetic representative driving cycle assembled from microtrip building blocks that statistically matches fleet-level metrics. Without this, the pipeline stops at clustering.
* **The 'What' (Execution):**
  - Define a cycle-assembly algorithm: select one representative microtrip per cluster, concatenate into a time-series speed profile, validate aggregate statistics (mean speed, stop %, acc/dec) against fleet averages.
  - Prototype as a new workflow script (`07x_assemble_cycle.py`) before promoting to package.
  - Output: time-series DataFrame + summary stats + validation report.
* **Targets:** New `examples/workflow/07x_*.py`, eventually `src/drive_cycle_calculator/cycle_assembly.py`.

---



## P1 — Modular In-Place Workflow (Single-Argument Ingest)
**Domain:** CLI / UX
**Effort:** S | **Impact:** M | **ROI:** High (Low-Hanging Fruit)
**Status:** 🏗️ Todo
**Dependencies:** None

* **The 'Why' (Value):** The two-argument `dcc ingest <raw_dir> <out_dir>` is a legacy of a centralized repository model. Researchers expect to keep processed artifacts alongside their raw data.
* **The 'What' (Execution):**
  - If `dcc ingest` receives a single directory argument, use it for both input and output (creating `trips/`, `microtrips/`, `reports/` subfolders within it).
  - Two-argument form remains supported for backward compatibility.
* **Targets:** `src/drive_cycle_calculator/cli/ingest.py`, `src/drive_cycle_calculator/cli/main.py`.

---

## P2 — Representative Microtrip Selection (Promote to Package)
- **Domain:** Analysis / Package API
- **Effort:** S | **Impact:** M | **ROI:** High (Low-Hanging Fruit)
- **Status:** 🏗️ Todo
- **Dependencies:** ~~v0.4 refactor~~ ✓ shipped. ~~Workflow prototype~~ ✓ `060`/`062` scripts.

* **The 'Why' (Value):** Algorithm is fully proven in workflow staging (`060_select_representatives.py`, `062_plot_representatives.py`). Promoting to the package makes it testable, importable, and reusable across datasets without copy-pasting workflow scripts.
* **The 'What' (Execution):**
  - Extract ranking logic from `060_select_representatives.py` into a new module (e.g. `src/drive_cycle_calculator/microtrip_ranking.py`) or as a method on `TripCollection`.
  - Support the three pluggable similarity measures already implemented: `z_score_distance`, `pct_deviation`, `cosine_similarity`.
  - Export `ranked_microtrips.csv` with `score_<name>` and `rank_<name>` columns per cluster.
  - Add unit tests covering per-cluster ranking and edge cases.
* **Targets:** New `src/drive_cycle_calculator/microtrip_ranking.py` or `trip_collection.py`, `tests/`.

---

## P2 — First-Batch Data Quality Audit
- **Domain:** Data Engineering / Quality
- **Effort:** S | **Impact:** M | **ROI:** Medium
- **Status:** 🏗️ Todo
- **Dependencies:** None

* **The 'Why' (Value):** The first batch (Galatas, Stefanakis, Kalyvas, Ladikas) was collected without standardized specs. Without an audit, the same quality issues (missing columns, format mismatches, separator/decimal inconsistencies) will recur with each new batch.
* **The 'What' (Execution):**
  - Run `scripts/migrate_to_archive.py` against `raw_data/`. Document which files fail, which columns are missing/malformed, and the spread per driver.
  - Write `docs/data_acquisition_spec.md`: required OBD-II channels, expected dtypes, known Torque export quirks. Reference `CURATED_COLS` as the minimum viable set.
* **Targets:** `scripts/migrate_to_archive.py`, `raw_data/`, new `docs/data_acquisition_spec.md`.

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

## P3 — Microtrip Export to Parquet (Promote to Package)
- **Domain:** Package API / Persistence
- **Effort:** S | **Impact:** L | **ROI:** Medium
- **Status:** 🏗️ Todo
- **Dependencies:** ~~v0.4 refactor~~ ✓ shipped. ~~Workflow prototype~~ ✓ `03_build_microtrips.py`.

* **The 'Why' (Value):** Logic is fully proven in workflow. `03_build_microtrips.py` writes per-microtrip Parquets (processed columns + `stop_phase` flag) and `summary.csv`. Microtrip Parquets contain only the processed (curated) columns — they are intermediate disposable artifacts. Promoting to the package makes it a first-class API.
* **The 'What' (Execution):**
  - Extract export logic into a `Microtrip.to_parquet()` method or a utility function in `segmentation.py`.
  - Ensure output schema matches workflow convention: processed columns only + `stop_phase` boolean.
  - Add unit tests.
* **Targets:** `src/drive_cycle_calculator/microtrip.py` or `segmentation.py`, `tests/`.

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

