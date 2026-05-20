# %%
"""
Step 051 — Cluster comparison: v-t scatter cloud.

Reads the clustered summary CSV produced by 040_microtrip_clustering.py and
the per-microtrip Parquet files produced by 030_build_microtrips.py.

Plots the v-t (time vs speed) scatter cloud for multiple clusters on the
same figure, using different colors for each cluster, to compare their
shapes and distributions.

Cluster selection: edit CLUSTER_IDS below.
Paths are read from config.json in the same directory.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

REPORTS_DIR = OUTPUT_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)

FIGS_DIR = REPORTS_DIR / "figs-comparison"
FIGS_DIR.mkdir(exist_ok=True, parents=True)

MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"

# ── User-adjustable settings ──────────────────────────────────────────────────

# List of cluster labels to visualise. Set to None to plot all available clusters.
# Example: CLUSTER_IDS = [0, 1]
CLUSTER_IDS: list[int] | None = None

# ── Load clustered summary ────────────────────────────────────────────────────
summary_path = MICROTRIPS_DIR / "summary_clustered.csv"
if not summary_path.exists():
    print(f"Summary not found: {summary_path}")
    print("Run 040_microtrip_clustering.py first.")
    raise SystemExit(1)

df_summary = pd.read_csv(summary_path)
available_clusters = sorted(df_summary["cluster_id"].unique())

if CLUSTER_IDS is None:
    clusters_to_plot = available_clusters
else:
    clusters_to_plot = [c for c in CLUSTER_IDS if c in available_clusters]

if not clusters_to_plot:
    print(f"No valid clusters found to plot. Available: {available_clusters}")
    raise SystemExit(1)

print(f"Plotting clusters: {clusters_to_plot}")

# ── Figure Setup ─────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
colors = plt.cm.tab10.colors

cluster_stats = []

for i, cid in enumerate(clusters_to_plot):
    cluster_df = df_summary[df_summary["cluster_id"] == cid]
    color = colors[i % len(colors)]

    frames = []
    for _, row in cluster_df.iterrows():
        p = MICROTRIPS_DIR / row["filename"]
        if not p.exists():
            continue

        part = pd.read_parquet(p, columns=["elapsed_s", "smooth_speed_kmh", "stop_phase"])
        motion = part[~part["stop_phase"]].copy()

        if motion.empty:
            continue

        motion["t_rel"] = motion["elapsed_s"] - motion["elapsed_s"].iloc[0]
        frames.append(motion)

    if not frames:
        print(f"  Cluster {cid}: No motion-phase data loaded.")
        continue

    data = pd.concat(frames, ignore_index=True)
    n_samples = len(data)
    n_microtrips = len(cluster_df)
    print(f"  Cluster {cid}: {n_microtrips} microtrips, {n_samples:,} samples")

    t_all = data["t_rel"].to_numpy()
    v_all = data["smooth_speed_kmh"].to_numpy()

    mean_speed = cluster_df["mean_speed_kmh"].mean()
    std_speed = cluster_df["mean_speed_kmh"].std()
    mean_speed_95th = cluster_df["speed_95th_kmh"].mean()
    std_speed_95th = cluster_df["speed_95th_kmh"].std()
    mean_rpa = cluster_df["rpa"].mean()
    std_rpa = cluster_df["rpa"].std()

    ax.scatter(
        t_all,
        v_all,
        s=4,
        alpha=0.15,
        linewidths=0,
        color=color,
        label=f"Cluster {cid} (n={n_microtrips})",
        rasterized=True,
    )

    cluster_stats.append(
        {
            "Cluster": cid,
            "Microtrips": n_microtrips,
            "Samples": n_samples,
            "Mean Speed (km/h)": f"{mean_speed:.1f} ± {std_speed:.1f}",
            "95th %ile Speed (km/h)": f"{mean_speed_95th:.1f} ± {std_speed_95th:.1f}",
            "RPA (m/s²)": f"{mean_rpa:.4f} ± {std_rpa:.4f}",
        }
    )

# ── Finalize Figure ─────────────────────────────────────────────────────────

ax.set_xlabel("Relative time (s)")
ax.set_ylabel("Speed (km/h)")
ax.set_title("v-t Scatter Cloud Comparison")

# Use custom legend to override alpha for visibility
leg = ax.legend(loc="upper right", markerscale=3)
for lh in leg.legend_handles:
    lh.set_alpha(1.0)

plt.tight_layout()

vt_path = FIGS_DIR / "microtrip_clusters_comparison_vt.png"
fig.savefig(vt_path, dpi=150)
print(f"\nSaved comparison plot to: {vt_path}")

# ── Markdown report ───────────────────────────────────────────────────────────
if cluster_stats:
    # Build markdown table manually to avoid tabulate dependency
    headers = ["Cluster", "Microtrips", "Samples", "Mean Speed (km/h)", "95th %ile Speed (km/h)", "RPA (m/s²)"]
    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"

    table_rows = [header_row, sep_row]
    for row in cluster_stats:
        cells = [
            str(row["Cluster"]),
            str(row["Microtrips"]),
            f"{row['Samples']:,}",
            str(row["Mean Speed (km/h)"]),
            str(row["95th %ile Speed (km/h)"]),
            str(row["RPA (m/s²)"]),
        ]
        table_rows.append("| " + " | ".join(cells) + " |")

    table_md = "\n".join(table_rows)

    report = f"""\
# Microtrip Cluster Comparison (v-t)

## Summary

{table_md}

## v-t Scatter Cloud Comparison

Every motion-phase sample plotted as (relative time from microtrip start, speed).
Stop-phase samples excluded. Clusters are color-coded.

![v-t scatter comparison](figs-comparison/microtrip_clusters_comparison_vt.png)
"""

    report_path = REPORTS_DIR / "microtrip_clusters_comparison_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Saved report to: {report_path}")

# %%
plt.show()
