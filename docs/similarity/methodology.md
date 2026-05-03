---
status: ACTIVE
last_updated: 2026-05-04
---
# Similarity Measures

All measures live in `src/drive_cycle_calculator/similarity/measures.py` and share the
`SimilarityMeasure` Protocol:

```python
def __call__(self, fleet: np.ndarray, trip: np.ndarray) -> float: ...
```

- `fleet` — shape `(n_trips, n_metrics)`: the full collection matrix (one row per trip)
- `trip`  — shape `(n_metrics,)`: the trip being scored
- Returns a float where higher = more similar

The 7 metrics (`_SEVEN_METRIC_KEYS`) that form each vector:

| Index | Key | Unit |
|---|---|---|
| 0 | `duration` | s |
| 1 | `mean_speed` | km/h |
| 2 | `mean_ns` | km/h (excl. stops) |
| 3 | `stops` | count |
| 4 | `stop_pct` | % |
| 5 | `mean_acc` | m/s² |
| 6 | `mean_dec` | m/s² (negative) |

---

## `pct_deviation` (default)

**File:** `measures.py` · **Range:** [0, 100]

Per-component percentage similarity, averaged across metrics.

For each metric *k*:

```
fleet_mean_k = mean of fleet[:, k]

score_k = max(0,  100 - |trip_k - fleet_mean_k| / |fleet_mean_k| × 100)
```

Special cases:
- `fleet_mean_k` is NaN → `score_k = 0`
- `fleet_mean_k == 0` and `trip_k == 0` → `score_k = 100`
- `fleet_mean_k == 0` and `trip_k ≠ 0` → `score_k = 0`

Final score = `mean(score_k for all k)`.

**Properties:**
- Each metric is treated independently — a large deviation on one metric can be
  offset by perfect matches on others.
- Scale-dependent: a 10 km/h deviation counts the same regardless of whether the
  fleet spread for that metric is 1 km/h or 50 km/h.
- Scores are human-readable percentages and easy to interpret.

**When to use:** Default choice. Works well when all metrics are roughly equally
important and you want a transparent, explainable score.

---

## `cosine_similarity`

**File:** `measures.py` · **Range:** [0, 100]

Cosine similarity between the trip vector and the fleet centroid vector.

```
fleet_mean = mean of fleet rows (shape: n_metrics)

cos(θ) = (fleet_mean · trip) / (‖fleet_mean‖ × ‖trip‖)

score = max(0, cos(θ)) × 100
```

Negative cosine values are clamped to 0. Zero vectors return 0.

**Properties:**
- **Direction only, not magnitude.** Two trips whose metric vectors are scalar
  multiples of each other score 100, even if one has twice the speed and duration
  of the other. This is the defining property and its main limitation for this domain.
- Scale-invariant: multiplying all metrics of a trip by a constant does not change
  its score.
- For drive-cycle data, all metrics are non-negative, so cosine is almost always
  positive and rarely reaches 0.

**When to use:** Experiments where you care about the *shape* of a driving profile
(e.g., high speed + low stop %) more than its absolute magnitudes. Useful as a
complement to `pct_deviation` — a trip can score differently on both measures,
revealing whether a mismatch is directional or magnitude-based.

**Limitation:** Cannot distinguish a trip that is proportionally faster/heavier
from one that matches the fleet average exactly. Consider pairing with
`z_score_distance` when magnitude matters.

---

## `z_score_distance`

**File:** `measures.py` · **Range:** (0, 100]

Z-score normalised Euclidean distance from the fleet centroid, converted to
a similarity score.

```
fleet_mean_k = nanmean(fleet[:, k])
fleet_std_k  = nanstd(fleet[:, k])   (if 0, replaced by 1)

z_k = (trip_k - fleet_mean_k) / fleet_std_k   [only for valid metrics]

d   = ‖z‖  (Euclidean norm of the z-score vector)

score = 100 / (1 + d)
```

NaN fleet means (no valid data for a metric across all trips) and NaN trip values
are excluded from the z-score vector.

**Properties:**
- **Scale-independent.** A 10 km/h deviation from the mean matters more when the
  fleet spread is 2 km/h than when it is 40 km/h. This corrects the main weakness
  of `pct_deviation`.
- Score decays asymptotically toward 0 as distance grows; it never reaches 0.
  A perfect match (trip = fleet mean) scores exactly 100.
- Sensitive to fleet size: with few trips, `fleet_std` estimates are noisy, which
  can make scores unreliable. Best used when the collection has ≥ 10 trips.
- Unlike cosine, captures magnitude differences — two trips with the same
  directional profile but different scales will score differently.

**When to use:** When you want each metric's contribution to be weighted by how
variable that metric actually is in your dataset. A natural upgrade from
`pct_deviation` once you have enough trips to estimate spread reliably.

---

## Adding a new measure

Any callable matching the Protocol can be passed to `similarity_scores()` or
`find_representative()` without modifying `TripCollection`:

```python
def my_measure(fleet: np.ndarray, trip: np.ndarray) -> float:
    ...

scores = tc.similarity_scores(measure=my_measure)
```

Guidelines:
- Return a float where higher = more similar (not a distance)
- Handle NaN values in both `fleet` and `trip`
- Handle the degenerate case of a single-trip collection
- Add unit tests in `tests/test_similarity.py` following the existing class pattern
