# Cluster-based Drive Cycle Synthesis

This workflow synthesizes a representative drive cycle by grouping microtrips using data-driven KMeans clusters instead of fixed WLTP speed-phase boundaries.

## How it differs from the WLTP workflow

| Aspect | WLTP (`examples/workflow/synthesis-wltp/`) | Cluster (`examples/workflow/synthesis-cluster/`) |
|---|---|---|
| Phase/cluster assignment | Fixed speed boundaries (GTR 15 §2) | KMeans clusters from step 040 |
| Number of groups | 4 (Low / Med / High / xHigh) | `n_clusters` in `config.json` |
| Group ordering | Low → xHigh (speed-based) | Sorted by cluster ID |
| Min distance per group | Per-phase dict in `config_wltp.json` | Single scalar `cluster_min_distance_m` |
| Output directory | `data/synthesis/` | `data/synthesis-cluster/` |
| Config file | `config_wltp.json` | `config_syn_cluster.json` |

## Prerequisites

Run the main workflow steps first:

```bash
uv run python examples/workflow/010_ingest.py
uv run python examples/workflow/020_extract_analyze.py
uv run python examples/workflow/030_build_microtrips.py
uv run python examples/workflow/040_microtrip_clustering.py   # recommended
```

Step 040 writes `data/microtrips/summary_clustered.csv` with a `cluster_id` column. Any clustering algorithm (KMeans, DBSCAN, hierarchical, …) can be used as long as it produces that file and column.

## Running the full pipeline

Run the entire cluster-based synthesis pipeline in sequence using the orchestrator:

```bash
uv run python examples/workflow/synthesis-cluster/200_synthesis_cluster.py
```

## Running Individual Steps

Or run individual steps for partial re-runs:

| Script | Description |
|---|---|
| `210_cluster_assignment.py` | Load `summary_clustered.csv`; add `total_duration_s`, `idle_fraction` |
| `220_cluster_markov_chain.py` | Build global Markov matrix + per-microtrip Frobenius distance |
| `230_cluster_targets.py` | Compute duration-weighted kinematic targets τ_c per cluster |
| `240_cluster_selection.py` | Stochastic Markov-guided microtrip selection per cluster |
| `250_cluster_assembly.py` | Concatenate traces, smooth junctions, validate, plot |

## Configuration

The scripts in this folder read configuration parameters from the parent directory:

1. **`../config.json`** — General output folder, segmentation, and clustering settings.
2. **`../config_syn_cluster.json`** — Cluster synthesis-specific settings (weights, random seeds, target tolerances, and bin widths).

## Outputs (`data/synthesis-cluster/`)

```
data/synthesis-cluster/
├── microtrips_clustered.csv      — Microtrip pool with cluster_id column
├── markov/
│   ├── global_matrix.csv         — Global Markov transition matrix T
│   └── microtrip_distances.csv   — Per-microtrip Frobenius distance from T
├── cluster_targets.csv           — τ_c targets and tolerance bounds per cluster
├── selected/
│   └── cluster_<id>_sequence.csv — Selected microtrip sequence per cluster
├── selection_report.csv          — F_c, convergence flag, achieved metrics per cluster
├── final_cycle.csv               — Assembled 1-Hz cycle (t_s, speed_kmh, cluster_id)
├── final_cycle.png               — Speed–time plot with cluster bands
└── validation_report.md          — Pass/fail table per metric per cluster
```
