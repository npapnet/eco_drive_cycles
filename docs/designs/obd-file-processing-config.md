---
status: ACTIVE
promoted_from: ~/.gstack/projects/npapnet-eco_drive_cycles/ceo-plans/2026-04-07-obd-file-processing-config.md
---
# Design: OBDFile + ProcessingConfig Refactor
Reviewed 2026-04-07 | Branch: refactor_drive_gui | Mode: SELECTIVE_EXPANSION

---

## Problem

`TripCollection.from_folder()` bakes in `window=4` smoothing silently and discards
raw OBD data. Researchers cannot apply different processing without modifying source.
The Parquet files store PROCESSED data (smooth_speed_kmh, speed_ms, a(m/s2), etc.)
which:
1. Has redundant columns (`speed_ms = smooth_speed_kmh / 3.6` exactly)
2. Cannot be re-processed with different smoothing without re-ingesting from xlsx
3. Has baked-in algorithm choices (window size) with no record of what was used

---

## Two-Stage Pipeline

```
Stage 1 — ARCHIVE (write once, replaces originals)
  xlsx / CSV
    → OBDFile.from_xlsx() / from_csv()
    → ALL columns, types fixed (dash → NaN, cast to float64)
    → to_parquet()
    → archive.parquet  ← permanent source of truth

Stage 2 — ANALYSIS (derived on demand from archive)
  archive.parquet
    → OBDFile.from_parquet()
    → .curated_df  (CURATED_COLS subset)
    → ProcessingConfig.apply()
    → Trip(processed_df, name)
    → TripCollection.similarity_scores(), find_representative()
    → DuckDB: metrics + config_hash + archive_parquet_path
```

---

## File Structure (one class per file)

```
src/drive_cycle_calculator/
├── _schema.py           ← OBD_COLUMN_MAP, CURATED_COLS, _gps_to_duration_seconds (no package imports)
├── obd_file.py          ← OBDFile
├── processing_config.py ← ProcessingConfig, DEFAULT_CONFIG
└── metrics/
    ├── __init__.py      ← re-exports Trip, TripCollection (unchanged public API)
    ├── trip.py          ← Trip (UNCHANGED, stays in metrics/)
    ├── trip_collection.py ← TripCollection (moved from trip.py, new file in metrics/)
    └── _computations.py ← GREEK_COLUMN_MAP, _compute_session_metrics, _similarity,
                            _infer_sheet_name, _SEVEN_METRIC_KEYS
                            (moved to _schema.py: _gps_to_duration_seconds)
                            (removed: _process_raw_df, _smooth_and_derive, _REQUIRED_RAW_COLS)
```

Trip and TripCollection live in `metrics/` — they deal with metrics and similarity scoring.
OBDFile and ProcessingConfig live at the package root — they deal with data ingestion and processing parameters.

---

## Class Specifications

### `OBDFile` (`obd_file.py`)

```
CURATED_COLS = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO₂ in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]
```

- `from_xlsx(path)` — reads ALL columns, coerces types (dash→NaN), infers name
- `from_csv(path, sep=None, decimal=None)` — reads ALL columns; separator via
  `csv.Sniffer` on first 20 lines; decimal separator inferred from first non-null
  numeric cell (`,` if present where `.` expected); falls back to `;` on ambiguity;
  raises `ValueError` with candidates + `sep=` suggestion if still unresolved
- `from_parquet(path)` — loads archive Parquet; raises `ValueError` if
  `"smooth_speed_kmh" in df.columns` (v1 processed format detected)
- `to_parquet(path)` — saves ALL columns, `format_version="2"` in PyArrow schema metadata
- `curated_df` — property returning CURATED_COLS subset
- `quality_report()` → dict:
  `row_count`, `missing_pct` (per col), `dash_count` (per col),
  `gps_gap_count` (gaps >5s in GPS Time), `speed_outlier_count` (>250 km/h),
  `speed_min_kmh`, `speed_max_kmh`, `missing_curated_cols` (absent required cols)
