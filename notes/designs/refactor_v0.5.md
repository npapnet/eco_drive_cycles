# Refactor v0.5 — Modular In-Place Workflow & Synthesis Package

**Status:** Planning (2026-05-21)  
**Builds on:** refactor_v0.3.md (pipeline), microtrip_design_spec.md (segmentation)

---

## Session Notes (read before starting)

**Feature branch:** `git flow feature start refactor-v0.5` (cut from `develop`)  
**First action on a new machine:** sync the branch, then start Step 1.

**Key architectural decisions locked during planning:**

- `MicrotripCollection` is a **container only** (`microtrip_collection.py`). No synthesis methods on it. Public API: `from_parquets(dir, summary_csv=None)`, `from_trip_collection(tc, segmenter)`, `__iter__`, `__len__`, `summary`, `is_persisted`, `rank(group_col, metrics=None, measure=pct_deviation)`.
- `is_persisted` is `True` only for collections built via `from_parquets()`. `synthesize()` raises `ValueError` if called with a non-persisted collection.
- `Microtrip` gets two new `PrivateAttr` fields: `_df` (data for standalone mode) and `_path` (own saved Parquet path, exposed as `mt.path`). `trip_file` (parent trip's Parquet path) is kept for traceability.
- `Clusterer` is a Protocol with `fit(summary: pd.DataFrame) -> pd.Series`. `KMeansClusterer` is the first implementation. `DBSCANClusterer` deferred to TODOS P2.
- `synthesize(mc, assignments, config)` is the single synthesis entry point. `assignments: pd.Series` (index=microtrip id, values=group label) is source-agnostic — WLTP rules, KMeans, DBSCAN, or manual.
- `SynthesisConfig = WLTPSynthesisConfig | ClusterSynthesisConfig` (type alias, not a base class).
- DuckDB dropped from CLI entirely. `TripCollection.from_duckdb_catalog()` stays in the package — update its docstring to note it is not currently used by any CLI subcommand.
- `dcc analyze` after DuckDB removal: reads `metrics.csv` with pandas directly, constructs fleet matrix from metric columns, calls similarity functions from `dcc.similarity`. No new `TripCollection` constructor needed — `TripCollection` is intentionally bypassed in this CLI path.
- `dcc synthesize` CLI subcommand is **out of scope** — synthesis runs from workflow scripts during the research phase.
- `metric_weights` in `SynthesisSelectionConfig` (Step 2): fill in real defaults from `examples/workflow/config_wltp.json` before implementing.
- Plotting code (`062_plot_representatives.py`) stays in workflow scripts — the package returns data, never figures.

---

## Context

The `examples/workflow/` scripts proved the end-to-end pipeline is sound, but they contain ~2 000 lines of duplicated synthesis logic spread across two near-identical paths (WLTP `100`-series and cluster `200`-series). Several concerns motivate this refactor:

1. **Promotion**: Business logic in workflow scripts belongs in the package so it can be tested, versioned, and reused.
2. **Deduplication**: The Markov chain, target computation, stochastic selection, and cycle assembly algorithms are copy-pasted between the two synthesis paths — they must be unified into a single `dcc.synthesis` subpackage.
3. **Directory model**: The current CLI forces a split between raw data and output (`dcc ingest <raw_dir> <out_dir>`). The preferred model is a self-contained project directory with fixed subdirectory names (`raw/`, `trips/`, `microtrips/`, `reports/`, `analyses/`).
4. **Config formalization**: The ad-hoc `config*.json` files used by workflow scripts should be backed by Pydantic models so the CLI and the library share the same validated structures.

---

## New Directory Convention

```
<project_dir>/
├── raw/                             ← raw OBD exports (xlsx/csv)
│   └── metadata-<project_dir>.yaml  ← user/vehicle metadata (produced by dcc config-init)
├── trips/                           ← v2 archive Parquets (produced by dcc ingest)
├── microtrips/                      ← per-trip microtrip Parquets (produced by dcc segment)
├── reports/                         ← per-trip QA reports (produced by dcc segment)
└── analyses/
    ├── dcca-<ts>/                   ← similarity analysis outputs (produced by dcc analyze)
    └── synth-<ts>/                  ← synthesized cycle outputs (produced by workflow scripts)
```

`dcc config-init .` (or `dcc config-init <project_dir>`) searches for a `raw/` subfolder and writes `raw/metadata-<project_dir_name>.yaml` there. The YAML name uses the **parent directory name**, not `raw/` (e.g., project dir `2019-opsimoulis/` → `raw/metadata-2019-opsimoulis.yaml`). `dcc ingest` reads the YAML from `raw/` automatically.

`dcc ingest <project_dir>` reads from `<project_dir>/raw/` and writes Parquets to `<project_dir>/trips/`. The two-argument form `dcc ingest <raw_dir> <out_dir>` is retained for backward compatibility.

---

## Migration Strategy

Work on a single gitflow feature branch (`feature/refactor-v0.5` cut from `develop`). Edit `examples/workflow/` scripts **in place** as each step is implemented — no parallel directories. The feature branch itself is the reference: use the editor's git diff against `develop` to see the old vs. new version of any script at any time.

Each step in the plan below ends with updating the corresponding workflow script to call the new package API. When the feature branch is merged, `examples/workflow/` reflects the current package state with full git history of every change.

---

## Implementation Steps

Each step is a self-contained deliverable with its own tests. Complete one before starting the next.

---

### Step 1 — In-Place Ingest & Project Layout

**What to implement:**

- Modify `cli/ingest.py`: when called with one argument, treat it as `<project_dir>`, look for a `raw/` subfolder, and write Parquets to `<project_dir>/trips/`. Raise a clear error (not a Python traceback) if `raw/` does not exist.
- Modify `cli/config_init.py`: `dcc config-init .` (or any project dir) searches for `raw/`, derives the template name from the **parent** directory name, and writes `raw/metadata-<parent>.yaml`. Raises a clear error if `raw/` is missing.
- Modify `cli/ingest.py`: reads metadata YAML from `raw/` automatically (no separate `--metadata` flag needed in the single-arg form).
- Modify `cli/extract.py`: **drop DuckDB output entirely**; default to CSV only. Output goes to `<project_dir>/analyses/<timestamp>/metrics.csv`. This aligns with the single-user, local-first model — DuckDB integration is deferred to a future milestone (6–12 months out).
- Modify `cli/analyze.py`: update to load from the metrics CSV produced by `extract` instead of `metrics.duckdb`. `TripCollection.from_duckdb_catalog()` stays in the package (not removed) but drops out of the CLI path.
- Add a helper `_project_layout(project_dir: Path)` (private, in a new `cli/_layout.py`) that returns the canonical subdirectory paths (`trips`, `microtrips`, `reports`, `analyses`) and creates them on first use. See rationale below.

**Files to modify:**
- `src/drive_cycle_calculator/cli/ingest.py`
- `src/drive_cycle_calculator/cli/config_init.py`
- `src/drive_cycle_calculator/cli/extract.py`
- `src/drive_cycle_calculator/cli/analyze.py`
- `src/drive_cycle_calculator/cli/_layout.py` (new — rationale discussed separately)

**Tests to add** (`tests/test_cli_ingest.py`, `tests/test_cli_config_init.py`):
- Single-arg ingest resolves `raw/` correctly and creates `trips/`
- Single-arg ingest with missing `raw/` prints a clear error, exit code 1
- Two-arg form still works (backward-compat)
- `config-init` writes YAML inside `raw/` with the parent-dir name
- `extract` produces a CSV and does not create a `.duckdb` file

**Rationale for `_layout.py`:** Every CLI subcommand (`ingest`, `extract`, `segment`, `analyze`) needs to resolve the same canonical paths (`trips/`, `microtrips/`, etc.) and create them if absent. The paths are always relative to a runtime `project_dir` argument, so a constants dict of string names doesn't help — each subcommand would still have to write `project_dir / SUBDIRS["trips"]` and call `mkdir` itself. Centralising into a single function eliminates that repetition: one call returns a named tuple of ready-to-use `Path` objects with subdirs already created.

**Verification:** Run `dcc ingest .` from a directory that has a `raw/` subfolder; confirm `trips/` appears. Run `dcc extract .`; confirm no `.duckdb` file is created and a CSV appears in `analyses/`.

---

### Step 2 — Config Pydantic Models

**Context:** The workflow scripts read three separate JSON files. This step introduces typed models for them so they can be validated, documented, and used directly from the CLI.

**What to implement:**

Add to `schema.py`:

```python
class MarkovConfig(BaseModel):
    speed_bin_width_kmh: float = 5.0
    acc_bin_width_ms2: float = 0.1
    acc_range_ms2: float = 2.0
    markov_lambda: float = 0.5

class SynthesisSelectionConfig(BaseModel):
    n_trials: int = 1000
    f_threshold: float = 0.05
    max_reuse_fraction: float = 0.4
    random_seed: int = 42
    metric_weights: dict[str, float] = {...}

class WLTPSynthesisConfig(BaseModel):
    markov: MarkovConfig = MarkovConfig()
    selection: SynthesisSelectionConfig = SynthesisSelectionConfig()
    inter_phase_idle_s: int = 20
    phase_min_distance_m: dict[str, float] = {"Low": 3000, "Med": 4756, "High": 7162, "xHigh": 8254}

class ClusterSynthesisConfig(BaseModel):
    markov: MarkovConfig = MarkovConfig()
    selection: SynthesisSelectionConfig = SynthesisSelectionConfig()
    inter_cluster_idle_s: int = 20
    cluster_min_distance_m: float = 3000.0
```

All models support `model_validate_json(Path.read_text())` — existing JSON files work unchanged.

**Files to modify:**
- `src/drive_cycle_calculator/schema.py`
- `src/drive_cycle_calculator/__init__.py` (re-export new models)

**Tests to add** (`tests/test_schema.py`):
- Round-trip: JSON → model → JSON preserves all fields
- Defaults validate without a JSON file
- Unknown fields in JSON raise `ValidationError`
- Existing `config_wltp.json` and `config_syn_cluster.json` parse cleanly

**Note on Pydantic:** These are additive changes. No existing models change. Pydantic `BaseModel` gives you `.model_dump_json()` and `model_validate_json()` for free — the pattern is identical to `SegmentationConfig` already in `schema.py`.

---

### Step 3 — Microtrip Persistence & MicrotripCollection

**Context:** `030_build_microtrips.py` saves each microtrip as a Parquet and writes a `summary.csv`. This logic belongs in the package. This step also introduces `MicrotripCollection` — the primary public API for everything microtrip-level (ranking, synthesis) in Steps 4–6.

**Microtrip dual-mode resolution:**

`Microtrip` currently holds only iloc indices into a parent `Trip`'s DataFrame (D1 design: no parquet reload fallback). `MicrotripCollection.from_parquets()` needs microtrips that load from disk without a live parent. Rather than a separate class, follow the same pattern `Trip` already uses for lazy loading: add a `_df: pd.DataFrame | None` field. `samples` checks `_df` first; if `None`, goes through the weakref as before. D1 is preserved for the segmentation path; `from_parquet()` is the explicit opt-out.

```python
@property
def samples(self) -> pd.DataFrame:
    if self._df is not None:       # standalone: loaded from parquet
        return self._df
    trip = self._trip_ref()        # bound: in-memory segmentation
    if trip is None:
        raise RuntimeError("Parent trip has been garbage collected")
    return trip.data.iloc[self.start_idx:self.end_idx]
```

**Pydantic PrivateAttr note:** `Microtrip` is a Pydantic model. `_df` must be declared as `_df: pd.DataFrame | None = PrivateAttr(default=None)`, matching the existing `_trip_ref` pattern. Plain underscore attributes are silently ignored by Pydantic v2.

**New fields on `Microtrip`** (both `PrivateAttr`, matching existing `_trip_ref` pattern):
- `_df: pd.DataFrame | None = PrivateAttr(default=None)` — holds data for standalone microtrips loaded from disk.
- `_path: Path | None = PrivateAttr(default=None)` — the microtrip's own saved Parquet path, exposed as `mt.path`. Distinct from `trip_file` (the parent trip's path). `None` for in-memory segmentation-only microtrips.

