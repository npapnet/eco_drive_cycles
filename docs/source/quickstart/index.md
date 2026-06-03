# Quick Start

The `examples/workflow/` directory contains a numbered sequence of scripts that
implement the full pipeline end-to-end. They are the reference implementation — the
`dcc` CLI commands cover the ingestion and metrics steps, while the downstream
segmentation, clustering, and synthesis steps currently live only in the workflow
scripts.

Run every script from the **repository root**:

```bash
uv run python examples/workflow/<script>.py
```

---

## Configuration

All parameters are controlled by JSON files in `examples/workflow/`:

| File | Used by |
|---|---|
| `config.json` | Core pipeline scripts `010`–`040` and synthesis orchestrators |
| `config_wltp.json` | WLTP synthesis (`synthesis-wltp/`) |
| `config_syn_cluster.json` | Cluster synthesis (`synthesis-cluster/`) |

Minimal `config.json`:

```json
{
  "data_dir": "raw_data/2019-opsimoulis",
  "output_dir": "data",
  "force_reingest": false,
  "processing": { "window": 4, "stop_threshold_kmh": 2.0 },
  "segmentation": {
    "stop_threshold_kmh": 2.0,
    "stop_min_duration_s": 1.0,
    "microtrip_min_duration_s": 15.0,
    "microtrip_min_distance_m": 50.0
  },
  "clustering": { "n_clusters": 4 }
}
```

---

## Pipeline Steps

```{mermaid}
flowchart TD
    s010["010 — Ingest\nRaw OBD → Archive Parquets"]
    s020["020 — Extract & Analyze\nMetrics + Similarity Report"]
    s030["030 — Build Microtrips\nSegmentation"]
    s040["040 — Clustering\nKMeans on microtrip features"]
    s050["050/051 — Visualisation\nDensity clouds, v-t overlays"]
    s060["060/062 — Representatives\nRank & plot representative microtrips"]
    wltp["WLTP Synthesis\n(100–150)"]
    clu["Cluster Synthesis\n(200–250)"]

    s010 --> s020
    s010 --> s030
    s030 --> s040
    s040 --> s050
    s040 --> s060
    s030 --> wltp
    s040 --> clu
```

---

## Contents

```{toctree}
:maxdepth: 1

core-pipeline
synthesis-wltp
synthesis-cluster
```

---

## Output Folder Layout

After running the full pipeline, `output_dir` (`data/` by default) looks like:

```
data/
├── trips/                         ← 010: one archive Parquet per trip
├── metrics.duckdb                 ← 020: per-trip metrics
├── analyses/
│   └── dcca-<YYYYMMDD-HHMM>/     ← 020: similarity scores + report.md
├── microtrips/                    ← 030: per-microtrip Parquets + summary.csv
├── reports/
│   ├── figs-clustering/           ← 040
│   ├── figs-visualisation/        ← 050
│   ├── figs-comparison/           ← 051
│   └── figs-representatives/      ← 062
├── synthesis/                     ← WLTP synthesis outputs
└── synthesis-cluster/             ← Cluster synthesis outputs
```
