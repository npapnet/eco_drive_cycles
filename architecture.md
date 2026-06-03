# Architecture

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data to compute
eco-driving scores and synthesize representative drive cycles.

Research and prototype repository. Processes real-world driving data collected via the
Torque app (OBD-II), computes trip metrics, identifies representative drive cycles, and
supports WLTP-style candidate cycle synthesis.

Raw driving-cycle data (`_data/`, `raw_data/`) was collected via the Torque app and
exported as CSV/XLSX. Archived v2 Parquets are in `data/trips/`.

---

## Pipeline

```
Raw .xlsx / .csv (OBD-II)
  → dcc config-init <folder>              # generate metadata-<folder>.yaml template
  [user fills in metadata-<folder>.yaml]
  → dcc ingest <raw_dir> <out_dir>        # raw file → uniform 1 Hz resampled archive Parquet
                                          # checks gaps, embeds metadata, NO DuckDB created

Archive Parquet (uniform 1 Hz time series + ParquetMetadata)
  → dcc extract <data_dir>               # read parquets → apply ProcessingConfig → output
  → DuckDB / CSV / XLSX (trip_metrics)   # metrics + metadata + config snapshot

DuckDB (trip_metrics table)
  → dcc analyze <data_dir>               # similarity scores, representative trip

Trip (in-memory, produced by OBDFile.to_trip() or TripCollection loaders)
  → MicrotripSegmenter(config).segment(trip)   # detect_boundaries() → build_microtrips()
  → trip.microtrips / trip.segmentation_config # stored on trip after segmentation
  → list[Microtrip]                            # motion segments for cycle construction

  # Collection-level entry point:
  → MicrotripSegmenter(config).segment_collection(tc)  # dict[str, list[Microtrip]]

---

## Project Directory Structure

```
<project_dir>/
├── raw/                             ← raw OBD exports (xlsx/csv)
│   └── metadata-<project_dir>.yaml  ← user/vehicle metadata (produced by dcc config-init)
├── trips/                           ← v2 archive Parquets (produced by dcc ingest)
├── microtrips/                      ← per-trip microtrip Parquets (produced by dcc segment)
├── reports/                         ← per-trip QA reports (produced by dcc segment)
└── analyses/
    ├── dcca-<ts>/                   ← similarity analysis outputs (produced by dcc extract/analyze)
    └── synth-<ts>/                  ← synthesized cycle outputs (produced by workflow scripts)
```

```

---

## Package (`src/drive_cycle_calculator/`)

The active calculation layer. All business logic lives here.

### File structure

```
src/drive_cycle_calculator/
├── __init__.py              — version string; re-exports OBDFile, Trip, TripCollection, MicrotripCollection
├── schema.py                — OBD_COLUMN_MAP, CURATED_COLS; Pydantic models: FuelType,
│                              VehicleCategory, UserMetadata, IngestProvenance,
│                              ComputedTripStats, ParquetMetadata, SegmentationConfig,
│                              MarkovConfig, SynthesisSelectionConfig, WLTPSynthesisConfig,
│                              ClusterSynthesisConfig; generate_yaml_template()
├── gps_time_parser.py       — GpsTimeParser
├── clustering.py            — Clusterer Protocol and KMeansClusterer
├── obd_file.py              — OBDFile
├── processing_config.py     — ProcessingConfig, DEFAULT_CONFIG
├── microtrip.py             — Microtrip (Pydantic model, lazy load / weakref data access)
├── microtrip_collection.py  — MicrotripCollection (container for microtrips, ranking)
├── segmentation.py          — SegmentBoundary, detect_boundaries(), build_microtrips(),
│                              MicrotripSegmenter, export_collection()
├── trip.py                  — Trip
├── trip_collection.py       — TripCollection, _SEVEN_METRIC_KEYS
├── cli/                     — CLI subpackage (Typer)
│   ├── main.py              — app entry point; registers all sub-apps
│   ├── config_init.py       — dcc config-init
│   ├── ingest.py            — dcc ingest
│   ├── extract.py           — dcc extract
│   ├── segment.py           — dcc segment
│   ├── analyze.py           — dcc analyze
│   └── gui.py               — dcc gui
├── synthesis/               — subpackage for drive cycle synthesis
│   ├── __init__.py          — synthesize() entry point
│   ├── markov.py            — state discretization and transition matrix calculations
│   ├── targets.py           — compute_targets()
│   ├── selection.py         — select_microtrips()
│   ├── assembly.py          — junction smoothing and cycle assembly
│   ├── wltp.py              — assign_wltp_phases()
│   └── cluster.py           — assign_clusters()
├── similarity/              — pluggable similarity measures subpackage
│   ├── __init__.py          — re-exports SimilarityMeasure, pct_deviation,
│   │                          cosine_similarity, z_score_distance
│   └── measures.py          — SimilarityMeasure Protocol + all implementations
└── vis/                     — visualisation subpackage (stub, not yet populated)
```

