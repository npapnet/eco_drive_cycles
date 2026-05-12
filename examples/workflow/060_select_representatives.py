# %%
"""
Step 6 — Select representative microtrips per cluster.

This script ranks microtrips within their respective clusters based on their similarity
to the cluster's "fleet" average. It exports an augmented summary CSV containing the
similarity scores and ranks, and generates a facet grid plot visualizing the top N
microtrips for each cluster.

Configuration (top N and similarity measure) is defined at the top of the script.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from drive_cycle_calculator.similarity.measures import (
    cosine_similarity,
    pct_deviation,
    z_score_distance,
)

# ── Script Configuration ───────────────────────────────────────────────────────
N_TOP = 5  # Number of top microtrips to plot per cluster

# FacetGrid sharing configuration
SHARE_X = True
SHARE_Y = True

# Available similarity methods.
# To change the method used for ranking, update ACTIVE_MEASURE to one of the keys.
MEASURES_MAP = {
    "z_score": z_score_distance,
    "pct_deviation": pct_deviation,
    "cosine": cosine_similarity,
}
ACTIVE_MEASURE = "z_score"  # Change this string to switch methods
# ───────────────────────────────────────────────────────────────────────────────

# ── Load shared config ─────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())
OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

REPORTS_DIR = OUTPUT_DIR / "reports/"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips/"

# Identifier columns to exclude from similarity calculation (must match clustering)
META_COLS = frozenset(
    {
        "trip_id",
        "parquet_id",
        "microtrip_index",
        "filename",
        "motion_samples",
        "stop_samples",
        "cluster",
    }
)

# ── Load data ──────────────────────────────────────────────────────────────────
summary_clustered_path = MICROTRIPS_DIR / "summary_clustered.csv"
if not summary_clustered_path.exists():
    print(f"Error: Could not find {summary_clustered_path}")
    print("Please run 04_microtrip_clustering.py first.")
    raise SystemExit(1)

df = pd.read_csv(summary_clustered_path)

# Ensure cluster column exists and is a string
if "cluster" not in df.columns:
    print("Error: 'cluster' column not found in summary. Did you run step 04?")
    raise SystemExit(1)

df["cluster"] = df["cluster"].astype(str)

unique_clusters = df["cluster"].unique()
n_clusters = len(unique_clusters)
print(f"Found {n_clusters} clusters.")

if n_clusters > 9:
    raise ValueError(
        f"Too many clusters ({n_clusters}) for facet grid visualization. Maximum is 9."
    )

features = [c for c in df.columns if c not in META_COLS]
print(f"Using {len(features)} features for similarity: {features}")

# ── Calculate Similarity & Rank ────────────────────────────────────────────────
similarity_fn = MEASURES_MAP[ACTIVE_MEASURE]
print(f"\nCalculating similarity using method: {ACTIVE_MEASURE}")

# We will calculate similarity per cluster
df["similarity_score"] = 0.0

for cluster_id in unique_clusters:
    # Get mask for current cluster
    mask = df["cluster"] == cluster_id
    cluster_df = df[mask]

    # Feature matrix for the cluster (fleet)
    fleet_matrix = cluster_df[features].to_numpy()

    # Calculate similarity for each microtrip in the cluster
    scores = []
    for row_idx in range(len(cluster_df)):
        trip_vector = fleet_matrix[row_idx]
        score = similarity_fn(fleet_matrix, trip_vector)
        scores.append(score)

    df.loc[mask, "similarity_score"] = scores

# Rank within cluster (descending, so highest score gets rank 1)
df["cluster_rank"] = (
    df.groupby("cluster")["similarity_score"].rank("dense", ascending=False).astype(int)
)

# ── Export Augmented Data ──────────────────────────────────────────────────────
ranked_path = MICROTRIPS_DIR / "ranked_microtrips.csv"
# Sort by cluster then rank for better readability
df_sorted = df.sort_values(["cluster", "cluster_rank"])
df_sorted.to_csv(ranked_path, index=False)
print(f"Augmented summary saved to {ranked_path}")

# ── Plotting Top N Microtrips ──────────────────────────────────────────────────
print(f"\nPlotting top {N_TOP} microtrips per cluster...")

# Filter for top N
top_df = df_sorted[df_sorted["cluster_rank"] <= N_TOP]

# Load timeseries data for the selected microtrips
plot_data = []

for _, row in top_df.iterrows():
    cluster = row["cluster"]
    rank = row["cluster_rank"]
    mt_id = f"{row['trip_id']}_mt{row['microtrip_index']}"
    filename = row["filename"]

    parquet_path = MICROTRIPS_DIR / filename
    if not parquet_path.exists():
        print(f"  Warning: Parquet {filename} not found, skipping...")
        continue

    mt_df = pd.read_parquet(parquet_path)

    # Use smooth_speed_kmh if available, else speed_kmh
    speed_col = "smooth_speed_kmh" if "smooth_speed_kmh" in mt_df.columns else "speed_kmh"

    # Keep only motion phase for plotting, or all if you prefer
    # Filtering for stop_phase == False to focus on the active driving part
    if "stop_phase" in mt_df.columns:
        mt_df = mt_df[mt_df["stop_phase"] == False]

    if not mt_df.empty and "elapsed_s" in mt_df.columns:
        t0 = mt_df["elapsed_s"].iloc[0]
    else:
        t0 = 0.0

    for _, sample in mt_df.iterrows():
        plot_data.append(
            {
                "cluster": cluster,
                "elapsed_s": sample.get("elapsed_s", t0) - t0,
                "speed_kmh": sample.get(speed_col, 0),
                "label": f"Rank {rank}: {mt_id}",
            }
        )

plot_df = pd.DataFrame(plot_data)

if plot_df.empty:
    print("No data available for plotting.")
    raise SystemExit(1)

# Facet grid
g = sns.FacetGrid(
    plot_df,
    col="cluster",
    col_wrap=min(3, n_clusters),
    sharex=SHARE_X,
    sharey=SHARE_Y,
    height=4,
    aspect=1.5,
)

# Plot each microtrip as a separate line
g.map_dataframe(
    sns.lineplot,
    x="elapsed_s",
    y="speed_kmh",
    hue="label",
    palette="tab10",
    linewidth=1.5,
    alpha=0.8,
)

# Customize
g.set_axis_labels("Elapsed Time (s)", "Speed (km/h)")
g.set_titles(col_template="Cluster {col_name}")

# Adjust legends: add legend per axis to avoid one massive global legend
for ax in g.axes.flat:
    # Add legend to the upper right
    ax.legend(title="Microtrips", fontsize="small", title_fontsize="small", loc="upper right")

plt.tight_layout()
plot_path = REPORTS_DIR / "representative_microtrips_plot.png"
g.savefig(plot_path, dpi=300)
print(f"Plot saved to {plot_path}")
plt.show()

# plt.show()
# %%