**Lifecycle:** `from_trip_collection()` is for the segment-and-immediately-inspect workflow — microtrips are weakref-bound to live `Trip` objects (D1 applies). It is **not** the entry point for synthesis. For synthesis, always save first via `export_collection()` then reload with `from_parquets()`. This ensures microtrips are self-contained and `Trip` objects can be GC'd safely.

**What to implement:**

1. `Microtrip.to_parquet(dest: Path) -> None` — writes motion+stop samples (processed columns only). Sets `self._path = dest` so the microtrip becomes self-locating.
2. `Microtrip.from_parquet(path: Path) -> "Microtrip"` — loads standalone microtrip; sets `_df` directly, no weakref. `trip_file` is preserved in Parquet metadata for traceability but not required for data access.
3. `MicrotripSegmenter.export_collection(result: dict[str, list[Microtrip]], dest: Path) -> pd.DataFrame` — saves all microtrips, returns summary DataFrame (`trip_id`, `microtrip_idx`, `path`, `duration_s`, `distance_m`, `mean_speed_kmh`).
4. **`MicrotripCollection`** (new file `microtrip_collection.py`):

```python
class MicrotripCollection:
    # Construction
    @classmethod
    def from_parquets(cls, directory: Path, summary_csv: Path | None = None) -> "MicrotripCollection": ...
    @classmethod
    def from_trip_collection(cls, tc: TripCollection, segmenter: MicrotripSegmenter) -> "MicrotripCollection": ...

    # Self-carrying identity — no external dir variable needed
    def __iter__(self) -> Iterator[Microtrip]: ...   # each mt carries its own .path
    def __len__(self) -> int: ...
    @property
    def summary(self) -> pd.DataFrame: ...           # one row per microtrip, all metrics + path

    @property
    def is_persisted(self) -> bool: ...
    # True when every microtrip has its own _path set (i.e. collection was built via
    # from_parquets()). False when built via from_trip_collection() — microtrips are
    # weakref-bound to live Trip objects and will raise RuntimeError if those trips are
    # GC'd. Only persisted collections may be passed to synthesize().

    # Analysis (Step 6)
    def rank(self, group_col: str, metrics: list[str] | None = None, measure: SimilarityMeasure = pct_deviation) -> pd.DataFrame: ...
```

