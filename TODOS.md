# TODOS

## ~~P1 — OBDFile + ProcessingConfig refactor~~ ✓ DONE

**What:** Two-stage archive pipeline. `OBDFile` wraps a raw OBD xlsx/CSV/Parquet file.
`ProcessingConfig` (dataclass with `window` and `stop_threshold_kmh`) applies smoothing,
acceleration derivation, and column renaming via `apply(curated_df)`. `DEFAULT_CONFIG`
is `ProcessingConfig(window=4)`.

**Shipped:**
- `src/drive_cycle_calculator/_schema.py` — dependency-free `OBD_COLUMN_MAP`, `CURATED_COLS`, `_gps_to_duration_seconds`
- `src/drive_cycle_calculator/obd_file.py` — `OBDFile.from_xlsx/from_csv/from_parquet`, `to_parquet` (v2 format), `curated_df`, `quality_report`, `to_trip`
- `src/drive_cycle_calculator/processing_config.py` — `ProcessingConfig`, `config_hash`, `DEFAULT_CONFIG`
- `src/drive_cycle_calculator/metrics/trip_collection.py` — `TripCollection` extracted from `trip.py`; adds `from_folder_raw`, `from_archive_parquets`, `from_duckdb_catalog` (eager via OBDFile)
- `scripts/migrate_to_archive.py` — one-shot xlsx → v2 Parquet converter
- `examples/cli/ingest.py` — updated for two-stage workflow
- 74 new tests; 198 total passing

---

## ~~P2~~ → ~~P1 — Migrate internal column names from Greek to English~~ ✓ DONE

**What:** Rename all Greek column names in the package computation layer to English at
the package entry points (`_process_raw_df()` and `TripCollection.from_excel()`).
`_normalise_columns()` in `_computations.py` applies `COLUMN_MAP` at both entry
points (`_process_raw_df()` and `TripCollection.from_excel()`). All internal package
code uses English column names. DriveGUI Excel output remains Greek (user-facing).
120 tests passing.

---

## ~~P1 — Rationalise Parquet Columns~~ → subsumed by OBDFile + ProcessingConfig refactor

**Resolved by:** The OBDFile + ProcessingConfig refactor (planned 2026-04-07).
Archive Parquets store all raw OBD columns (no derived columns). ProcessingConfig.apply()
produces `smooth_speed_kmh` and `acc_ms2` in-memory only — no redundant persisted columns.
`speed_ms` (= smooth_speed_kmh/3.6) and `acceleration_ms2`/`deceleration_ms2` (= subsets
of acc_ms2) are removed from all persisted storage.


---

## P2 — First-batch data quality audit + future acquisition spec

**What:** Run `scripts/migrate_to_archive.py` against the first batch of raw data
(Galatas, Stefanakis, Kalyvas, Ladikas) and document which files fail, which columns
are missing or malformed, and what the spread of issues is per driver. Then define a
minimum column spec for future data acquisition sessions.

**Why:** The first batch was collected without standardized specs — it's a reconnaissance
dataset. When future data collection happens (or students collect new data), they should
receive an explicit list of required Torque columns before starting. Without this, the same
quality issues will recur with each new batch.

**How to apply:** After the OBDFile + ProcessingConfig refactor lands, run the migration
script against `raw_data/`. Review the `SKIP` output. Write a `docs/data_acquisition_spec.md`
listing: required OBD-II channels, expected dtypes, known Torque export quirks (GPS Time
format, dash placeholders). Reference CURATED_COLS as the minimum viable set.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

**Depends on:** OBDFile + ProcessingConfig refactor must land first (migration script).

---

## P2 — `OBDFile.compare_smoothing(windows=[2, 4, 8])`

**What:** Method on `OBDFile` that applies `ProcessingConfig(window=w)` for each window
size and returns a DataFrame of key metrics (mean_speed, mean_acc, stop_pct) per window.
Useful for choosing the right smoothing parameter before committing to a ProcessingConfig.

**Why:** The window=4 default was inherited from the student DriveGUI. No empirical basis.
Researchers need a quick way to see how metric stability changes with window size.

**Where:** `src/drive_cycle_calculator/obd_file.py`

**Effort:** S (human: ~1 hr / CC: ~10 min)

**Depends on:** OBDFile + ProcessingConfig refactor must land first.

---

## P2 — Fix stop_percentage unit-detection heuristic

**What:** Both `stop_percentage.py` and `total_stop_percentage.py` have:
```python
if speeds.max() < stop_threshold_kmh:
    speeds = speeds * 3.6  # assume m/s → km/h
```
This silently produces wrong results for all-stop sessions (all legitimate km/h values below 2.0 km/h get multiplied by 3.6).

**Why:** Silent wrong output is worse than an error. After the Greek→English migration enforces explicit unit contracts at the `compute_*` layer, this heuristic can be removed and the function can assume km/h always.

**Where:** `students/DriveGUI/stop_percentage.py:72` and `total_stop_percentage.py:85`

