# Changelog

All notable changes to this project will be documented in this file.

## [0.0.1.0] - 2026-04-07

### Added
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
- `_process_raw_df()`: Torque sensor-off cells (`"-"`) in CO₂, Engine Load, and
  Fuel flow columns are now coerced to `float64` (NaN) via `pd.to_numeric`.
  Previously these produced `object`-dtype columns that caused PyArrow to raise
  `ArrowTypeError` on `to_parquet()`.
- `load_raw_df()`: raises `FileNotFoundError` for both missing files and directory
  paths (previously only missing files were guarded).

### Changed
- `TODOS.md`: P1 "Rationalise Parquet Columns" marked as subsumed by the
  OBDFile + ProcessingConfig refactor. New P2 TODOs added for first-batch data
  quality audit and `OBDFile.compare_smoothing()`.
- `CLAUDE.md`: updated architecture section to reflect current sprint priorities
  and skill routing rules.
- Reorganized `docs/` and `brainstorming/` folder structure — concepts and data
  schema files moved from `docs/` to `brainstorming/` so `docs/` hosts only
  authoritative design documents.
