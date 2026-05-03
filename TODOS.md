# Immediate Next Steps

# Backlog

## P2 - revisit cli commands workflow 

Why: Ladikas data processing indicated problems with the current workflow. 

The current workflow is:
- `dcc ingest`
- `dcc extract` 
- `dcc analyze`
- `dcc gui`


**Issues identified with the current workflow:**

1. **extract** could use a filter with the name of the user. 
3. **analyse**: only outputs to the console. It would be better to have an option to output to a file. It was unclear which db or set of data it used. 
4. **gui**:
    - The gui during analysis tried to load files and could not ( reporte to hte console something like `<path>\drive_cycle_calculator\cli\gui.py:137: UserWarning: Trip 't20250813-092120-384-3bdac5': cannot load '<path to repo>>\\data\\trips\\t20250813-092120-384-3bdac5.parquet' — File not found: <path to repo>\data\trips\t20250813-092120-384-3bdac5.parquet. Skipping.`)
    - There was no option for outputing the data, nor reporting fo the similarity measures. 
    - There were no filters 
  

I am focusing towards an approach that creates for the analysis a dedicated folder based on the date and time of the analysis, and all the outputs of the analysis are stored in that folder. This folder will include the similarity measures, the representative microtrips, and the representative driving cycle. 


## P1 — Representative microtrip selection

**What:** `TripCollection.find_representative_microtrip() -> Microtrip` using the same 7-metric similarity scoring but at microtrip granularity.

**Effort:** S (human: ~4 hrs / CC: ~10 min)

**Depends on:** ~~v0.4 refactor (`MicrotripSegmenter` + `trip.microtrips`)~~ ✓ shipped (2026-05-03). `trip.microtrips` and `MicrotripSegmenter` are live.

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

## P2 — Supabase migration script

**What:** `scripts/migrate_to_postgres.py` — reads `metadata.duckdb` and writes to a Supabase/PostgreSQL `trips` table.

**Effort:** M (human: ~1 day / CC: ~20 min)

**Depends on:** Parquet + DuckDB persistence proven in practice ✓.


---

## P3 — Trip listbox in examples/gui/

**What:** Show all trips in a scrollable listbox in `examples/gui/main.py`. Clicking a trip loads its speed profile. Representative trip is highlighted.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

---

## P2 — Microtrip export to Parquet

**What:** Persist a `list[Microtrip]` to disk as Parquet files in a dedicated output folder, so microtrips can be loaded and analysed independently of the parent `Trip` objects.

**Why:** Currently microtrips are in-memory only and lost when the process exits. Exporting them is a prerequisite for the analysis output folder workflow (`dcca-<YYYYMMDD-hhmm>/microtrips/`).

**Depends on:** ~~v0.4 refactor~~ ✓ shipped (2026-05-03).

---

## P3 — TripCollection constructor-level filtering

**What:** Optional filter parameters on `TripCollection.from_archive_parquets()` (and potentially `from_duckdb_catalog()`) so callers can load a pre-filtered collection without loading all trips first. Example: `from_archive_parquets(path, user="John")`.

**Why:** `TripCollection` is a result/container type — filtering belongs at load time, not as a method on the collection. With single-driver datasets this is not needed; becomes useful when the archive contains multiple drivers.

**Effort:** S

---

## P3 — SQL-backed similarity scoring (fast path for large catalogs)

**What:** Optional fast path for `TripCollection.similarity_scores()` that reads pre-computed metrics directly from the DuckDB catalog instead of loading all DataFrames.

**Why:** Current approach triggers N `pd.read_parquet()` calls on first invocation. Fine at 5–20 trips. At 500+ trips this is slow; the 7 metrics are already stored in the catalog.

**Effort:** S (human: ~4 hrs / CC: ~15 min)

**Depends on:** Parquet + DuckDB persistence layer ✓.