**Effort:** S (human: ~2 hrs / CC: ~10 min)

**Depends on:** calc/presentation split + Greek→English column migration (units become explicit and no guessing needed).

---

## ~~P1 — Trip + TripCollection class API~~ ✓ DONE

`Trip(df, name)` and `TripCollection` shipped in `src/drive_cycle_calculator/metrics/trip.py`.
`_computations.py` holds the private helpers (`_compute_session_metrics`, `_similarity`,
`_process_raw_df`, `_infer_sheet_name`) plus backward-compat re-exports of all flat functions.
`tests/conftest.py` deleted; 95 tests passing via real installed package.

---

## ~~P1 — Parquet + DuckDB persistence layer~~ ✓ DONE

**What:**
- `TripCollection.to_parquet(directory)` — write each trip as `{trip_id}.parquet`
- `TripCollection.from_parquet(directory)` — load from Parquet files
- `TripCollection.to_duckdb_catalog(db_path)` — write/upsert trip metadata to `metadata.duckdb`
- `TripCollection.from_duckdb_catalog(db_path)` — load trip stubs (lazy: DataFrame loaded on first access)

**Why:** Ingest once, query instantly. No re-processing of raw xlsx on every run.
DuckDB catalog enables SQL queries across trips without loading DataFrames.
Parquet files are portable: readable by pandas, inspectable with any data tool,
and the transport format for the eventual Supabase migration (files go to S3,
DuckDB queries S3 URLs unchanged).

**Storage layout:**
```
data/
  trips/
    2025-05-14_Morning.parquet   # one file per trip (processed DataFrame)
    2025-05-14_Evening.parquet
  metadata.duckdb                # catalog: one row per trip, 7 metrics + parquet_path
```

**Lazy loading:** `Trip.__init__` accepts `df=None` when `_path` is set.
`_df` becomes a property that auto-loads from `_path` on first access.
`from_duckdb_catalog()` creates Trip stubs (df=None, _path=parquet_path) only.

**New dependencies:** `pyarrow`, `duckdb` — add to `pyproject.toml`.

**Effort:** M (human: ~2 days / CC: ~30 min)

**Depends on:** Greek→English column migration must land first (Parquet files store English column names).

---

## P1 — Microtrip segmentation

**What:** `Trip.microtrips` returns actual `list[Microtrip]` instead of raising
`NotImplementedError`.

**Why:** Microtrips are the fundamental unit of analysis for WLTP-style driving-cycle
construction. The current session-level similarity scoring is a stepping stone.
Scientific goal: find the ensemble of microtrips whose collective statistics best
match the overall distribution, then assemble the candidate cycle from them.

**Algorithm:**
1. Identify stop intervals (speed ≤ 2 km/h for ≥ N consecutive samples)
2. Split the speed profile at those intervals
3. Each contiguous moving segment = one Microtrip
4. Compute per-microtrip metrics: duration, mean_speed, mean_acc, mean_dec, stop_pct

**Effort:** M (human: ~1 day / CC: ~20 min)

**Depends on:** Trip class shipped ✓. Implement Microtrip dataclass first.

---

## P1 — Representative microtrip selection

**What:** `TripCollection.find_representative_microtrip() -> Microtrip` using the
same 7-metric similarity scoring but at microtrip granularity.

**Why:** Required for WLTP-style candidate cycle construction. Current
`find_representative()` works at session level; this extends it to the microtrip level.

**Effort:** S (human: ~4 hrs / CC: ~10 min)

**Depends on:** Microtrip segmentation (P1) must land first.

---

## P1 — Candidate cycle assembly

**What:** Assemble a synthetic representative driving cycle from a sequence of
representative microtrips. Output: a time-series speed profile that matches the
overall fleet statistics.

**Effort:** M (human: ~2 days / CC: ~30 min)

**Depends on:** Representative microtrip selection (P1).

---

## ~~P1 — Remove os.chdir() from short_excel.py before any src/ migration~~ ✓ DONE

`os.chdir(folder)` removed from both `short_excel.process_files()` and the GUI's own
`process_files()`. Both now use `os.path.join(folder, "*.xlsx")` for glob and return/store
the folder explicitly. `run_calculations()` and `plot_all_and_save()` receive the folder
directly — no more reliance on CWD side-effects.

---

## P2 — CLI entry point

**What:** `dcc analyze ./data/ --output report.xlsx` — a command-line interface
for the drive cycle calculator package.

**Why:** Researchers outside the GUI workflow need a scriptable interface. Once
`from_folder()` is available (shipped ✓), a thin CLI is straightforward.

**Effort:** S (human: ~4 hrs / CC: ~10 min)

**Depends on:** `TripCollection.from_folder()` shipped ✓.

---

## ~~P1 — Examples directory (CLI + GUI)~~ ✓ DONE