- `to_trip(config=DEFAULT_CONFIG)` — raises `ValueError` if curated col absent

### `ProcessingConfig` (`processing_config.py`)

```python
@dataclass
class ProcessingConfig:
    window: int = 4
    stop_threshold_kmh: float = 2.0
```

- `apply(curated_df)` → processed DataFrame with columns:
  `elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, `co2_g_per_km`,
  `engine_load_pct`, `fuel_flow_lph`
  (GPS Time → elapsed_s; Speed (OBD)(km/h) → rolling(window)→smooth_speed_kmh,
   smooth.diff()→acc_ms2; remaining CURATED_COLS renamed via OBD_COLUMN_MAP)
- `config_hash` — cached_property, first 8 chars of md5(sorted JSON of fields)
- `DEFAULT_CONFIG = ProcessingConfig()` at module level

### `_compute_session_metrics` updates required

Currently reads `speed_ms`, `acceleration_ms2`, `deceleration_ms2`.
After this refactor, must read `smooth_speed_kmh / 3.6`, `acc_ms2.where(>0)`,
`acc_ms2.where(<0)` instead. `Trip.max_speed` uses `smooth_speed_kmh.max()`.

### `TripCollection` (`metrics/trip_collection.py`)

New/changed methods:
- `from_folder(folder, config=DEFAULT_CONFIG)` — uses OBDFile internally
- `from_folder_raw(folder) → list[OBDFile]` — for interactive inspection
- `from_archive_parquets(folder, config=DEFAULT_CONFIG)` — replaces `from_parquet()`
- `from_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` — creates OBDFile stubs,
  calls `.to_trip(config)` eagerly, returns `TripCollection`
- `to_duckdb_catalog(db_path, config=DEFAULT_CONFIG)` — adds `config_hash` column

Removed: `to_parquet()` (archive writing belongs to OBDFile)

---

## Method Migration Table

| Old | New | Status |
|-----|-----|--------|
| `TripCollection.from_parquet(dir)` | `TripCollection.from_archive_parquets(dir, config)` | Replaced |
| `TripCollection.to_parquet(dir)` | `OBDFile.to_parquet(path)` per file | Removed |
| `Trip._path` lazy-load | Removed — Trip always gets complete processed df | Removed |
| `_computations.COLUMN_MAP` (Greek) | Stays as `GREEK_COLUMN_MAP` in `_computations.py` | Renamed |
| `_computations._process_raw_df()` | `ProcessingConfig.apply(OBDFile.curated_df)` | Replaced |
| `_computations._smooth_and_derive()` | Inside `ProcessingConfig.apply()` | Moved |

---

## Interactive Research Usage

```python
# Inspect before archiving
raw_files = TripCollection.from_folder_raw("./raw_data/")  # list[OBDFile]
for f in raw_files:
    report = f.quality_report()
    print(f.name, report["missing_curated_cols"], report["speed_outlier_count"])
    f.to_parquet(f"./data/archive/{f.name}.parquet")

# Build trip collection from archives
tc = TripCollection.from_archive_parquets("./data/archive/")
print(tc.find_representative())

# Try different smoothing
from drive_cycle_calculator.processing_config import ProcessingConfig
config_8 = ProcessingConfig(window=8)
tc_smooth = TripCollection.from_archive_parquets("./data/archive/", config=config_8)
```

---

## Updated `examples/cli/ingest.py` Workflow

`TripCollection.to_parquet()` is removed. The new ingest pattern:

```python
from drive_cycle_calculator.metrics.trip_collection import TripCollection

raw_files = TripCollection.from_folder_raw(raw_dir)   # list[OBDFile]
archive_dir.mkdir(parents=True, exist_ok=True)
for f in raw_files:
    f.to_parquet(archive_dir / f"{f.name}.parquet")

