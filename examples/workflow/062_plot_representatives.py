# %%
"""
Step 6.2 — Plot the top N representative microtrips per cluster, one figure per similarity metric.

Reads ranked_microtrips.csv (produced by 060_select_representatives.py) and plots
the top N microtrips per cluster for every rank_* column found in the file.
One PNG is saved per metric.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# ── Script Configuration ───────────────────────────────────────────────────────
N_TOP = 5  # Number of top microtrips to plot per cluster

SHARE_X = True
SHARE_Y = True
# ───────────────────────────────────────────────────────────────────────────────

# ── Load shared config ─────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())
OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

REPORTS_DIR = OUTPUT_DIR / "reports/"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)

FIGS_DIR = REPORTS_DIR / "figs-representatives"
FIGS_DIR.mkdir(exist_ok=True, parents=True)
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips/"

# ── Load data ──────────────────────────────────────────────────────────────────
ranked_path = MICROTRIPS_DIR / "ranked_microtrips.csv"
if not ranked_path.exists():
    print(f"Error: Could not find {ranked_path}")
    print("Please run 060_select_representatives.py first.")
    raise SystemExit(1)

df = pd.read_csv(ranked_path)
df["cluster_id"] = df["cluster_id"].astype(str)

rank_cols = [c for c in df.columns if c.startswith("rank_")]
if not rank_cols:
    print("Error: No rank_* columns found in ranked_microtrips.csv.")
    raise SystemExit(1)

n_clusters = df["cluster_id"].nunique()
if n_clusters > 9:
    raise ValueError(
        f"Too many clusters ({n_clusters}) for facet grid visualization. Maximum is 9."
    )

# ── Parquet cache — avoid re-reading the same file for each metric ─────────────
_parquet_cache: dict[str, pd.DataFrame] = {}


def _load_microtrip(filename: str) -> pd.DataFrame | None:
    if filename not in _parquet_cache:
        parquet_path = MICROTRIPS_DIR / filename
        if not parquet_path.exists():
            print(f"  Warning: {filename} not found, skipping.")
            return None
        _parquet_cache[filename] = pd.read_parquet(parquet_path)
    return _parquet_cache[filename]


# ── Plot one figure per metric ─────────────────────────────────────────────────
print(f"Plotting top {N_TOP} microtrips per cluster for {len(rank_cols)} metric(s)...")

for rank_col in rank_cols:
    measure_name = rank_col[len("rank_"):]
    top_df = df[df[rank_col] <= N_TOP]

    plot_data = []
    for _, row in top_df.iterrows():
        mt_df = _load_microtrip(row["filename"])
        if mt_df is None:
            continue

        speed_col = "smooth_speed_kmh" if "smooth_speed_kmh" in mt_df.columns else "speed_kmh"

        if "stop_phase" in mt_df.columns:
            mt_df = mt_df[mt_df["stop_phase"] == False]

        t0 = mt_df["elapsed_s"].iloc[0] if not mt_df.empty and "elapsed_s" in mt_df.columns else 0.0
        mt_id = f"{row['trip_id']}_mt{row['microtrip_index']}"

        for _, sample in mt_df.iterrows():
            plot_data.append(
                {
                    "cluster_id": row["cluster_id"],
                    "elapsed_s": sample.get("elapsed_s", t0) - t0,
                    "speed_kmh": sample.get(speed_col, 0),
                    "label": f"Rank {row[rank_col]}: {mt_id}",
                }
            )

    if not plot_data:
        print(f"  No data for '{measure_name}', skipping.")
        continue

    plot_df = pd.DataFrame(plot_data)

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
    g.figure.suptitle(f"Top {N_TOP} microtrips — {measure_name}", y=1.02)

    for ax in g.axes.flat:
        ax.legend(title="Microtrips", fontsize="small", title_fontsize="small", loc="upper right")

    plot_path = FIGS_DIR / f"representative_microtrips_{measure_name}.png"
    g.savefig(plot_path, dpi=300, bbox_inches="tight")
    print(f"  Saved: {plot_path}")
    plt.close(g.figure)

print("Done.")
# %%