`summary` is the single source of truth for downstream steps — it replaces the external `MICROTRIPS_DIR` variable pattern in the workflow scripts. Iterate with `for mt in mc` to access data; query with `mc.summary` to filter or group.

`summary_csv` allows loading pre-computed cluster assignments: after `040` produces `summary_clustered.csv`, the user constructs `MicrotripCollection.from_parquets(dir, summary_csv=clustered_csv)` and the extra columns (e.g. `cluster_id`) are available in `mc.summary` for synthesis.

`MicrotripCollection` is a **container only** — it does not orchestrate synthesis. Synthesis methods live in `dcc.synthesis` and accept `mc` as an argument (see Step 4–5).

5. **`clustering.py`** (new file) — `Clusterer` Protocol + `KMeansClusterer`:

```python
class Clusterer(Protocol):
    def fit(self, summary: pd.DataFrame) -> pd.Series: ...
    # index = microtrip id, values = group label

class KMeansClusterer:
    def __init__(self, n_clusters: int, features: list[str] | None = None, random_state: int = 42): ...
    def fit(self, summary: pd.DataFrame) -> pd.Series: ...
    # selects feature columns, scales, runs sklearn KMeans, returns labels
```

`DBSCANClusterer` and other algorithms are deferred to TODOS.md (P2). `040_microtrip_clustering.py` is updated to use `KMeansClusterer.fit(mc.summary)` and write the resulting `pd.Series` merged into `summary_clustered.csv`. Synthesis functions receive `assignments: pd.Series` — the source algorithm is irrelevant to them.

