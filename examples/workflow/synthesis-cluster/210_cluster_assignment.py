# %%
"""
Cluster Synthesis Step 210 — Load microtrip cluster assignments.

Reads the clustered summary produced by any clustering step
(e.g. 04_microtrip_clustering.py) that writes
data/microtrips/summary_clustered.csv with a cluster_id column.
The clustering algorithm (KMeans, DBSCAN, hierarchical, …) is
irrelevant here — only the cluster_id column matters.

Adds two derived columns used by later steps:
  - total_duration_s  = duration_s + stop_duration_s
  - idle_fraction     = stop_duration_s / total_duration_s

Output: data/synthesis-cluster/microtrips_clustered.csv

Next step: 220_cluster_markov_chain.py  (and 230_cluster_targets.py, independently)
"""

import json
from pathlib import Path

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg = json.loads((Path(__file__).parent.parent / "config.json").read_text())

OUTPUT_DIR     = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR  = OUTPUT_DIR / "synthesis-cluster"

# ── Load ───────────────────────────────────────────────────────────────────────
clustered_path = MICROTRIPS_DIR / "summary_clustered.csv"
if not clustered_path.exists():
    print(f"summary_clustered.csv not found at {clustered_path}.")
    print("Run a clustering step (e.g. 04_microtrip_clustering.py) first.")
    raise SystemExit(1)

df = pd.read_csv(clustered_path)
print(f"Loaded {len(df)} microtrips from {clustered_path}")

if "cluster_id" not in df.columns:
    print("ERROR: 'cluster_id' column missing — re-run your clustering step.")
    raise SystemExit(1)

df["cluster_id"] = df["cluster_id"].astype(str)

# ── Derived columns ────────────────────────────────────────────────────────────
df["total_duration_s"] = df["duration_s"] + df["stop_duration_s"]
df["idle_fraction"] = df["stop_duration_s"] / df["total_duration_s"].replace(0.0, float("nan"))

# ── Save ───────────────────────────────────────────────────────────────────────
SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
out_path = SYNTHESIS_DIR / "microtrips_clustered.csv"
df.to_csv(out_path, index=False)
print(f"Saved: {out_path}")

# ── Report ─────────────────────────────────────────────────────────────────────
summary = (
    df.groupby("cluster_id")
    .agg(
        count=("cluster_id", "size"),
        mean_vmax=("max_speed_kmh", "mean"),
        min_vmax=("max_speed_kmh", "min"),
        max_vmax=("max_speed_kmh", "max"),
        mean_speed=("mean_speed_kmh", "mean"),
    )
    .sort_index()
    .round(1)
)

print("\nCluster distribution:")
print(summary.to_string())

small_clusters = summary[summary["count"] < 10].index.tolist()
if small_clusters:
    print(f"\nWARNING: Small cluster pools (< 10 microtrips): {small_clusters}")
    print("  Microtrip reuse will be required in the selection step.")
# %%
