# TODOS

## P1 - Simplify Trip Dataframe Creation in Tests

**What:**: consider using a conftest.py fixture that generates a simple, valid Trip DataFrame for testing purposes. This would eliminate the need for manually constructing DataFrames in each test case, reducing boilerplate and improving readability. 

**Why:** Many tests currently construct Trip DataFrames from scratch, which can be verbose and error-prone. A fixture would centralize this logic, making it easier to maintain and update the test data structure as needed.


## P1 — Representative microtrip selection

**What:** `TripCollection.find_representative_microtrip() -> Microtrip` using the same 7-metric similarity scoring but at microtrip granularity.

**Effort:** S (human: ~4 hrs / CC: ~10 min)

**Depends on:** Microtrip segmentation ✓ landed (2026-04-23, branch `feature/microtrips`).

---

## P1 — Candidate cycle assembly

**What:** Assemble a synthetic representative driving cycle from a sequence of representative microtrips. Output: a time-series speed profile that matches the overall fleet statistics.

**Effort:** M (human: ~2 days / CC: ~30 min)

**Depends on:** Representative microtrip selection (P1).

---

## P2 — First-batch data quality audit + future acquisition spec

**What:** Run `scripts/migrate_to_archive.py` against the first batch of raw data (Galatas, Stefanakis, Kalyvas, Ladikas) and document which files fail, which columns are missing or malformed, and what the spread of issues is per driver. Then define a minimum column spec for future data acquisition sessions.

**Why:** The first batch was collected without standardized specs. Without this, the same quality issues will recur with each new batch.

**How to apply:** Run migration script against `raw_data/`. Review the `SKIP` output. Write `docs/data_acquisition_spec.md` listing: required OBD-II channels, expected dtypes, known Torque export quirks. Reference `CURATED_COLS` as the minimum viable set.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

---

## P2 — `OBDFile.compare_smoothing(windows=[2, 4, 8])`

**What:** Method on `OBDFile` that applies `ProcessingConfig(window=w)` for each window size and returns a DataFrame of key metrics (mean_speed, mean_acc, stop_pct) per window. Useful for choosing the right smoothing parameter before committing to a `ProcessingConfig`.

**Why:** The `window=4` default was inherited from the student DriveGUI. No empirical basis. Researchers need a quick way to see how metric stability changes with window size.

**Where:** `src/drive_cycle_calculator/obd_file.py`

**Effort:** S (human: ~1 hr / CC: ~10 min)

---


## P2 — Fix stop_percentage unit-detection heuristic (DriveGUI only)

**What:** `stop_percentage.py:72` and `total_stop_percentage.py:85` in `students/DriveGUI/` silently multiply all-stop sessions by 3.6, producing wrong results for any session where all speed values are legitimately below 2.0 km/h.

**Where:** `students/DriveGUI/stop_percentage.py:72`, `total_stop_percentage.py:85`

**Effort:** S (human: ~2 hrs / CC: ~10 min)

---

## P2 — Supabase migration script

**What:** `scripts/migrate_to_postgres.py` — reads `metadata.duckdb` and writes to a Supabase/PostgreSQL `trips` table.

**Effort:** M (human: ~1 day / CC: ~20 min)

**Depends on:** Parquet + DuckDB persistence proven in practice ✓.

---

## P2 — Deduplicate similarity scoring in DriveGUI speed_profile.py

**What:** `compute_speed_profile()` in `students/DriveGUI/metrics.py` uses its own inline 2-metric selection while `find_representative_sheet()` uses 7 metrics. They can return different sessions — a scientific correctness issue.

**Where:** `students/DriveGUI/metrics.py:272`

**Effort:** S (human: ~1 hr / CC: ~5 min)

---

## P3 — Trip listbox in examples/gui/

**What:** Show all trips in a scrollable listbox in `examples/gui/main.py`. Clicking a trip loads its speed profile. Representative trip is highlighted.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

---

## P3 — SQL-backed similarity scoring (fast path for large catalogs)

**What:** Optional fast path for `TripCollection.similarity_scores()` that reads pre-computed metrics directly from the DuckDB catalog instead of loading all DataFrames.

**Why:** Current approach triggers N `pd.read_parquet()` calls on first invocation. Fine at 5–20 trips. At 500+ trips this is slow; the 7 metrics are already stored in the catalog.

**Effort:** S (human: ~4 hrs / CC: ~15 min)

**Depends on:** Parquet + DuckDB persistence layer ✓.


# DONE

## ~~P1 — Microtrip segmentation~~ ✓ DONE (2026-04-23, branch `feature/microtrips`)

**Shipped:**
- `schema.py` — `SegmentationConfig` Pydantic model (stop/duration/distance thresholds).
- `microtrip.py` — `Microtrip` Pydantic model with weakref data access (D1: no parquet reload fallback).
- `segmentation.py` — `SegmentBoundary` dataclass, `detect_boundaries()`, `build_microtrips()`.
- `trip.py` — `parquet_id` param, `data`/`file` public properties, `segment(config)` method.
- `obd_file.py` — `to_trip()` now passes `parquet_id`.
- `tests/test_segmentation.py` — 38 tests covering boundary detection, object construction, filtering, data access, and degenerate inputs.
- Spec archived at `docs/designs/archive/microtrip_design_spec.md`.

---

## ~~P2 — CLI entry point~~ ✓ DONE

All five subcommands shipped as part of the v0.3 refactor (package v0.1.0):
`dcc config-init`, `dcc ingest`, `dcc extract`, `dcc analyze`, `dcc gui`.
`dcc extract` goes beyond the original spec — supports `--output duckdb|csv|xlsx`,
date filters, and GPS centroid filters.

---

