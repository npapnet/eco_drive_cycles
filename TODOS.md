# Immediate Next Steps

## P1 — Resampling and gap-check during ingestion

**What:** In `dcc ingest` (and `OBDFile.to_parquet`), resample raw data to a fixed 1s frequency before saving to Parquet. Add an adjustable `max_gap_s` check (default 5s). If a time gap exceeds this threshold, either issue a warning or abort the conversion based on a CLI flag.

**Why:** Raw OBD data often has irregular sampling. Resampling to 1s ensures a uniform time base for all downstream calculations. Gaps in data indicate sensor loss or engine restarts, which should be flagged to the user.

**Where:** `src/drive_cycle_calculator/obd_file.py` and `src/drive_cycle_calculator/cli/ingest.py`.

**Effort:** S

## P1 — Modular in-place workflow (single-argument ingest)

**What:** Modify `dcc ingest` (and potentially other commands) to support a modular, in-place workflow. The `ingest` command should accept a single directory argument. If only one argument is provided, it should use that directory for both input (raw data) and output (creating `trips/`, `microtrips/`, and reports subfolders within it).

**Why:** The current requirement for separate input and output directories is a legacy of a centralized repository model. A more modular approach allows researchers to keep processed artifacts alongside their raw data source.

**Where:** `src/drive_cycle_calculator/cli/ingest.py` and `src/drive_cycle_calculator/cli/main.py`.

**Effort:** S

## P1 — Representative microtrip selection per cluster

**What:** For each cluster identified in the clustering phase, find the single most representative microtrip using the new `SimilarityMeasure` (cosine similarity, etc.) from the core library.

**Why:** Finding the representative sample for each cluster allows for synthetic cycle construction and provides a "canonical" example of that driving behavior.

**Where:** `examples/workflow/05_microtrip_visulisation.py`.

**Effort:** S

## P1 — v-a density cloud and canonical profile visualisation

**What:** Implement advanced visualisations for cluster analysis:
1. **v-a Density Cloud**: Create a 2D density plot (KDE2D or Hexbin) of Speed vs. Acceleration for all samples in the dataset, color-coded or faceted by cluster.
2. **Canonical Microtrips**: Plot the time-series speed profiles of the representative microtrips for each cluster.

**Why:** Clustering needs visual validation. Joint velocity-acceleration (v-a) probability density matrices (or "clouds") are the industry standard for drive cycle "fingerprinting" and representativeness validation (e.g., André 2004, Ericsson 2001). Unlike v-t (speed-time) profiles which show individual events, v-a clouds capture the aggregate statistical "signature" of the driving behavior. Standard scatter plots become unreadable with large datasets.

**Performance Consideration:** With large datasets (thousands of microtrips), KDE plots and pairwise similarity can be computationally expensive. Use sampling or efficient binning (e.g., `datashader` or `hexbin`) for the v-a cloud. Plan carefully

**Where:** `examples/workflow/05_microtrip_visulisation.py` 

**Effort:** M


# Backlog

## P2 — Reassess the role of DuckDB in the pipeline

**Question:** Is DuckDB still the right persistence layer, or should the pipeline be simplified?

**Context:** The original motivation was a persistent catalog of trip metrics for fast querying without reprocessing Parquets. In practice:
- `dcc extract` already exports metrics to CSV or XLSX (not just DuckDB), so the metrics are available in open formats without a database.
- `dcc analyze` uses DuckDB only as a lookup table to find Parquet paths, then re-reads the Parquets anyway — so DuckDB adds a round-trip with no data benefit at current scale.
- `dcc ingest` was explicitly decoupled from DuckDB (no catalog write at ingest time), which further reduces DuckDB's role.
- The `examples/workflow/` scripts exposed this: `02_extract_analyze.py` could skip the DuckDB round-trip in the analyze phase and call `TripCollection.from_archive_parquets()` directly.

**Investigate:**
1. Is there any scenario at current or expected scale where the DuckDB catalog provides a real benefit over loading Parquets directly?
2. Should `dcc analyze` accept a `trips/` folder directly instead of requiring a `metrics.duckdb`?
3. Should DuckDB be demoted to an optional output format of `dcc extract` (alongside CSV/XLSX) rather than being a required intermediate step for `dcc analyze`?
4. Does the planned Supabase migration (see below) change the answer?

---

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


