# Changelog

All notable changes to this project will be documented in this file.

## [0.0.1.0] - 2026-04-07

### Added
- `OBDFile` class (`src/drive_cycle_calculator/obd_file.py`) — wraps a raw OBD
  xlsx/CSV/Parquet file. Constructors: `from_xlsx`, `from_csv`, `from_parquet`.
  Methods: `quality_report()`, `curated_df` (property), `to_parquet()` (v2 archive),
  `to_trip(config)`. CSV ingest auto-detects separator and decimal locale.
- `ProcessingConfig` dataclass (`src/drive_cycle_calculator/processing_config.py`) —
  `window=4`, `stop_threshold_kmh=2.0`. `apply(curated_df)` produces `smooth_speed_kmh`
  and `acc_ms2` in-memory only (no derived columns in persisted Parquets). `config_hash`
  is first 8 chars of MD5 over the config dict. `DEFAULT_CONFIG = ProcessingConfig()`.
- `_schema.py` — dependency-free schema constants: `OBD_COLUMN_MAP`, `CURATED_COLS`,
  `_gps_to_duration_seconds`. Imported by both `obd_file.py` and `processing_config.py`
  to avoid circular imports.
- `TripCollection.from_folder_raw(dir)` — loads all `.xlsx` in a directory as raw
  `OBDFile` objects (no processing). Used for the ingest quality-check pass.
- `TripCollection.from_archive_parquets(dir)` — processes v2 archive Parquets into
  `Trip` objects via `DEFAULT_CONFIG`.
- `TripCollection.from_duckdb_catalog(db_path)` (eager) — loads all archived trips via
  `OBDFile.to_trip()` at catalog-load time.
- `TripCollection.to_duckdb_catalog()` now stores `config_hash` column; existing
  catalogs are migrated via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- `scripts/migrate_to_archive.py` — one-shot batch converter: raw xlsx →
  v2 archive Parquets. Skips files with missing `CURATED_COLS` with a warning.
- `examples/cli/ingest.py` updated for the two-stage workflow: quality check →
  archive Parquets → DuckDB catalog.
- 74 new tests; 199 total passing.
- `load_raw_df(path)` utility function — loads an OBD xlsx file as exported by
  Torque, with no processing applied. Exposes raw column names, dtypes, and
  sensor-off markers (`"-"`) for data-quality inspection before ingest.
  Exported from `drive_cycle_calculator.metrics`.
- `examples/cli-single/inspect_raw.py` — standalone script showing column names,
  dtypes, non-null counts, and dash-placeholder counts for any raw Torque xlsx.
- `examples/cli-single/analyse_single.py` — interactive-window example for
  exploring a single archived parquet file (speed, acceleration, CO₂ plots).
- `brainstorming/concepts/trip_collection_usage.md` — compiled usage patterns for
  `TripCollection` to inform the OBDFile + ProcessingConfig refactor plan.
- `docs/designs/obd-file-processing-config.md` — finalized design document for the
  OBDFile + ProcessingConfig refactor. Covers two-stage pipeline, class specs,
  file structure, test requirements, known issues, and migration script spec.
- Raw data files from first acquisition batch (`raw_data/`) for 14 sessions.

### Fixed
- `_schema._gps_to_duration_seconds`: `from dateutil import parser` moved to module
  level (was inside per-row closure called via `Series.map()`, causing a Python import
  on every element).
- `OBDFile.from_csv`: added test coverage for `ValueError` when separator cannot be
  resolved (`test_undetectable_separator_raises`).
- `_process_raw_df()`: Torque sensor-off cells (`"-"`) in CO₂, Engine Load, and
  Fuel flow columns are now coerced to `float64` (NaN) via `pd.to_numeric`.
  Previously these produced `object`-dtype columns that caused PyArrow to raise
  `ArrowTypeError` on `to_parquet()`.
- `load_raw_df()`: raises `FileNotFoundError` for both missing files and directory
  paths (previously only missing files were guarded).

### Changed
- `TripCollection` extracted from `trip.py` into its own module
  `metrics/trip_collection.py` (one class per file). `trip.py` re-exports
  `TripCollection` for backward compatibility.
- `_computations.py`: `COLUMN_MAP` renamed to `GREEK_COLUMN_MAP`; `COLUMN_MAP` alias
  kept. `_compute_session_metrics` now prefers `smooth_speed_kmh`/`acc_ms2` columns
  with fallback to legacy `acceleration_ms2`/`deceleration_ms2` split columns.
- `metrics/__init__.py`: re-exports `TripCollection` directly alongside `Trip`.
- `TODOS.md`: OBDFile + ProcessingConfig refactor marked DONE. P1 "Rationalise Parquet
  Columns" marked as subsumed. New P2 TODOs added for first-batch data quality audit
  and `OBDFile.compare_smoothing()`.
- `CLAUDE.md`: updated architecture section to reflect current sprint priorities
  and skill routing rules.
- Reorganized `docs/` and `brainstorming/` folder structure — concepts and data
  schema files moved from `docs/` to `brainstorming/` so `docs/` hosts only
  authoritative design documents.