## ~~P1 — Clean up remaining legacy code (to_parquet_optimised)~~ ✓ DONE

`OBDFile.to_parquet_optimised()` removed. `OBDFile.to_parquet(path, user_metadata)`
is the canonical path and now embeds `ParquetMetadata` JSON.

---

## ~~v0.3 refactor~~ ✓ DONE

**Shipped in package v0.1.0 (2026-04-19):**
- `schema.py` — Pydantic metadata models (`UserMetadata`, `IngestProvenance`,
  `ComputedTripStats`, `ParquetMetadata`) + `ProcessingConfig` (migrated from `@dataclass`).
- `OBDFile` updated: `from_file()`, `parquet_name`, `strict` mode, fuel unit fallback,
  `to_parquet(user_metadata)` embeds `ParquetMetadata` JSON.
- `processing_config.py` is now a re-export shim.
- Full CLI: `config-init`, `ingest`, `extract`, `analyze`, `gui`.

---

## ~~P1 — OBDFile + ProcessingConfig refactor~~ ✓ DONE

**What:** Two-stage archive pipeline. `OBDFile` wraps a raw OBD xlsx/CSV/Parquet file.
`ProcessingConfig` (dataclass with `window` and `stop_threshold_kmh`) applies smoothing,
acceleration derivation, and column renaming via `apply(curated_df)`. `DEFAULT_CONFIG`
is `ProcessingConfig(window=4)`.

**Shipped:**
- `src/drive_cycle_calculator/_schema.py` — `OBD_COLUMN_MAP`, `CURATED_COLS`
- `src/drive_cycle_calculator/gps_time_parser.py` — `GpsTimeParser`
- `src/drive_cycle_calculator/obd_file.py` — `OBDFile.from_xlsx/from_csv/from_parquet`, `to_parquet` (v2 format), `curated_df`, `quality_report`, `to_trip`
- `src/drive_cycle_calculator/processing_config.py` — `ProcessingConfig`, `config_hash`, `DEFAULT_CONFIG`
- `src/drive_cycle_calculator/trip_collection.py` — `TripCollection` extracted from `trip.py`; adds `from_folder_raw`, `from_archive_parquets`, `from_duckdb_catalog` (eager via OBDFile)
- `scripts/migrate_to_archive.py` — one-shot xlsx → v2 Parquet converter
- `examples/cli/ingest.py` — two-stage ingest workflow
- 129 tests passing

**Processed DataFrame columns** (output of `ProcessingConfig.apply()`):
`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, `co2_g_per_km`, `engine_load_pct`, `fuel_flow_lph`.
Note: `speed_ms`, `acceleration_ms2`, `deceleration_ms2` were removed as redundant.

---

## ~~P1 — Remove legacy code from _computations.py~~ ✓ DONE

**Removed:** `process_raw_df()`, `load_raw_df()`, `smooth_and_derive()`, `_SEVEN_METRIC_KEYS`,
`_REQUIRED_RAW_COLS` from `_computations.py`. `_similarity_calcs.py` module folded into
`trip_collection.py`. `similarity()` and `_SEVEN_METRIC_KEYS` now live in `trip_collection.py`.

**Remaining in `_computations.py`:** None. Completely deleted after migrating `gps_to_duration_seconds()` to `GpsTimeParser`.

---

## ~~P2~~ → ~~P1 — Migrate internal column names from Greek to English~~ ✓ DONE

Internal package code uses English column names. DriveGUI Excel output remains Greek (user-facing).

---

## ~~P1 — Parquet + DuckDB persistence layer~~ ✓ DONE

**Current storage layout:**
```
data/
  trips/
    trackLog-2019-Sep-16_10-58-16.parquet   # v2 archive (raw OBD columns)
    trackLog-2019-Sep-16_18-45-06.parquet
    …
  metadata.duckdb                           # catalog: trip_metadata table
```

`TripCollection.from_archive_parquets()` is the canonical constructor.
`TripCollection.from_parquet()` (v1 processed Parquets) is deprecated, kept for backward compat.

---

## ~~P1 — Examples directory (CLI + GUI)~~ ✓ DONE

- `examples/cli/ingest.py` — two-stage ingest: `from_folder_raw` → `OBDFile.to_parquet` → `from_archive_parquets` → `to_duckdb_catalog`
- `examples/cli/analyze.py` — loads from catalog → prints similarity scores + representative trip
- `examples/gui/main.py` — Tkinter + Matplotlib GUI with scrollable log pane; three buttons:
  "Import raw xlsx → write archive", "Load existing archive parquets", "Reload from catalog"
- `examples/README.md`, `examples/cli/README.md`, `examples/gui/README.md`

---

## ~~P2 — Freeze DriveGUI and restore self-sufficiency~~ ✓ DONE

`students/DriveGUI/` is frozen. No imports from `src/drive_cycle_calculator`. See `students/DriveGUI/README.md` for the FROZEN notice.

---

## ~~P1 — Remove os.chdir() from short_excel.py~~ ✓ DONE

---

## ~~~P1 — Clean up remaining legacy code~~~ ✓ DONE

1. **`smooth_and_derive()` in `processing_config.py`** — marked `TODO: Remove from codebase`. Used only by `TestSmoothAndDerive` in `test_processing_config.py`. Both the function and its test class should be deleted.
2. **`_computations.gps_to_duration_seconds()`** — near-duplicate of `misc._gps_to_duration_seconds()`. Replaced with GpsTimeParser Class
3. **`misc.py` housekeeping** — completely deleted after migrating date parsers to `GpsTimeParser`.
4. **`TripCollection.from_parquet()`** — deprecated, reads old v1 processed Parquets. No tests reference it except backward-compat ones. Remove method and update any remaining tests.