tc = TripCollection.from_archive_parquets(archive_dir)
tc.to_duckdb_catalog(db_path)
```

`ingest.py` and `examples/README.md` must be updated to match this pattern.

---

## `scripts/migrate_to_archive.py` Specification

Iterates `raw_data/` (or any given source folder) and archives to `data/archive/`:

1. Find all `*.xlsx` and `*.csv` files in source folder
2. For each file:
   a. Try `OBDFile.from_xlsx()` / `OBDFile.from_csv()` (based on extension)
   b. On parse failure: log `SKIP [filename]: parse error — {reason}`, continue
   c. Call `quality_report()` and print summary (row_count, missing_curated_cols, speed_outlier_count)
   d. If `missing_curated_cols` is non-empty: log `SKIP [filename]: missing required columns {list}`, continue
   e. Otherwise: call `.to_parquet(archive_dir / f"{f.name}.parquet")`
   f. Log `ARCHIVED [filename]: {row_count} rows`
3. Print final summary: `N files archived, M skipped (K parse errors, J missing columns)`

**Design note**: The first batch of raw data (Galatas, Stefanakis, Kalyvas, Ladikas) was collected without standardized column specs. The migration script treats missing CURATED_COLS as a skip condition, not an error. Files that archive cleanly can be analyzed immediately; files that skip need manual inspection and possibly column mapping.

---

## NOT in scope

- `compare_smoothing(windows)` — P2 TODOS.md
- `Trip.reprocess(window)` — deferred
- Per-trip ProcessingConfig — all trips use same config for comparability
- `RawTripCollection` class — `list[OBDFile]` is sufficient

---

## Known Issues / Pre-implementation Checks

0. **`Trip.max_speed` guard must change** — current code at `trip.py:152` checks
   `if "speed_ms" not in self._df.columns: return float("nan")`. After refactor,
   `speed_ms` NEVER exists in a processed DataFrame, so this ALWAYS returns NaN silently.
   Replace with: check `smooth_speed_kmh` instead:
   ```python
   if "smooth_speed_kmh" not in self._df.columns:
       return float("nan")
   return float(pd.to_numeric(self._df["smooth_speed_kmh"], errors="coerce").max())
   ```
1. **`_compute_session_metrics` column rename** — update to use `smooth_speed_kmh / 3.6`
   (for speed), `acc_ms2.where(acc_ms2 > 0)` (for mean_acc), `acc_ms2.where(acc_ms2 < 0)`
   (for mean_dec). `Trip.max_speed` uses `smooth_speed_kmh.max()`.
2. **COLUMN_MAP split** — keep `GREEK_COLUMN_MAP` in `_computations.py`;
   new `OBD_COLUMN_MAP` and `_gps_to_duration_seconds` in `_schema.py`. Don't conflate the two.
   Note: current COLUMN_MAP in `_computations.py` contains `"Speed (OBD)(km/h)": "speed_kmh"` —
   pull this entry into OBD_COLUMN_MAP, do NOT leave it in the Greek map.
3. **Migration script** — `scripts/migrate_to_archive.py` included in this PR.
4. **CSV decimal separator** — `csv.Sniffer` alone is insufficient; need explicit
   numeric-cell inspection for `,` vs `.` decimal.
5. **Test files: ~28 existing tests need update/replacement, NOT 5-8.** New test files:
   - `tests/test_obd_file.py` — all OBDFile tests (new)
   - `tests/test_processing_config.py` — ProcessingConfig tests (new)
   - `tests/test_trip_collection.py` — TripCollection tests, replaces removed TC tests (new)
   - `tests/test_trip.py` — TRIM: remove TestTripLazyLoading, TestTripCollectionParquet,
     TestTripCollectionDuckDB, TestProcessRawDf, TestTripMaxSpeed; update _make_processed_df()
     to remove speed_ms/acceleration_ms2/deceleration_ms2 and add acc_ms2
6. **`metrics/__init__.py` update** — change TripCollection import from metrics.trip to
   metrics.trip_collection: `from drive_cycle_calculator.metrics.trip_collection import TripCollection`
7. **DuckDB config_hash migration** — `to_duckdb_catalog()` must include
   `ALTER TABLE trip_metadata ADD COLUMN IF NOT EXISTS config_hash VARCHAR` before INSERT,
   otherwise existing catalog files crash on column mismatch.
8. **`load_raw_df()` in _computations.py** — will become duplicate of OBDFile.from_xlsx().
   Keep as backward-compat export for now; add `# Deprecated: use OBDFile.from_xlsx()` comment.

