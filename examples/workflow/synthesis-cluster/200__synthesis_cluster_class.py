# %%
"""
Cluster-based Drive Cycle Synthesis.

Loads the persisted microtrip collection with cluster assignments from
040_microtrip_clustering.py, then synthesises a representative 1-Hz
speed-time cycle via the package's Markov-guided stochastic selection +
assembly pipeline.

Prerequisites:
  Run 010_ingest.py → 030_build_microtrips.py → 040_microtrip_clustering.py first.
  Parameters are in config.json (shared) and config_syn_cluster.json.

Outputs:
  OUTPUT_DIR/synthesis-cluster/final_cycle.csv  — t_s, speed_kmh, group (1-Hz)
  OUTPUT_DIR/synthesis-cluster/final_cycle.png  — speed-time plot with cluster bands
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt

from drive_cycle_calculator.microtrip_collection import MicrotripCollection
from drive_cycle_calculator.schema import ClusterSynthesisConfig
from drive_cycle_calculator.synthesis import synthesize
from drive_cycle_calculator.synthesis.cluster import assign_clusters

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg = json.loads((Path(__file__).parent.parent / "config.json").read_text())
_syn = json.loads((Path(__file__).parent.parent / "config_syn_cluster.json").read_text())

OUTPUT_DIR     = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR  = OUTPUT_DIR / "synthesis-cluster"
SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)

config = ClusterSynthesisConfig.model_validate(_syn)

# ── Load microtrips + cluster assignments ──────────────────────────────────────
clustered_csv = MICROTRIPS_DIR / "summary_clustered.csv"
if not clustered_csv.exists():
    print(f"summary_clustered.csv not found at {clustered_csv}.")
    print("Run 040_microtrip_clustering.py first.")
    raise SystemExit(1)

mc = MicrotripCollection.from_parquets(MICROTRIPS_DIR, summary_csv=clustered_csv)
print(f"Loaded {len(mc)} microtrips.")

assignments = assign_clusters(mc.summary)
cluster_order = sorted(assignments.unique(), key=str)
print(f"Clusters: {cluster_order}")
small = [c for c in cluster_order if (assignments == c).sum() < 10]
if small:
    print(f"  WARNING: small cluster pools (< 10): {small} — reuse will occur during selection.")

# ── Synthesize ────────────────────────────────────────────────────────────────
print("Running synthesis …")
cycle = synthesize(mc, assignments, config)
print(f"Cycle: {len(cycle)} s = {len(cycle) / 60:.1f} min")

# ── Save CSV ──────────────────────────────────────────────────────────────────
csv_path = SYNTHESIS_DIR / "final_cycle.csv"
cycle.to_csv(csv_path, index=False)
print(f"Saved: {csv_path}")

# ── Plot ───────────────────────────────────────────────────────────────────────
_cmap = plt.get_cmap("tab10")
cluster_colours = {c: _cmap(i) for i, c in enumerate(cluster_order)}

fig, ax = plt.subplots(figsize=(14, 4))
v_max = cycle["speed_kmh"].max()

for cluster in cluster_order:
    grp_df = cycle[cycle["group"] == cluster]
    if grp_df.empty:
        continue
    colour = cluster_colours[cluster]
    start, end = int(grp_df["t_s"].min()), int(grp_df["t_s"].max()) + 1
    ax.axvspan(start, end, alpha=0.12, color=colour, lw=0)
    ax.text(
        (start + end) / 2, v_max * 0.92, f"C{cluster}",
        ha="center", va="bottom", fontsize=8, color=colour, fontweight="bold",
    )

ax.plot(cycle["t_s"], cycle["speed_kmh"], lw=0.8, color="#222")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Speed (km/h)")
ax.set_title("Synthesised Drive Cycle — Cluster-based")
ax.set_xlim(0, cycle["t_s"].max())
ax.set_ylim(0)
plt.tight_layout()

png_path = SYNTHESIS_DIR / "final_cycle.png"
fig.savefig(png_path, dpi=150)
print(f"Saved: {png_path}")
plt.show()
# %%
