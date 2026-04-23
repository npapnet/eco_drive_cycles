# Microtrip Analysis Module — Design Specification

**Version:** 0.1 (draft for review)  
**Status:** Pre-implementation — happy path spec  
**Pipeline context:** OBDII data pipeline, WLTP driving cycle analysis

---

## 1. Purpose and Scope

This module segments processed vehicle speed signals into **microtrips** for use in driving cycle analysis (WLTP and similar standards). It does not handle signal acquisition, smoothing, or Trip-level I/O — those are upstream responsibilities.

---

## 2. Definitions

### 2.1 Microtrip

A microtrip is a **motion-based segment** of a vehicle journey, defined as the interval from one stop to the next, inclusive of the trailing stop. It is not ignition-bounded.

**Formal definition:**
- Begins at the first sample where `speed ≥ stop_threshold_kmh` after a stop
- Ends at the last sample of the subsequent sustained stop (inclusive)
- A **stop** is a sustained condition where `speed < stop_threshold_kmh` for `≥ stop_min_duration_s`

**Known limitation:** Ignition state and cold-start annotations are not captured at the microtrip level in this version. Cold-start validity assessment is deferred.

### 2.2 Stop

A stop is a sustained period of zero (or near-zero) speed. It belongs to the **closing microtrip** — the microtrip that precedes it. Stop samples are not duplicated into the following microtrip.

Stop duration is tracked via `stop_duration_after` as a derived property (see §5).

### 2.3 Trip

A `Trip` owns the parent DataFrame and acts as the container from which microtrips are derived. Trip identity criteria are deferred pending usage context. Working assumption: one ignition session = one Trip.

---

## 3. Configuration

### 3.1 Config Architecture

All pipeline configuration is centralised in a `PipelineConfig` root object with sibling namespaces:

```python
class PipelineConfig(BaseModel):
    processing: ProcessingConfig
    segmentation: SegmentationConfig
```

`PipelineConfig` is serialisable to/from JSON/YAML and is the single object passed between pipeline stages.

### 3.2 `SegmentationConfig`

```python
class SegmentationConfig(BaseModel):
    stop_threshold_kmh: float = 1.0
    # Speed below this value is considered stopped.
    # Accounts for GPS noise and low-speed OBDII signal drift.

    stop_min_duration_s: float = 1.0
    # Minimum sustained duration to confirm a stop.
    # Guards against transient dips through zero.

    microtrip_min_duration_s: float = 15.0
    # Minimum total microtrip duration (motion + trailing stop).
    # Default: 15s (conservative, inclusive of stop time).
    # Hard floor: 5s (enforced by validator, not user-exposed).
    # Note: no academic consensus on this value; WLTP filters
    # by distance (≥200m) rather than duration.

    microtrip_min_distance_m: float = 50.0
    # Minimum microtrip distance. Guards against crawl segments
    # that pass the duration filter but represent near-zero motion.

    @validator('microtrip_min_duration_s')
    def min_above_floor(cls, v):
        if v < 5.0:
            raise ValueError("microtrip_min_duration_s cannot be below 5s floor")
        return v
```

**Design notes:**
- `stop_threshold_kmh` and `stop_min_duration_s` are distinct from `ProcessingConfig.window_size`. Smoothing and segmentation are independent concerns with independent sensitivity profiles.
- The 5s floor is a domain constraint derived from sensor noise literature (Kamble et al., Tamsanya et al.), not a user preference. It is hardcoded in the validator and documented here.
- `microtrip_min_duration_s` is **total duration** including stop time. This is a deliberate, documented choice.

---

## 4. Data Model

### 4.1 `Microtrip`

```python
class Microtrip(BaseModel):
    # Identity
    trip_file: Path             # Parquet filename — stable key for reload
    start_idx: int              # Index of first motion sample (inclusive)
    end_idx: int                # Index of last motion sample (exclusive)
    stop_start_idx: int         # Index of first stop sample (inclusive)
    stop_end_idx: int           # Index of last stop sample (exclusive)

    # Private — not serialised
    _trip_ref: weakref | None = PrivateAttr(default=None)

    def bind(self, trip: "Trip") -> None:
        """Bind in-memory Trip reference. Call after instantiation."""
        self._trip_ref = weakref.ref(trip)

    @property
    def samples(self) -> pd.DataFrame:
        """Motion samples. Degrades to parquet reload if Trip is GC'd."""
        return self._resolve_data().iloc[self.start_idx:self.end_idx]

    @property
    def stop_samples(self) -> pd.DataFrame:
        """Stop samples (trailing stop, inclusive)."""
        return self._resolve_data().iloc[self.stop_start_idx:self.stop_end_idx]

    @property
    def stop_duration_after(self) -> float:
        """Duration of trailing stop in seconds. Derived from stop_samples."""
        ...

    def _resolve_data(self) -> pd.DataFrame:
        trip = self._trip_ref() if self._trip_ref else None
        if trip is None:
            return pd.read_parquet(self.trip_file)
        return trip.data
```

