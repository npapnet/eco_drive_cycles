# Workflow Examples

Complete four-step pipeline from raw OBD data to clustered microtrip segments, plus downstream representative drive cycle synthesis.

Run every script from the **repository root** with:

```bash
uv run python examples/workflow/<script>.py
```

---

## Configuration Files

All parameters for the pipeline and synthesis steps are located in the `examples/workflow/` directory.

1. **`config.json`** — Shared configuration for all core pipeline scripts (`010`–`040`) and downstream synthesis.
2. **`config_wltp.json`** — WLTP-specific synthesis parameters (used by scripts in `synthesis-wltp/`).
3. **`config_syn_cluster.json`** — Cluster-specific synthesis parameters (used by scripts in `synthesis-cluster/`).

### Shared Config — `config.json`

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
| `force_reingest` | Overwrite existing Parquets in step 010 |
| `processing` | Smoothing window and stop-detection threshold |
| `segmentation` | Microtrip boundary thresholds |
| `clustering.n_clusters` | K for KMeans — adjust after inspecting the elbow plot |

---

## Output Folder Layout

After running the full pipeline, `data/` (or whatever `output_dir` is set to) will contain:

```
data/
├── trips/                        ← step 010: one archive Parquet per trip
│   └── <parquet_name>.parquet
├── metrics.duckdb                ← step 020: per-trip metrics
├── analyses/
│   └── dcca-<YYYYMMDD-HHMM>/    ← step 020: one folder per analysis run
│       ├── similarity_scores.csv
│       └── report.md
├── microtrips/                   ← step 030: per-microtrip Parquets + summary
│   ├── <trip>_mt<NN>.parquet
│   └── summary.csv
└── reports/                      ← step 040-062: clustering plots and reports
    ├── figs-clustering/
    ├── figs-visualisation/
    ├── figs-comparison/
    ├── figs-representatives/
    ├── microtrip_clusters_report.md
    └── ...
```

---

## Core Scripts

### `010_ingest.py` — Raw → Archive Parquets

Reads every `.xlsx` / `.xls` / `.csv` from `data_dir` and writes one v2 archive Parquet per trip to `output_dir/trips/`. Existing files are skipped by default; set `"force_reingest": true` in `config.json` to overwrite.

```bash
uv run python examples/workflow/010_ingest.py
```

*Equivalent CLI:* `uv run dcc ingest <data_dir> <output_dir>`

---

### `020_extract_analyze.py` — Metrics + Similarity Report

Reads archive Parquets from `output_dir/trips/`, computes per-trip metrics into `output_dir/metrics.duckdb`, then runs 7-metric similarity scoring and writes:

- `output_dir/analyses/dcca-<timestamp>/similarity_scores.csv`
- `output_dir/analyses/dcca-<timestamp>/report.md`

```bash
uv run python examples/workflow/020_extract_analyze.py
```

*Equivalent CLI:* `uv run dcc extract <output_dir>` then `uv run dcc analyze <output_dir>`

---

### `030_build_microtrips.py` — Microtrip Segmentation

Segments every trip into stop-to-stop motion segments and writes:

- `output_dir/microtrips/<trip>_mt<NN>.parquet` — samples for each microtrip (motion phase + trailing stop)
- `output_dir/microtrips/summary.csv` — one row per microtrip with key stats

```bash
uv run python examples/workflow/030_build_microtrips.py
```

---

### `040_microtrip_clustering.py` — KMeans Clustering

Loads `output_dir/microtrips/summary.csv`, auto-detects numeric feature columns (everything not in `META_COLS`), runs the elbow method, fits KMeans, and writes:

- `output_dir/figs/microtrip_clusters_pairplot.png`
- `output_dir/figs/microtrip_clusters_report.md`

```bash
uv run python examples/workflow/040_microtrip_clustering.py
```

---

## Downstream Synthesis Pipelines

We provide two distinct approaches for synthesis:

1. **[WLTP-based Synthesis (GTR 15)](synthesis-wltp/README.md)** — Located in `examples/workflow/synthesis-wltp/`. Group microtrips into fixed speed-based phases (Low, Medium, High, Extra High) according to GTR 15 standards.
2. **[Cluster-based Synthesis](synthesis-cluster/README.md)** — Located in `examples/workflow/synthesis-cluster/`. Group microtrips using data-driven KMeans cluster groups.
