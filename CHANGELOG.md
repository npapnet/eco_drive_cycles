# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-04-19

### Added
- `schema.py` — Pydantic models for the v0.3 metadata schema:
  `FuelType`, `VehicleCategory` (enums); `UserMetadata`, `IngestProvenance`,
  `ComputedTripStats`, `ParquetMetadata` (provenance-grouped containers);
  `ProcessingConfig` (migrated from `@dataclass`); `generate_yaml_template()`.
- `ProcessingConfig.config_snapshot` — `model_dump_json()` string stored in DuckDB
  alongside `config_hash` so past configs are recoverable without source code.
- `OBDFile.from_file(path, strict=True, **kwargs)` — dispatches to `from_xlsx` or
  `from_csv` by extension. Used by `dcc ingest`.
- `OBDFile.parquet_name` property — canonical archive stem
  `t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>`. `to_trip()` sets `Trip.name` to this
  value so DuckDB `trip_id` aligns with the Parquet filename.
- `OBDFile.to_parquet()` now accepts `user_metadata: UserMetadata` and embeds a
  full `ParquetMetadata` JSON blob under PyArrow key `b"dcc_metadata"`.
- `OBDFile.get_metrics(config=None)` — convenience wrapper: `to_trip().metrics`
  merged with spatial metadata dict.
- Fuel unit fallback in `OBDFile.__init__`: synthesizes `Fuel flow rate/hour(l/hr)`
  from `Fuel Rate (direct from ECU)(L/m)` (×60) or `Fuel flow rate/hour(gal/hr)`
  (×3.78541) when the primary column is absent.
- `OBDFile(strict=True)` parameter — strict mode (default, CLI always uses it)
  raises `ValueError` on missing `CURATED_COLS`; permissive mode (`strict=False`)
  injects NaN columns for library/debug use.
- `cli/` sub-package with five fully-implemented subcommands:
  - `dcc config-init <folder> [--force]` — writes `metadata-<folder>.yaml` template
    from `UserMetadata` field descriptions; adds `sep`/`decimal` ingest-settings block.
  - `dcc ingest <raw_dir> <out_dir> [--format] [--sep] [--decimal]` — discovers and
    validates `metadata-<folder>.yaml` via Pydantic; archives raw files to
    `<out_dir>/trips/` as v2 Parquets with embedded `ParquetMetadata`; no DuckDB.
  - `dcc extract <data_dir> [-o duckdb|csv|xlsx] [--window] [--stop-threshold]
    [--from DATE] [--to DATE] [--lat-min/max] [--lon-min/max]` — reads archive
    Parquets, applies `ProcessingConfig`, writes `trip_metrics` table.
  - `dcc analyze <data_dir>` — loads `metrics.duckdb`, prints similarity scores and
    representative trip stats.
  - `dcc gui` — launches the tkinter GUI.
- `TripCollection.from_duckdb_catalog()` now auto-detects whether the DB contains
  `trip_metrics` (new schema) or `trip_metadata` (legacy schema) and queries accordingly.

### Changed
- `ProcessingConfig` migrated from `@dataclass` to Pydantic `BaseModel` in `schema.py`.
  `processing_config.py` is now a re-export shim (`from schema import ProcessingConfig`
  + `DEFAULT_CONFIG`). Public API unchanged.
- `OBDFile.to_trip()` now uses `self.parquet_name` (not `self.name`) as `Trip.name`
  so that archive paths and DuckDB `trip_id` values are consistent.
- DuckDB output from `dcc extract` uses table name `trip_metrics` (not `trip_metadata`)
  and includes all `UserMetadata` fields flattened as columns.
- Package version bumped from `0.0.2.0` → `0.1.0`.

### Removed
- `OBDFile.to_parquet_optimised()` — removed (was incomplete, hardcoded output path).

## [0.0.2.0] - 2026-04-07

### Fixed
- `ProcessingConfig.apply()`: acceleration (`acc_ms2`) now guards against `dt=0`
  (duplicate Torque timestamps) and `dt<0` (out-of-order rows). Previously, a
  duplicate-timestamp pair produced `±inf` in `acc_ms2`, which propagated silently
  into DuckDB catalog metrics and corrupted similarity scoring.
- `ProcessingConfig.apply()`: `acc_ms2` was already divided by the real inter-sample
  interval `dt` (not assumed 1 Hz), but the `dt ≤ 0` edge case was unguarded.
- `TripCollection.from_archive_parquets()`: exception handling now catches any
  load failure (including corrupt/truncated Parquet files that raise `ArrowInvalid`),
  not just `ValueError` from the v1-format check.
- `TripCollection.from_duckdb_catalog()`: same broadening — corrupt archive Parquets
  are now warned-and-skipped rather than aborting the full collection load.
- `TripCollection.from_duckdb_catalog()`: `trip._path` is now set on each loaded
  `Trip`, so re-saving to a catalog correctly records the archive path.
- `stop_threshold_kmh` from `ProcessingConfig` is now forwarded through
  `OBDFile.to_trip()` → `Trip.__init__` → `_compute_session_metrics`, so custom
  stop thresholds actually affect `stop_pct` and `stops` metrics.
- Removed dead imports from `trip_collection.py` (`_compute_session_metrics`,
  `_infer_sheet_name`, `_process_raw_df`) and unused `import io` from `obd_file.py`.

### Changed
- `TripCollection.to_parquet()` and `TripCollection.from_parquet()` now emit
  `DeprecationWarning` at call time (in addition to their existing docstring notes).
  Use `OBDFile.to_parquet()` + `TripCollection.from_archive_parquets()` instead.

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