6. `dcc segment <project_dir>` CLI subcommand: loads `trips/`, segments, writes `microtrips/` + `reports/microtrip_summary.csv`.

**Files to modify/create:**
- `src/drive_cycle_calculator/microtrip.py`
- `src/drive_cycle_calculator/microtrip_collection.py` (new)
- `src/drive_cycle_calculator/clustering.py` (new)
- `src/drive_cycle_calculator/segmentation.py` (add `export_collection`)
- `src/drive_cycle_calculator/__init__.py` (re-export `MicrotripCollection`, `KMeansClusterer`, `Clusterer`)
- `src/drive_cycle_calculator/cli/segment.py` (new)
- `src/drive_cycle_calculator/cli/main.py` (register `segment` sub-app)

**Tests to add** (`tests/test_microtrip_persistence.py`, `tests/test_microtrip_collection.py`):
- `to_parquet` / `from_parquet` round-trip preserves `samples` shape and column names
- Bound microtrip raises `RuntimeError` when parent Trip is GC'd (D1 still holds)
- Standalone microtrip (`from_parquet`) does not raise on `samples` access
- `MicrotripCollection.from_parquets()` length matches file count; `summary` has correct row count
- `for mt in mc: mt.path` is always a valid, existing path
- `from_parquets()` → `is_persisted` is `True`; `from_trip_collection()` → `is_persisted` is `False`
- `KMeansClusterer.fit(summary)` returns a `pd.Series` of length `len(summary)` with integer labels

