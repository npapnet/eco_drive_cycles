# Cluster-based Drive Cycle Synthesis

This workflow synthesises a representative drive cycle by grouping microtrips
using data-driven KMeans clusters instead of fixed WLTP speed-phase boundaries.

## How it differs from the WLTP workflow

| Aspect | WLTP (`examples/workflow/`) | Cluster (`examples/workflow-syn-cluster/`) |
|---|---|---|
| Phase/cluster assignment | Fixed speed boundaries (GTR 15 §2) | KMeans clusters from step 04 |
| Number of groups | 4 (Low / Med / High / xHigh) | `n_clusters` in `config.json` |
| Group ordering | Low → xHigh (speed-based) | Sorted by cluster ID |
| Min distance per group | Per-phase dict in `config_wltp.json` | Single scalar `cluster_min_distance_m` |
| Output directory | `data/synthesis/` | `data/synthesis-cluster/` |
| Config file | `config_wltp.json` | `config_syn_cluster.json` |

## Prerequisites

Run the main workflow steps first:

```
uv run python examples/workflow/01_ingest.py
uv run python examples/workflow/02_extract_analyze.py
uv run python examples/workflow/03_build_microtrips.py
uv run python examples/workflow/04_microtrip_clustering.py   # recommended
```

Step 04 writes `data/microtrips/summary_clustered.csv` with a `cluster_id`
column.  Any clustering algorithm (KMeans, DBSCAN, hierarchical, …) can be
used as long as it produces that file and column — step 210 is agnostic to
how the clusters were produced.

## Running the full pipeline

```bash
uv run python examples/workflow-syn-cluster/200_synthesis_cluster.py
```

Or run individual steps for partial re-runs:

```bash
uv run python examples/workflow-syn-cluster/240_cluster_selection.py
uv run python examples/workflow-syn-cluster/250_cluster_assembly.py
```

## Pipeline steps

| Script | Description |
|---|---|
| `200_synthesis_cluster.py` | Orchestrator — runs 210–250 in order |
| `210_cluster_assignment.py` | Load `summary_clustered.csv`; add `total_duration_s`, `idle_fraction` |
| `220_cluster_markov_chain.py` | Build global Markov matrix + per-microtrip Frobenius distance |
| `230_cluster_targets.py` | Compute duration-weighted kinematic targets τ_c per cluster |
| `240_cluster_selection.py` | Stochastic Markov-guided microtrip selection per cluster |
| `250_cluster_assembly.py` | Concatenate traces, smooth junctions, validate, plot |

## Configuration

`config.json` — shared with the main workflow (microtrip segmentation, clustering k).

`config_syn_cluster.json` — synthesis-specific parameters:

| Key | Default | Description |
|---|---|---|
| `speed_bin_width_kmh` | 10 | State-space speed bin width (Markov) |
| `acc_bin_width_ms2` | 0.2 | State-space acceleration bin width |
| `acc_range_ms2` | 1.5 | Acceleration range ±value (values outside clamped) |
| `markov_lambda` | 1.0 | Markov weight decay λ in exp(−λD) |
| `n_trials` | 1000 | Random assemblies per cluster |
| `f_threshold` | 0.01 | Early-exit objective threshold |
| `max_reuse_fraction` | 0.30 | Max fraction of total duration a single microtrip may occupy |
| `inter_cluster_idle_s` | 20 | Idle seconds inserted between cluster segments |
| `cluster_min_distance_m` | 600 | Minimum assembled distance per cluster |
| `random_seed` | 42 | RNG seed for reproducibility |
| `metric_weights` | see file | Per-metric weights in the objective function F_c |

## Outputs (`data/synthesis-cluster/`)

```
microtrips_clustered.csv          — microtrip pool with cluster_id column
markov/
  global_matrix.csv               — global Markov transition matrix T
  microtrip_distances.csv         — per-microtrip Frobenius distance from T
cluster_targets.csv               — τ_c targets and tolerance bounds per cluster
selected/
  cluster_<id>_sequence.csv       — selected microtrip sequence per cluster
selection_report.csv              — F_c, convergence flag, achieved metrics per cluster
final_cycle.csv                   — assembled 1-Hz cycle (t_s, speed_kmh, cluster_id)
final_cycle.png                   — speed–time plot with cluster bands
validation_report.md              — pass/fail table per metric per cluster
```
