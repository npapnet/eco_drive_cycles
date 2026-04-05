# TODOS

## P2 — Migrate internal column names and identifiers from Greek to English

**What:** All internal variable names, column header strings, and function parameters that
use Greek (e.g., `"Ταχ m/s"`, `"Εξομαλυνση"`, `"Επιταχυνση"`, `"Διάρκεια (sec)"`) should
be migrated to English equivalents in the computation layer (`metrics.py`, `calculations.py`).
The Excel output and GUI labels can remain Greek for user-facing purposes.

**Why:** Once the library is pip-installable, researchers outside Greece will need to use
the API. Greek-only identifiers make the package unusable to the broader telematics and
eco-driving research community. Internationalization starts with the API surface.

**How to apply:** After the calc/presentation split ships, add a column mapping layer in
`metrics.py` that normalises incoming column names (Greek → English canonical) at the
boundary between `pd.read_excel()` and `compute_*()`. Visualization modules translate back
to Greek for display if needed.

**Effort:** M (human: ~1 day / CC: ~20 min)

**Depends on:** calc/presentation split (metrics.py extraction) must land first — the
mapping layer lives in `metrics.py`.

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

## P1 — DuckDB persistence backend

**What:** `TripCollection.to_duckdb(path)` and `TripCollection.from_duckdb(path)`.

**Why:** As the dataset grows (more drivers, more sessions), full in-memory loading
will exceed available RAM. DuckDB stores columnar data on disk and queries lazily —
no full load required. Also the natural persistence layer for microtrip analytics
(cross-trip aggregates over millions of rows).

**How to apply:** After `Trip._path` is used for lazy loading, use DuckDB as the
backing store: `Trip` stores metadata eagerly, defers the DataFrame load until
`.speed_profile` or `.microtrips` is accessed. `TripCollection.from_duckdb()` opens
the DB and yields Trip objects without loading any DataFrames. `to_duckdb()` processes
and writes all trips. Start with the schema: one row per time sample, with a `trip_id`
foreign key.

**Effort:** M (human: ~2 days / CC: ~30 min)

**Depends on:** Trip._path already reserved. Implement lazy loading before DuckDB.

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
