# Cluster-based Synthesis

Located in `examples/workflow/synthesis-cluster/`. Groups microtrips using the
data-driven KMeans cluster IDs produced by step `040`, then applies the same
Markov-guided stochastic assembly as the WLTP workflow — without imposing fixed
speed-phase boundaries.

**Prerequisites:** run steps `010`, `020`, `030`, `040` first.

---

## How It Differs from WLTP

| Aspect | WLTP (`synthesis-wltp/`) | Cluster (`synthesis-cluster/`) |
|---|---|---|
| Phase/cluster assignment | Fixed speed boundaries (GTR 15 §2) | KMeans from step `040` |
| Number of groups | 4 (Low / Med / High / xHigh) | `n_clusters` in `config.json` |
| Group ordering | Low → xHigh (speed-based) | Sorted by cluster ID |
| Min distance per group | Per-phase dict in `config_wltp.json` | Single scalar `cluster_min_distance_m` |
| Output directory | `data/synthesis/` | `data/synthesis-cluster/` |
| Config file | `config_wltp.json` | `config_syn_cluster.json` |

---

## Run the Full Pipeline

```bash
uv run python examples/workflow/synthesis-cluster/200_synthesis_cluster.py
```

---

## Step-by-Step

```{mermaid}
flowchart LR
    s210["210\nCluster Assignment\nLoad summary_clustered.csv"] --> s220
    s220["220\nMarkov Chain\nGlobal matrix T"] --> s230
    s230["230\nCluster Targets\nτ_c per cluster"] --> s240
    s240["240\nStochastic Selection\nMarkov-guided per cluster"] --> s250
    s250["250\nAssembly & Validation\n1 Hz final_cycle.csv"]
```

### 210 — Cluster Assignment

Loads `data/microtrips/summary_clustered.csv` (written by step `040`), adds derived
columns `total_duration_s` and `idle_fraction`.

Any clustering algorithm that produces a `cluster_id` column in `summary_clustered.csv`
is compatible — KMeans is the default but DBSCAN or hierarchical clustering work too.

### 220 — Markov Chain

Same method as step `120`: builds global transition matrix **T** from the observed
microtrip sequence and computes per-microtrip Frobenius distances.

Writes to `data/synthesis-cluster/markov/`.

### 230 — Cluster Targets

Computes duration-weighted kinematic targets τ_c per cluster from the full microtrip
pool within each cluster. Writes `data/synthesis-cluster/cluster_targets.csv` with
target values and tolerance bounds.

### 240 — Stochastic Selection

Same Markov-guided selection as step `140`, but operating per-cluster rather than
per-phase. Writes:

- `data/synthesis-cluster/selected/cluster_<id>_sequence.csv`
- `data/synthesis-cluster/selection_report.csv`

### 250 — Assembly & Validation

Concatenates clusters in order, smooths junctions, and validates. Writes:

- `data/synthesis-cluster/final_cycle.csv` — `t_s`, `speed_kmh`, `cluster_id`
- `data/synthesis-cluster/final_cycle.png` — speed–time plot with cluster colour bands
- `data/synthesis-cluster/validation_report.md` — Pass/Fail per metric per cluster

---

## Configuration (`config_syn_cluster.json`)

Key parameters:

| Key | Description |
|---|---|
| `weights` | Objective weight per kinematic metric |
| `random_seed` | Reproducibility seed |
| `target_tolerances` | Acceptable deviation (%) per metric |
| `cluster_min_distance_m` | Minimum cumulative distance per cluster |