**Design notes:**
- **weakref-first, degrade to file reload.** The weakref is live during normal pipeline execution (in-memory speed). On reload, `trip_file` is the stable key.
- `_trip_ref` is a `PrivateAttr` — excluded from Pydantic serialisation by design.
- **Parquet index stability invariant:** Row order in the parquet file must be preserved and match the original Trip DataFrame. Indices are positional (`iloc`). This invariant must be enforced at Trip write time.
- I/O is isolated behind `_resolve_data()`. Parquet loading does not leak into other methods.

### 4.2 `Trip`

```python
class Trip:
    data: pd.DataFrame    # Owns the parent DataFrame
    file: Path            # Path to parquet backing store
    microtrips: list[Microtrip]
```

Trip owns the DataFrame. Microtrips hold indices and a weakref back to Trip.

---

## 5. Segmentation Algorithm

### 5.1 Architecture: Two-Stage Design

Segmentation is split into two functions with a clean interface boundary:

```
detect_boundaries(speed, config) → list[SegmentBoundary]
build_microtrips(trip, boundaries, config) → list[Microtrip]
```

This separation allows `detect_boundaries` to be tested in isolation against raw speed arrays without requiring a full `Trip` object.

### 5.2 `SegmentBoundary`

```python
@dataclass
class SegmentBoundary:
    motion_start_idx: int
    motion_end_idx: int
    stop_start_idx: int
    stop_end_idx: int
```

Both motion and stop boundaries are derived from the same speed signal pass in stage 1. Stage 2 constructs objects only.

### 5.3 `detect_boundaries`

```python
def detect_boundaries(
    speed: pd.Series,
    config: SegmentationConfig
) -> list[SegmentBoundary]:
    """
    Detect motion/stop boundaries in a speed signal.

    Args:
        speed: Pre-smoothed speed signal (km/h). Smoothing must be
               applied upstream via ProcessingConfig. Passing raw
               speed will produce subtly incorrect boundaries.
        config: Segmentation parameters.

    Returns:
        List of SegmentBoundary objects. Empty list if no boundaries
        found or if input is degenerate.

    Raises:
        Logs WARNING and returns [] if speed series is all zeros.
        Logs WARNING and returns [] if speed series is shorter than
        microtrip_min_duration_s worth of samples.
    """
```

**Degenerate input handling:**
- All-zero speed series → `logging.warning(...)`, return `[]`
- Series shorter than minimum duration → `logging.warning(...)`, return `[]`
- No valid boundaries found → return `[]` (not `None`, not an exception)

### 5.4 `build_microtrips`

```python
def build_microtrips(
    trip: Trip,
    boundaries: list[SegmentBoundary],
    config: SegmentationConfig
) -> list[Microtrip]:
    """
    Construct, filter, and bind Microtrip objects from detected boundaries.

    Applies duration and distance filters. Binds weakref to parent Trip.
    Returns empty list if no boundaries pass filters.
    """
```

**Filtering order (applied per boundary):**
1. Total duration filter: `(stop_end_idx - motion_start_idx) / sample_rate ≥ microtrip_min_duration_s`
2. Distance filter: cumulative distance over motion samples `≥ microtrip_min_distance_m`
3. Instantiate `Microtrip`, call `.bind(trip)`

---

## 6. Config Traceability

All `SegmentationConfig` and `ProcessingConfig` field values are serialised into each microtrip output record (denormalised). This is a deliberate choice for auditability at the cost of storage redundancy.

**Note:** This design is appropriate at current scale. Revisit if cross-trip analysis datasets grow large enough to make denormalisation costly.

---

## 7. Open Items (Deferred)

| Item | Status | Notes |
|---|---|---|
| Trip identity criteria | Deferred | Working assumption: ignition-bounded. Requires RPM or ignition signal — not currently in all OBDII logs. |
| Cold-start annotations | Deferred | Requires ignition state or RPM proxy. Flag as known limitation. |
| WLTP class assignment | Out of scope | Downstream of this module. |
| Metric definitions | Out of scope | Not part of this spec. |
| `PipelineConfig` versioning | Deferred | Relevant when filtering or additional components are added. |

---

## 8. Invariants and Constraints Summary

| Invariant | Enforcement |
|---|---|
| Parquet row order matches Trip DataFrame | Documented — enforced at Trip write time |
| `microtrip_min_duration_s ≥ 5.0` | Pydantic validator |
| `detect_boundaries` receives pre-smoothed speed | Documented in docstring |
| Stop samples belong to closing microtrip | Architectural — stop indices stored in `Microtrip` |
| Empty result → `[]` not `None` | Convention — documented here |
| I/O isolated to `_resolve_data()` | Structural |