**What:** Create `examples/` with:
- `examples/cli/ingest.py` — ingests raw xlsx folder → Parquet + DuckDB catalog
- `examples/cli/analyze.py` — loads from catalog → prints similarity scores + representative trip
- `examples/gui/main.py` — Tkinter GUI: folder picker → ingest → catalog → speed profile chart
- `examples/README.md`, `examples/cli/README.md`, `examples/gui/README.md`

**Why:** `examples/gui/` is the **successor** to `students/DriveGUI/`. Demonstrates the
new two-step workflow (ingest once, query fast) vs the old full-reprocess-every-run pattern.

**How to apply:** GUI is a thin Tkinter wrapper around TripCollection — no business logic
in the GUI layer. Migrate to PyQt6/PySide6 later by replacing `tk.*` calls only.
CLI scripts use `sys.argv` (no argparse), ~50 lines each.

**Effort:** S (human: ~4 hrs / CC: ~15 min)

**Depends on:** Parquet + DuckDB persistence layer must ship first.

---

## ~~P2 — Freeze DriveGUI and restore self-sufficiency~~ ✓ DONE

**What:** Ensure `students/DriveGUI/` runs completely standalone — no imports from
`src/drive_cycle_calculator`. Revert any package dependencies introduced by the
refactor branch. Add a `FROZEN` notice to `students/DriveGUI/README.md`.

**Why:** DriveGUI is a historical reference implementation. It should be a snapshot
that works forever, independent of package API evolution. If the package API changes,
DriveGUI must not break.

**How to apply:** Check `students/DriveGUI/*.py` for any `from drive_cycle_calculator`
imports. Inline any shared logic back into the DriveGUI layer. The inline
`calculations.py`, `metrics.py`, `log_utils.py` inside `students/DriveGUI/` are its
implementation — they should not import from `src/`.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

**Depends on:** `examples/gui/` must be functional first (so there is a working replacement).

---

## P2 — Supabase migration script

**What:** `scripts/migrate_to_postgres.py` — reads `metadata.duckdb` and writes to a
Supabase/PostgreSQL `trips` table. Updates `pla_trajectory_uri` to S3/GCS URLs.

**Why:** When going online, the local DuckDB catalog needs to be promoted to Supabase.
The column mapping is already designed into the DuckDB schema — migration is one
`INSERT SELECT` + URL update.

**How to apply:** Use `psycopg2` or the Supabase Python client. Map DuckDB column names
to DBML `trips` table columns (see `docs/data_schema/FUEL_EKO_wars.dbml`). Drop
`parquet_path` from the PostgreSQL schema; populate `pla_trajectory_uri` with S3 URLs.

**Effort:** M (human: ~1 day / CC: ~20 min)

**Depends on:** Parquet + DuckDB persistence layer must be proven in practice first.

---

## P3 — Trip listbox in examples/gui/

**What:** Show all trips in a scrollable listbox in `examples/gui/main.py`. Clicking
a trip loads its speed profile. Representative trip is highlighted.

**Why:** Natural next step after the basic single-chart GUI ships.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

**Depends on:** `examples/gui/main.py` (P1 above) must ship first.

---

## P2 — Deduplicate similarity scoring in speed_profile.py

**What:** `compute_speed_profile()` in `metrics.py` uses its own inline 2-metric selection
(mean speed + stop %) to pick the representative session for the Speed Profile tab.
`find_representative_sheet()` uses 7 metrics. They can return different sessions.

**Why:** **Scientific correctness issue.** The GUI can simultaneously claim Session A is the
representative route (Representative Route tab, 7-metric scoring) and display Session B's
speed profile (Speed Profile tab, 2-metric scoring). A researcher exporting these results
would get inconsistent data without any warning. Make `compute_speed_profile()` call
`find_representative_sheet()` and remove the inline `_metrics()`/`_sim()` closures.

**Where:** `students/DriveGUI/metrics.py:272` — `compute_speed_profile()` function.

**Effort:** S (human: ~1 hr / CC: ~5 min)

**Depends on:** calc/presentation split (metrics.py extraction) must land first. ✓ Done.

---

## P3 — SQL-backed similarity scoring (fast path for large catalogs)

**What:** Once `to_duckdb_catalog()` exists, add an optional fast path for
`TripCollection.similarity_scores()` that reads pre-computed metrics directly from
the DuckDB catalog (a single `SELECT` query) instead of loading all DataFrames.

**Why:** Current lazy-load approach triggers N `pd.read_parquet()` calls on first
`similarity_scores()` invocation. Fine at 5-20 trips. At 500+ trips: ~2s sequential
file reads that could be a single SQL query against already-computed catalog rows.

**How to apply:** Add a `from_duckdb_catalog()` variant that retains the `conn`
reference so `similarity_scores()` can query the catalog metadata without loading
DataFrames. The 7 metrics are stored in the catalog — no Parquet I/O needed.

**Effort:** S (human: ~4 hrs / CC: ~15 min)

**Depends on:** Parquet + DuckDB persistence layer must be functional first.