### Key classes

**`OBDFile(df, name, strict=True)`** — wraps one raw OBD recording.
Constructors (all accept `strict: bool = True`):
- `from_xlsx(path)`, `from_csv(path, sep, decimal)`, `from_parquet(path)` — format-specific
- `from_file(path)` — dispatches by extension (`.xlsx`/`.xls`/`.csv`)

Strict mode (default, always used by CLI): missing curated columns → `ValueError`.
Permissive mode (`strict=False`, library/debug use only): missing columns → NaN injected.

Key methods: `to_parquet(path, user_metadata)` (v2 format with embedded `ParquetMetadata`),
`to_trip(config)`, `quality_report()`, `get_metrics(config)`.
Properties: `curated_df`, `full_df`, `parquet_name` (canonical filename stem).

---

**`ProcessingConfig(window=4, stop_threshold_kmh=2.0)`** — Pydantic `BaseModel` in `processing_config.py`.
- `config_hash`: first 8 hex chars of md5 of sorted JSON fields.
- `config_snapshot`: `model_dump_json()` — full field values as JSON string.
- Stored in DuckDB `trip_metrics` alongside computed metrics.

---

**`SegmentationConfig(stop_threshold_kmh=2.0, stop_min_duration_s=1.0, microtrip_min_duration_s=15.0, microtrip_min_distance_m=50.0)`** — Pydantic `BaseModel` in `schema.py`.
Passed to `Trip.segment()` at call time; not stored on the Trip.

---

**`Microtrip`** — one motion segment derived from a parent `Trip`.
Fields: `trip_file` (Path), `parquet_id` (str), `start_idx`, `end_idx`,
`stop_start_idx`, `stop_end_idx` (all iloc positions).
Private `_trip_ref: weakref.ref` bound via `bind(trip)`.

**Properties (Data Access)**:
- `samples` (motion DataFrame slice)
- `stop_samples` (trailing-stop slice)
- `stop_duration_after` (float seconds)

**Lifecycle & Persistence**:
- Microtrips are **intermediate disposable artifacts**.
- When saved to disk (e.g. by workflow scripts), they contain only the **processed columns** (the subset derived from `CURATED_COLS`). Original raw data is not preserved in microtrips to save space.
- Data access in-memory raises `RuntimeError` if Trip is GC'd (D1: no parquet reload fallback).
- See `notes/designs/archive/microtrip_design_spec.md`.

---

**`Trip(df, name, stop_threshold_kmh, parquet_id="")`** — one processed session.
`@cached_property` metrics: `duration`, `mean_speed` (mean speed including stops), `mean_speed_no_stops` (mean speed excluding stops), `stop_count`, `stop_pct`, `mean_acceleration`, `mean_deceleration`, `max_speed`.
Properties: `data` (public DataFrame alias), `file` (Path or None).
`segment(config: SegmentationConfig) → list[Microtrip]` — convenience wrapper around `MicrotripSegmenter`.
Stores result on `self._microtrips`; accessible via `trip.microtrips` and `trip.segmentation_config` after the call.

**Note on `mean_ns` (mean non-stop speed)**: This represents the mean speed excluding stops (moving speed). It is stored under the `mean_ns` key inside the metrics dictionary. The property `mean_speed_no_stops` is a direct alias for `mean_ns`.
The mean speed including stops (`mean_speed`) is derived from the non-stop mean speed and the idle fraction via the relation:
`mean_speed ≈ mean_ns × (1 - idle_fraction)` (where `idle_fraction` is equivalent to `stop_pct`).


