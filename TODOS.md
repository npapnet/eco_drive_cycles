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

## P2 — Deduplicate similarity scoring in speed_profile.py

**What:** `speed_profile.py` contains `_choose_representative_sheet()`, which reimplements
the same representative-route selection algorithm as `metrics.find_representative_sheet()`.
After the calc/presentation split lands, make `speed_profile.py` call
`metrics.find_representative_sheet()` instead and delete the local copy.

**Why:** Two divergent implementations of the same algorithm will silently produce different
results over time as one gets fixed/tuned and the other doesn't.

**Where:** `students/DriveGUI/speed_profile.py` — look for `_choose_representative_sheet`.

**Effort:** S (human: ~1 hr / CC: ~5 min)

**Depends on:** calc/presentation split (metrics.py extraction) must land first.

