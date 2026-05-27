# Core Pipeline (010 – 040)

The four core scripts take raw OBD exports through ingestion, metric extraction,
microtrip segmentation, and clustering.

---

## 010 — Ingest

**Script:** `examples/workflow/010_ingest.py`
**CLI equivalent:** `uv run dcc ingest <data_dir> <output_dir>`

Reads every `.xlsx` / `.xls` / `.csv` from `config["data_dir"]` and writes one v2
archive Parquet per trip to `output_dir/trips/`. Existing files are skipped by default;
set `"force_reingest": true` to overwrite.

Each Parquet embeds a `ParquetMetadata` block with user-supplied metadata (vehicle,
driver), ingest provenance, and GPS-derived statistics computed from the raw signal.

```bash
uv run python examples/workflow/010_ingest.py
```

**Key package classes used:**

- {py:class}`drive_cycle_calculator.OBDFile` — reads and validates a raw OBD file
- {py:meth}`drive_cycle_calculator.OBDFile.to_parquet` — writes the v2 archive Parquet

---

## 020 — Extract & Analyze

**Script:** `examples/workflow/020_extract_analyze.py`
**CLI equivalent:** `uv run dcc extract <output_dir>` then `uv run dcc analyze <output_dir>`

Reads archive Parquets from `output_dir/trips/`, applies `ProcessingConfig` to derive
smoothed speed and acceleration columns, and writes per-trip scalar metrics to
`output_dir/metrics.duckdb` (plus CSV and XLSX copies).

Then runs pairwise 7-metric similarity scoring across all trips and writes:

- `output_dir/analyses/dcca-<timestamp>/similarity_scores.csv`
- `output_dir/analyses/dcca-<timestamp>/report.md`

```bash
uv run python examples/workflow/020_extract_analyze.py
```

**Key package classes used:**

- {py:class}`drive_cycle_calculator.TripCollection` — loads a folder of archive Parquets
- {py:meth}`drive_cycle_calculator.TripCollection.similarity_scores` — 7-metric pairwise scores
- {py:meth}`drive_cycle_calculator.TripCollection.find_representative` — identifies the most representative trip

---

## 030 — Build Microtrips

**Script:** `examples/workflow/030_build_microtrips.py`

Loads every archive Parquet, segments each trip into stop-to-stop motion segments
using `MicrotripSegmenter`, and writes:

- `output_dir/microtrips/<trip>_mt<NN>.parquet` — processed columns for each microtrip
- `output_dir/microtrips/summary.csv` — one row per microtrip with key stats

A microtrip is a motion phase that begins when speed exceeds the stop threshold and
ends at the start of the next stop (or end of trip). Each microtrip also carries the
trailing stop period as metadata.

```bash
uv run python examples/workflow/030_build_microtrips.py
```

**Segmentation parameters** (from `config["segmentation"]`):

| Parameter | Default | Description |
|---|---|---|
| `stop_threshold_kmh` | 2.0 | Speed below which the vehicle is considered stopped |
| `stop_min_duration_s` | 1.0 | Minimum stop duration to register as a boundary |
| `microtrip_min_duration_s` | 15.0 | Discard motion segments shorter than this |
| `microtrip_min_distance_m` | 50.0 | Discard motion segments shorter than this |

**Key package classes used:**

- {py:class}`drive_cycle_calculator.MicrotripSegmenter` — two-stage segmentation
- {py:class}`drive_cycle_calculator.segmentation.SegmentBoundary`

---

## 040 — KMeans Clustering

**Script:** `examples/workflow/040_microtrip_clustering.py`

Loads `output_dir/microtrips/summary.csv`, auto-detects numeric feature columns
(everything except trip ID and metadata), runs the **elbow method** to suggest an
optimal `k`, fits KMeans with `config["clustering"]["n_clusters"]`, and writes:

- Pairplot of cluster assignments
- `microtrip_clusters_report.md` — per-cluster statistics
- `summary_clustered.csv` — original summary with `cluster_id` column appended

```bash
uv run python examples/workflow/040_microtrip_clustering.py
```

Inspect the elbow plot and adjust `n_clusters` in `config.json` before proceeding to
synthesis. The cluster ID column in `summary_clustered.csv` is the input for both
downstream synthesis workflows.

---

## 050 / 051 / 060 / 062 — Visualisation & Representatives

These scripts produce diagnostic plots and rankings **within** each cluster:

| Script | Output |
|---|---|
| `050` | Per-cluster v-a density hexbin + v-t scatter cloud |
| `051` | Multi-cluster v-t overlay |
| `060` | Per-cluster representative ranking (z-score, pct deviation, cosine) |
| `062` | Faceted top-N speed profiles per cluster per similarity metric |

These are exploratory — run them to validate clustering quality before synthesis.