---

**`TripCollection`** — groups multiple trips.
Constructors:
- `from_folder(path, config)` — loads raw OBD xlsx files via `OBDFile` pipeline
- `from_folder_raw(path)` → `list[OBDFile]` — raw files only, no processing (for QA)
- `from_archive_parquets(path, config)` — loads v2 archive Parquets
- `from_duckdb_catalog(db_path, config)` — loads from DuckDB catalog (legacy)

Methods: `similarity_scores(measure=pct_deviation)`, `find_representative(measure=pct_deviation)`.
Both accept any `SimilarityMeasure` (see `similarity/` subpackage). See `notes/similarity/methodology.md`.

---

**`MicrotripCollection`** — container for microtrips.
Constructors:
- `from_parquets(directory, summary_csv)` — loads persisted microtrips from disk.
- `from_trip_collection(tc, segmenter)` — builds microtrips in-memory from a `TripCollection`.

Methods:
- `rank(group_col, metrics, measure)` — ranks microtrips within each group by similarity to their group mean.

---

**`Clusterer`** — Protocol for microtrip clustering algorithms in `clustering.py`.
Methods:
- `fit(summary)` -> returns a `pd.Series` containing group assignments aligned with the summary index.

**`KMeansClusterer`** — K-Means implementation of `Clusterer`.

---

### Synthesis Subpackage (`synthesis/`)

Unifies the drive cycle synthesis logic (WLTP phase-based and cluster-based synthesis) into a single engine.

Modules:
- `markov` — state discretization and transition matrix calculations.
- `targets` — duration-weighted mean kinematic target computations.
- `selection` — stochastic selection of microtrips satisfying distance and probability targets.
- `assembly` — junction smoothing and drive cycle profile assembly.
- `wltp` — WLTP-specific phase assignment helpers.
- `cluster` — cluster-specific assignment helpers.

Top-level entry point:
- `synthesize(mc, assignments, config)` — runs the full Markov chain synthesis pipeline.

---

### Pydantic metadata models (all in `schema.py`)

Grouped by provenance — each model reflects *who or what is responsible* for its fields:

| Model | Populated by | Fields |
|---|---|---|
| `UserMetadata` | User via `metadata-<folder>.yaml` | `user`, `vehicle_make`, `vehicle_model`, `engine_size_cc`, `year`, `fuel_type`, `vehicle_category`, `misc` |
| `IngestProvenance` | Ingest process | `ingest_timestamp`, `source_filename` |
| `ComputedTripStats` | GPS signal | `start_time`, `end_time`, `gps_lat_mean`, `gps_lat_std`, `gps_lon_mean`, `gps_lon_std` |
| `ParquetMetadata` | Root container | `schema_version`, `software_version`, `parquet_id` (6-char GPS hash) + three sub-models |

`ParquetMetadata` is embedded in every archive Parquet under PyArrow key `"dcc_metadata"` as JSON.

---

### Parquet filename convention

`t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>.parquet`
where `hash6 = sha256(lat_bytes + lon_bytes)[:6]`.

Use `obd.parquet_name` everywhere. `obd.name` (raw filename stem) is NOT used for
Parquet filenames or DuckDB keys.

---

### DuckDB table: `trip_metrics`

Produced by `dcc extract`, not by ingest. One row per trip.
Columns: `trip_id`, `parquet_path`, `parquet_id`, `start_time`, `end_time`,
all `UserMetadata` fields flattened, GPS stats, trip scalar metrics,
`config_hash`, `config_snapshot`.

---

### Processed DataFrame columns

