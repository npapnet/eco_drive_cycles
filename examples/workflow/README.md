# Workflow Examples

Complete four-step pipeline from raw OBD data to clustered microtrip segments.
Run every script from the **repository root** with:

```bash
uv run python examples/workflow/<script>.py
```

---

## Shared Configuration — `config.json`

All scripts read a single `config.json` file located in this folder.
Edit it once to change input data, output paths, or algorithm parameters for
the entire pipeline — no need to touch individual scripts.

```json
{
  "data_dir": "raw_data/2019-opsimoulis",
  "output_dir": "data",
  "force_reingest": false,
  "processing": {
    "window": 4,
    "stop_threshold_kmh": 2.0
  },
  "segmentation": {
    "stop_threshold_kmh": 2.0,
    "stop_min_duration_s": 1.0,
    "microtrip_min_duration_s": 15.0,
    "microtrip_min_distance_m": 50.0
  },
  "clustering": {
    "n_clusters": 4
  }
}
```

| Key | Description |
|---|---|
| `data_dir` | Source folder for raw OBD exports (relative to repo root) |
| `output_dir` | Root output folder (relative to repo root) |
| `force_reingest` | Overwrite existing Parquets in step 01 |
| `processing` | Smoothing window and stop-detection threshold |
| `segmentation` | Microtrip boundary thresholds |
| `clustering.n_clusters` | K for KMeans — adjust after inspecting the elbow plot |

---

## Output Folder Layout

After running the full pipeline, `data/` (or whatever `output_dir` is set to)
will contain:

```
data/
├── trips/                        ← step 01: one archive Parquet per trip
│   └── <parquet_name>.parquet
├── metrics.duckdb                ← step 02: per-trip metrics
├── analyses/
│   └── dcca-<YYYYMMDD-HHMM>/    ← step 02: one folder per analysis run
│       ├── similarity_scores.csv
│       └── report.md
├── microtrips/                   ← step 03: per-microtrip Parquets + summary
│   ├── <trip>_mt<NN>.parquet
│   └── summary.csv
└── figs/                         ← step 04: clustering plots and report
    ├── microtrip_clusters_pairplot.png
    └── microtrip_clusters_report.md
```

---

## Scripts

### `01_ingest.py` — Raw → Archive Parquets

Reads every `.xlsx` / `.xls` / `.csv` from `data_dir` and writes one v2
archive Parquet per trip to `output_dir/trips/`.  Existing files are skipped
by default; set `"force_reingest": true` in `config.json` to overwrite.

```bash
uv run python examples/workflow/01_ingest.py
```

Equivalent CLI: `uv run dcc ingest <data_dir> <output_dir>`

---

### `02_extract_analyze.py` — Metrics + Similarity Report

Reads archive Parquets from `output_dir/trips/`, computes per-trip metrics
into `output_dir/metrics.duckdb`, then runs 7-metric similarity scoring and
writes:

- `output_dir/analyses/dcca-<timestamp>/similarity_scores.csv`
- `output_dir/analyses/dcca-<timestamp>/report.md`

```bash
uv run python examples/workflow/02_extract_analyze.py
```

Equivalent CLI: `uv run dcc extract <output_dir>` then `uv run dcc analyze <output_dir>`

---

### `03_build_microtrips.py` — Microtrip Segmentation

Segments every trip into stop-to-stop motion segments and writes:

- `output_dir/microtrips/<trip>_mt<NN>.parquet` — samples for each microtrip
  (motion phase + trailing stop, distinguished by `stop_phase` column)
- `output_dir/microtrips/summary.csv` — one row per microtrip with key stats

```bash
uv run python examples/workflow/03_build_microtrips.py
```

---

### `04_microtrip_clustering.py` — KMeans Clustering

Loads `output_dir/microtrips/summary.csv`, auto-detects numeric feature
columns (everything not in `META_COLS`), runs the elbow method, fits KMeans,
and writes:

- `output_dir/figs/microtrip_clusters_pairplot.png`
- `output_dir/figs/microtrip_clusters_report.md`

```bash
uv run python examples/workflow/04_microtrip_clustering.py
```

Inspect the elbow plot to pick the right `n_clusters`, then update
`config.json` and re-run.