---

### Step 4 — Synthesis Subpackage (Dedup 100/200 Series)

**Context:** This is the largest step. The WLTP (`110`–`150`) and cluster (`210`–`250`) synthesis scripts are 90–100% duplicated. They all operate on the same abstractions: groups of microtrips → Markov matrix → targets → stochastic selection → assembled cycle. The only difference is how microtrips are assigned to groups.

**New subpackage:** `src/drive_cycle_calculator/synthesis/`

```
synthesis/
├── __init__.py       — re-exports public API
├── markov.py         — state discretization + Markov matrix construction
├── targets.py        — per-group kinematic target computation
├── selection.py      — stochastic microtrip selection (objective function)
└── assembly.py       — junction smoothing + cycle assembly + validation
```

**`markov.py` public API:**
```python
def discretize_states(df: pd.DataFrame, config: MarkovConfig) -> pd.Series
    """Add 'state' column: (speed_bin, acc_bin) label for each sample."""

def build_transition_matrix(states: pd.Series) -> pd.DataFrame
    """Return normalized transition matrix from consecutive-state pairs."""

def frobenius_distance(m1: pd.DataFrame, m2: pd.DataFrame) -> float
    """||M1 - M2||_F — used in selection objective."""
```

**`targets.py` public API:**
```python
def compute_targets(
    summary: pd.DataFrame,
    group_col: str,
    metric_weights: dict[str, float],
) -> dict[str, dict[str, float]]
    """Duration-weighted mean of mean_speed, RPA, idle_fraction, speed_95th per group."""
```

**`synthesis/__init__.py` — top-level entry point:**

`SynthesisConfig` is a type alias, not a base class — no inheritance needed:
```python
SynthesisConfig = WLTPSynthesisConfig | ClusterSynthesisConfig

def synthesize(
    mc: MicrotripCollection,
    assignments: pd.Series,
    config: SynthesisConfig,
) -> pd.DataFrame:
    if not mc.is_persisted:
        raise ValueError(
            "synthesize() requires a persisted MicrotripCollection. "
            "Call export_collection() then MicrotripCollection.from_parquets() first."
        )
    ...
```

**`selection.py` public API:**
```python
def select_microtrips(
    candidates: pd.DataFrame,
    group: str,
    target: dict[str, float],
    global_matrix: pd.DataFrame,
    config: SynthesisSelectionConfig,
) -> list[str]
    """Stochastic selection: returns list of microtrip Parquet paths for this group."""
```

**`assembly.py` public API:**
```python
def smooth_junction(a: pd.Series, b: pd.Series, ramp_s: int = 3) -> pd.Series
    """Linear velocity ramp between two microtrip speed traces."""

def assemble_cycle(
    groups: list[tuple[str, list[Path]]],
    idle_s: int,
    config: MarkovConfig,
) -> pd.DataFrame
    """Concatenate selected microtrips with idle segments; return speed-time series."""

def validate_cycle(
    cycle: pd.DataFrame,
    targets: dict[str, dict],
    tolerances: dict[str, float],
) -> dict[str, bool]
    """Check each group's kinematic stats against targets+tolerances."""
```

**Files to create:**
- `src/drive_cycle_calculator/synthesis/__init__.py`
- `src/drive_cycle_calculator/synthesis/markov.py`
- `src/drive_cycle_calculator/synthesis/targets.py`
- `src/drive_cycle_calculator/synthesis/selection.py`
- `src/drive_cycle_calculator/synthesis/assembly.py`