Output of `ProcessingConfig.apply()`:
`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, `speed_kmh`, `co2_g_per_km`,
`engine_load_pct`, `fuel_flow_lph`.

> `speed_ms`, `acceleration_ms2`, `deceleration_ms2` no longer exist. No new code should produce those columns.

### Required OBD-II columns (CURATED_COLS)

`GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km (Average)(g/km)`, `Engine Load(%)`,
`Fuel flow rate/hour(l/hr)`

### Language convention

All internal column names are **English** (`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`,
`speed_kmh`, etc.). Mapping from raw OBD names happens in `_schema.OBD_COLUMN_MAP`
via `ProcessingConfig.apply()`.

---

## CLI Subcommands

| Subcommand | Status | Description |
|---|---|---|
| `dcc config-init <folder>` | New (v0.3) | Write `metadata-<folder>.yaml` template |
| `dcc ingest <project_dir>` | Revised (v0.5) | Raw → archive Parquets. Supports single-argument project directory mode (reads from `raw/` and writes to `trips/`). |
| `dcc segment <project_dir>` | New (v0.5) | Segment archive Parquets into microtrips under `microtrips/` and generate `reports/microtrip_summary.csv`. |
| `dcc extract <data_dir>` | Revised (v0.5) | Parquets → CSV / XLSX with metrics. DuckDB support dropped from CLI. |
| `dcc analyze <data_dir>` | Revised (v0.5) | Similarity analysis from metrics CSV. |
| `dcc gui` | Bug-fix (v0.3) | Uses `parquet_name` scheme |

---

## Other Areas

### Examples (`examples/`)

Thin wrappers and scratchpads. Not guaranteed to be up to date with the current CLI.
Scripts act as tutorials or proof-of-concept for new ideas; not part of the core package.
If a script docstring is marked **OBSOLETE**, offer to update it to use the current CLI approach.

### Frozen Historical Reference (`students/DriveGUI/`)

Self-contained historical reference.

```
Raw .xlsx (OBD-II)
  → calculations.py          # Cleans & derives metrics → writes calculations_log_*.xlsx
  → <metric>_chart.py (×13)  # Each reads the log and renders a Matplotlib chart
```

### Data paths

| Path | Contents |
|---|---|
| `raw_data/` | Raw xlsx/csv from Torque app (source of truth before archiving) |
| `data/trips/` | v2 archive Parquets (permanent source of truth after archiving) |
| `data/metrics.duckdb` | DuckDB metrics output (`trip_metrics` table) |
| `_data/complete_extract/` | Older CSVs organised by driver name |

**Known data-quality issues:**
- Galatas: repeated header rows (potential corruption)
- Stefanakis: inconsistent column names across files
- Kalyvas/9.9.24: different format than other sessions
- Separator (`,`, `;`, `\t`) and decimal separator (`,` vs `.`) vary across folders

---

## Key Documentation

| File | Purpose |
|---|---|
| [refactor_v0.3.md](file:///d:/_sandbox/research/eco_drive_cycles/notes/designs/archive/refactor_v0.3.md) | v0.3 design doc (shipped). Authoritative reference for metadata schema, ingest/extract pipeline, OBDFile strictness. |
| [microtrip_design_spec.md](file:///d:/_sandbox/research/eco_drive_cycles/notes/designs/archive/microtrip_design_spec.md) | Microtrip segmentation spec (shipped 2026-04-23). Two-stage design, Microtrip model, SegmentationConfig. |
| [ingestion-preprocessing.rst](file:///d:/_sandbox/research/eco_drive_cycles/docs/source/theory/ingestion-preprocessing.rst) | Theory documentation explaining raw file parsing, validation, QA filtering, resampling, and Parquet metadata archiving. |
| [microtrip-spec.rst](file:///d:/_sandbox/research/eco_drive_cycles/docs/source/theory/microtrip-spec.rst) | Theory documentation explaining what microtrips are in eco-driving, target configurations, data models, and the two-stage segmentation boundaries. |
| [synthesis-algorithm.rst](file:///d:/_sandbox/research/eco_drive_cycles/docs/source/theory/synthesis-algorithm.rst) | Technical reference for the drive cycle synthesis algorithm, explaining state discretization, transition matrices, Frobenius representative distance, stochastic selection, and comparing WLTP vs. generic clustering assignment. |
| [TODOS.md](file:///d:/_sandbox/research/eco_drive_cycles/TODOS.md) | Prioritised backlog |
| [DATA.md](file:///d:/_sandbox/research/eco_drive_cycles/DATA.md) | Data collection notes and Google Drive link |
