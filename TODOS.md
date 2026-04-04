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

## P1 — Remove os.chdir() from short_excel.py before any src/ migration

**What:** `short_excel.process_files()` calls `os.chdir(folder)` as a side effect. This is
a session-global mutation that silently corrupts the working directory for any code that
runs after it. It works for the current GUI-only flow, but is incompatible with a
pip-installable library — any library caller would have their cwd silently changed.

**Why:** Library blocker. `short_excel.py` must NOT be migrated to `src/drive_cycle_calculator/`
until this is removed. The fix is to return the folder path and let callers use it, or
to rewrite `process_files()` to accept an explicit folder argument instead of calling
`os.chdir()`. Downstream callers (`driving_cycles_calculatorV1.py:82`) pass the result to
`run_calculations(os.getcwd())` — once `os.chdir` is removed, this needs to become
`run_calculations(folder_path)`.

**Where:** `students/DriveGUI/short_excel.py:46` — `process_files()` function.

**Effort:** S (human: ~2 hrs / CC: ~10 min)

**Depends on:** Nothing. Can be done independently before src/ restructure.

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