**Files to modify:**
- `src/drive_cycle_calculator/__init__.py` (optionally re-export synthesis entry points)

**Tests to add** (`tests/test_synthesis_*.py` — one file per module):
- `markov.py`: known transition sequence → expected matrix values
- `targets.py`: weighted mean calculation with known inputs
- `selection.py`: mock candidates → objective function returns finite float; min-distance constraint respected
- `assembly.py`: two-microtrip assembly produces correct idle gap; validation passes when targets met

---

### Step 5 — WLTP & Cluster Adapters

**Context:** With the shared core in place (Step 4), the WLTP and cluster paths each need only a thin adapter that assigns microtrips to groups.

**New files:**
- `src/drive_cycle_calculator/synthesis/wltp.py`
- `src/drive_cycle_calculator/synthesis/cluster.py`

**`wltp.py` public API** (implementation only — called by workflow scripts via `synthesize()`):
```python
WLTP_PHASE_BOUNDS: dict[str, tuple[float, float]]  # Low/Med/High/xHigh speed ranges

def assign_wltp_phases(summary: pd.DataFrame) -> pd.Series
    """Classify each microtrip into Low/Med/High/xHigh by max_speed_kmh."""
```

**`cluster.py` public API** (implementation only — called by workflow scripts via `synthesize()`):
```python
def assign_clusters(summary: pd.DataFrame, cluster_col: str = "cluster_id") -> pd.Series
    """Read cluster assignments already present in summary."""
```

The synthesis functions accept `mc` + `assignments` — the source of the assignments (WLTP rules, KMeans, DBSCAN, manual) is irrelevant to the synthesis pipeline:

```python
from dcc.synthesis import synthesize
from dcc.synthesis.wltp import assign_wltp_phases

mc = MicrotripCollection.from_parquets(project_dir / "microtrips")

# WLTP path: phase assignment is a helper, not synthesis itself
assignments = assign_wltp_phases(mc.summary)     # pd.Series: microtrip_id → "Low"/"Med"/"High"/"xHigh"
cycle = synthesize(mc, assignments, wltp_config)

# Cluster path: assignments come from KMeansClusterer output saved in summary_clustered.csv
mc_clustered = MicrotripCollection.from_parquets(dir, summary_csv=clustered_csv)
assignments = mc_clustered.summary["cluster_id"]
cycle = synthesize(mc_clustered, assignments, cluster_config)
```

**CLI synthesis subcommand is out of scope for this refactor.** The synthesis pipeline is best driven from workflow scripts during the research phase, where config tuning and intermediate inspection are needed. A `dcc synthesize` CLI subcommand can be added in a future milestone once the algorithms stabilise.

**Tests to add:**
- End-to-end with synthetic microtrips + known assignments: output cycle has correct number of groups
- `assign_wltp_phases` classifies correctly at boundary speeds
- Config validation: unknown phase name in `phase_min_distance_m` raises `ValidationError`

---

### Step 6 — MicrotripCollection.rank()

**Context:** `060_select_representatives.py` ranks microtrips by similarity to their group mean. `062_plot_representatives.py` plots the top-N speed traces. Plotting stays in the workflow scripts — the package returns data, not figures. The ranking logic (`060`) is thin enough that it does not need a standalone module; it belongs as `MicrotripCollection.rank()`, stubbed in Step 3 and implemented here.

**What to implement:**

`MicrotripCollection.rank(group_col, measure)` — already declared in Step 3. The measure *functions* from `similarity/` (pct_deviation, etc.) are reused directly; they operate on any numeric vector. The metric *columns* used for ranking are microtrip-specific (`mean_speed_kmh`, `rpa`, `idle_fraction`, `speed_95th`) and are selected via the `metrics` parameter — they are not the same as the 7 trip-level metrics in `TripCollection`.

```python
mc = MicrotripCollection.from_parquets(project_dir / "microtrips")
ranked = mc.rank(group_col="cluster_id")
# ranked is mc.summary with added 'score' and 'rank' columns per group
# workflow script uses ranked to drive its own matplotlib output
```

`060_select_representatives.py` becomes: load → `mc.rank()` → write CSV + pass to plotting script. No package changes to plotting.