## Test Requirements (per new test file)

### tests/test_obd_file.py
- from_xlsx: happy path (all columns preserved), dash→NaN coercion, name inference
- from_xlsx: missing file → FileNotFoundError
- from_csv: sep auto-detected (comma), sep auto-detected (semicolon)
- from_csv: decimal separator `,` inferred from numeric cell scan
- from_csv: explicit sep= and decimal= override auto-detection
- from_csv: ambiguous → ValueError listing candidates
- from_parquet: v2 archive loads OK
- from_parquet: v1 (smooth_speed_kmh present) → ValueError with migration message
- from_parquet: missing file → FileNotFoundError
- to_parquet: format_version="2" in PyArrow schema metadata
- to_parquet: roundtrip (from_xlsx → to_parquet → from_parquet) preserves all columns
- curated_df: returns only CURATED_COLS subset
- curated_df: missing col not raised (filtering only — missing cols absent from result)
- quality_report: returns dict with all 8 keys
- quality_report: gps_gap_count counts gaps > 5s correctly
- quality_report: speed_outlier_count counts speed > 250 km/h
- quality_report: missing_curated_cols lists absent required cols
- quality_report: empty DataFrame → row_count=0, no crash
- quality_report: all-NaN GPS Time → gps_gap_count=0 (no crash)
- to_trip: happy path → Trip with correct output columns
- to_trip: missing curated col → ValueError with descriptive message

### tests/test_processing_config.py
- apply: output columns exactly {elapsed_s, smooth_speed_kmh, acc_ms2, speed_kmh,
  co2_g_per_km, engine_load_pct, fuel_flow_lph}
- apply: window=4 produces different smooth_speed_kmh than window=8
- apply: acc_ms2 is signed (pos+neg), not split
- config_hash: same config → same hash (deterministic)
- config_hash: different window value → different hash
- config_hash: cached (same object returned on second access)
- DEFAULT_CONFIG: window=4, stop_threshold_kmh=2.0

### tests/test_trip_collection.py
- from_folder: uses OBDFile internally (trip has no speed_ms column)
- from_folder_raw: returns list[OBDFile], not TripCollection
- from_archive_parquets: loads v2 Parquets, builds Trips
- from_archive_parquets: v1 Parquet in folder → ValueError propagated
- from_duckdb_catalog: config_hash written to catalog
- from_duckdb_catalog: OBDFile stubs → .to_trip(config) called eagerly
- to_duckdb_catalog: config_hash stored in trip_metadata row
- to_duckdb_catalog: existing catalog gains config_hash column (ALTER TABLE path)

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 4 | OPEN | 6 proposals, 5 accepted, 1 deferred |
| Codex Review | `/codex review` | Independent 2nd opinion | 4 | issues_found | outside voice via Claude subagent |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 4 | OPEN (PLAN) | 9 issues, 1 critical gap |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CRITICAL GAP:** `Trip.max_speed` at `trip.py:152` — `speed_ms` guard must be replaced with `smooth_speed_kmh` guard before implementation (silent NaN regression otherwise). See Known Issues #0.

**UNRESOLVED:** 0 — all decisions made.

**VERDICT:** ENG REVIEW has 1 critical pre-implementation check. Address Known Issues #0, #1, #7 in existing files FIRST, then build new classes. CEO CLEARED (3 rounds, scope confirmed).
