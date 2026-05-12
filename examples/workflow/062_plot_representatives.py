# %%
"""
Step 6.2 — Plot the top N representative microtrips per cluster.

Reads ranked_microtrips.csv (produced by 060_select_representatives.py) and plots
the top N microtrips per cluster ranked by PRIMARY_MEASURE.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# ── Script Configuration ───────────────────────────────────────────────────────
N_TOP = 5  # Number of top microtrips to plot per cluster

# Must match one of the measure names used in 060_select_representatives.py.
# Defaults to "z_score" (the first measure in that script's MEASURES_MAP).
PRIMARY_MEASURE = "z_score"

SHARE_X = True
SHARE_Y = True
# ───────────────────────────────────────────────────────────────────────────────

# ── Load shared config ─────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())
OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

REPORTS_DIR = OUTPUT_DIR / "reports/"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips/"

# ── Load data ──────────────────────────────────────────────────────────────────
ranked_path = MICROTRIPS_DIR / "ranked_microtrips.csv"
if not ranked_path.exists():
    print(f"Error: Could not find {ranked_path}")
    print("Please run 060_select_representatives.py first.")
    raise SystemExit(1)

df = pd.read_csv(ranked_path)
df["cluster_id"] = df["cluster_id"].astype(str)

rank_col = f"rank_{PRIMARY_MEASURE}"
if rank_col not in df.columns:
    available = [c for c in df.columns if c.startswith("rank_")]
    print(f"Error: '{rank_col}' not found. Available rank columns: {available}")
    raise SystemExit(1)

n_clusters = df["cluster_id"].nunique()
if n_clusters > 9:
    raise ValueError(
        f"Too many clusters ({n_clusters}) for facet grid visualization. Maximum is 9."
    )

# ── Load timeseries for top N microtrips ──────────────────────────────────────
top_df = df[df[rank_col] <= N_TOP]
print(f"Plotting top {N_TOP} microtrips per cluster (measure: {PRIMARY_MEASURE})...")

plot_data = []

for _, row in top_df.iterrows():
    cluster = row["cluster_id"]
    rank = row[rank_col]
    mt_id = f"{row['trip_id']}_mt{row['microtrip_index']}"
    filename = row["filename"]

    parquet_path = MICROTRIPS_DIR / filename
    if not parquet_path.exists():
        print(f"  Warning: Parquet {filename} not found, skipping...")
        continue

    mt_df = pd.read_parquet(parquet_path)

    speed_col = "smooth_speed_kmh" if "smooth_speed_kmh" in mt_df.columns else "speed_kmh"

    if "stop_phase" in mt_df.columns:
        mt_df = mt_df[mt_df["stop_phase"] == False]

    t0 = mt_df["elapsed_s"].iloc[0] if not mt_df.empty and "elapsed_s" in mt_df.columns else 0.0

    for _, sample in mt_df.iterrows():
        plot_data.append(
            {
                "cluster_id": cluster,
                "elapsed_s": sample.get("elapsed_s", t0) - t0,
                "speed_kmh": sample.get(speed_col, 0),
                "label": f"Rank {rank}: {mt_id}",
            }
        )

plot_df = pd.DataFrame(plot_data)

if plot_df.empty:
    print("No data available for plotting.")
    raise SystemExit(1)

# ── Facet grid ────────────────────────────────────────────────────────────────
g = sns.FacetGrid(
    plot_df,
    col="cluster_id",
    col_wrap=min(3, n_clusters),
    sharex=SHARE_X,
    sharey=SHARE_Y,
    height=4,
    aspect=1.5,
)

g.map_dataframe(
    sns.lineplot,
    x="elapsed_s",
    y="speed_kmh",
    hue="label",
    palette="tab10",
    linewidth=1.5,
    alpha=0.8,
)

g.set_axis_labels("Elapsed Time (s)", "Speed (km/h)")
g.set_titles(col_template="Cluster {col_name}")

for ax in g.axes.flat:
    ax.legend(title="Microtrips", fontsize="small", title_fontsize="small", loc="upper right")

plt.tight_layout()
plot_path = REPORTS_DIR / "representative_microtrips_plot.png"
g.savefig(plot_path, dpi=300)
print(f"Plot saved to {plot_path}")
plt.show()
# %%