**Files to modify:**
- `src/drive_cycle_calculator/microtrip_collection.py` (implement `rank`)

**Tests to add** (`tests/test_microtrip_collection.py`, extending Step 3 file):
- Two-group summary → top-ranked microtrip is the one closest to its group mean
- Ranking is stable when scores are tied (deterministic order)

---

### Step 7 — Workflow Scripts as Thin Wrappers

Update `examples/workflow/` scripts to use the new package APIs. Each script becomes a ~20-line call into the package, retaining only:
- Config loading
- Path setup
- One-line calls into `dcc.*` functions
- Optional matplotlib output

Scripts to update:

| Script | New package call |
|---|---|
| `010_ingest.py` | Already thin — update paths for new layout |
| `020_extract_analyze.py` | Already thin — update paths |
| `030_build_microtrips.py` | Replace with `MicrotripSegmenter.export_collection()` → `MicrotripCollection` |
| `040_microtrip_clustering.py` | Minimal change (sklearn stays in examples; assigns `cluster_id` to summary CSV) |
| `050/051` visualisation | No change — plotting stays in scripts |
| `060_select_representatives.py` | Replace with `mc.rank(group_col=...)` → write CSV → pass to 062 |
| `062_plot_representatives.py` | No change — reads ranked CSV and plots; no package promotion |
| `synthesis-wltp/100-150` | Replace with `assign_wltp_phases(mc.summary)` → `synthesize(mc, assignments, config)` |
| `synthesis-cluster/200-250` | Load `summary_clustered.csv` → `synthesize(mc, assignments, config)` |

Delete the now-redundant internal helper functions from the synthesis sub-scripts (everything moved to `dcc.synthesis`).

---

### Step 8 — Tests, Documentation & Cleanup

**Tests:**
- Integration test: run Step 1–5 pipeline end-to-end with the existing `data/trips/` Parquets (using real data)
- Update `conftest.py` fixtures: add a `project_dir` fixture that creates the full subdirectory layout with a few synthetic trips

**Docs to update:**
- `architecture.md`: add `synthesis/` and `clustering.py` sections; update CLI table with `dcc segment`; update directory layout diagram; document `mean_ns` explicitly as mean speed excluding stops, and note the derivation `mean_speed_with_stops ≈ mean_ns × (1 − idle_fraction)`
- `notes/designs/cli-subcommands.md`: add `dcc segment` entry
- Sphinx: module pages for `synthesis.markov`, `synthesis.targets`, `synthesis.selection`, `synthesis.assembly`, `synthesis.wltp`, `synthesis.cluster`, `clustering`

**Cleanup:**
- `TODOS.md`: mark P1 "Candidate Cycle Assembly" and P1 "Modular In-Place Workflow" complete; add P2 "GUI Parquet path fix" and P2 "DBSCANClusterer + additional clustering algorithms" as next priorities
- `CHANGELOG.md`: append v0.5.0 entry
- `trip_collection.py`: update `from_duckdb_catalog()` docstring to note it is retained for future use but not currently invoked by any CLI subcommand

---

## Pydantic Notes (for reference)

No existing Pydantic models change. New models in Steps 2 and later follow the same pattern as `SegmentationConfig` in `schema.py`:

```python
class MyConfig(BaseModel):
    field: float = 1.0          # typed + default
    nested: OtherModel = OtherModel()  # composed models

# Load from JSON file:
cfg = MyConfig.model_validate_json(Path("config.json").read_text())
# Save to JSON:
Path("config.json").write_text(cfg.model_dump_json(indent=2))
```

Inheritance (`WLTPSynthesisConfig` inherits from nothing special — both WLTP and cluster configs just share the `MarkovConfig` and `SynthesisSelectionConfig` as nested fields, not through inheritance) keeps the models simple and independently serializable.

---

## Step Ordering Rationale

Steps 1 and 2 are prerequisites (layout + models) for everything downstream.  
Step 3 (microtrip persistence) is prerequisite for Step 4 (synthesis needs to load saved microtrips).  
Steps 4 → 5 (shared core → adapters) follow naturally.  
Step 6 (representative selection) is independent and can run in parallel with Step 4.  
Steps 7 and 8 are integrative and should be last.
