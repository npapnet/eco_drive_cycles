# %%
"""
Step 050 — Cluster visualisation: v-t scatter cloud and v-a density hexbin.

Reads the clustered summary CSV produced by 040_microtrip_clustering.py (or
04_microtrip_clustering.py) and the per-microtrip Parquet files produced by
030_build_microtrips.py / 03_build_microtrips.py.

Two figures are produced:

  Figure 1  v-a density cloud  [DISABLED by default]
    Hexbin of Speed (x) vs. Acceleration (y) for all motion-phase samples in
    the selected cluster.  Set ENABLE_VA_DENSITY = True to activate.

  Figure 2  v-t scatter cloud  [active]
    Every (relative time, speed) sample from every microtrip in the cluster,
    re-zeroed to t = 0, plotted as a raw point cloud.

Cluster selection: edit CLUSTER_ID below.
Paths are read from config.json in the same directory.

# ── Scalability note ──────────────────────────────────────────────────────────
# The current approach (raw matplotlib scatter with alpha blending) is adequate
# for the present dataset (~17 k points for the largest cluster).  It remains
# comfortable up to roughly 100 k–500 k points depending on figure size and
# renderer.  For fleet-scale datasets the following alternatives should be
# considered — listed in order of implementation effort and ascending scale:
#
# 1. Hexbin  (matplotlib.axes.Axes.hexbin)
#    O(n) binning; renders density as coloured hexagons.  Drop-in replacement:
#      ax.hexbin(t_all, v_all, gridsize=60, cmap="YlOrRd")
#    Handles tens of millions of points.  Same API for both v-t and v-a axes.
#
# 2. 2-D histogram + pcolormesh  (numpy.histogram2d → ax.pcolormesh)
#    Rectangular bins; gives fine control over bin edges (e.g. fixed 1 s ×
#    1 km/h grid).  Comparable speed to hexbin.
#
# 3. KDE2D  (seaborn.kdeplot or scipy.stats.gaussian_kde)
#    Smooth isocontour lines over the density field.  Beautiful but O(n·m)
#    where m is the evaluation grid size.  Only practical after subsampling to
#    ≤ 50 k points, or with a fast bandwidth estimator (scikit-learn
#    KernelDensity with the ball_tree algorithm).
#
# 4. Stratified / random subsampling before any plot call
#    Sample a fixed budget (e.g. 20 k points) proportionally from each
#    microtrip so every segment contributes equally regardless of length.
#    Fastest retrofit: insert one pd.DataFrame.sample() call before plotting.
#
# 5. Datashader  (pip install datashader)
#    Designed for 10 M – 1 B+ points.  Aggregates data into a fixed-resolution
#    raster *before* rendering; memory cost is O(W × H), not O(n).
#    Best long-term choice for fleet-scale v-t and v-a density maps.
#    See: https://datashader.org/user_guide/Points.html
#
# 6. Vaex  (pip install vaex)
#    Out-of-core DataFrame library with built-in 2-D binned statistics and
#    plot helpers.  Can process datasets larger than RAM via memory-mapped
#    Arrow / HDF5 files — useful when microtrip Parquets are too large to
#    concatenate in memory.
# ─────────────────────────────────────────────────────────────────────────────
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

MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"

# ── User-adjustable settings ──────────────────────────────────────────────────

# Cluster label to visualise (integer, must exist in summary_clustered.csv).
CLUSTER_ID: int = 0

# Set to True to also produce Figure 1 (v-a density hexbin).
ENABLE_VA_DENSITY: bool = True

# ── Load clustered summary ────────────────────────────────────────────────────
summary_path = MICROTRIPS_DIR / "summary_clustered.csv"
if not summary_path.exists():
    print(f"Summary not found: {summary_path}")
    print("Run 04_microtrip_clustering.py (or 040_*) first.")
    raise SystemExit(1)

df_summary = pd.read_csv(summary_path)
cluster_df = df_summary[df_summary["cluster"] == CLUSTER_ID].copy()

if cluster_df.empty:
    available = sorted(df_summary["cluster"].unique())
    print(f"No microtrips found for cluster {CLUSTER_ID}.")
    print(f"Available cluster IDs: {available}")
    raise SystemExit(1)

n_microtrips = len(cluster_df)
print(f"Cluster {CLUSTER_ID}: {n_microtrips} microtrip(s) selected.")

# ── Load motion-phase samples from Parquet files ──────────────────────────────
# Only motion-phase samples (stop_phase == False) are loaded.
# Stop-phase samples cluster around (speed ≈ 0, acc ≈ 0) and would obscure
# the motion signature in both the v-a and v-t figures.

frames: list[pd.DataFrame] = []
missing = 0

for _, row in cluster_df.iterrows():
    p = MICROTRIPS_DIR / row["filename"]
    if not p.exists():
        missing += 1
        print(f"  WARNING  Parquet not found: {p.name} — skipped.")
        continue

    part = pd.read_parquet(p, columns=["elapsed_s", "smooth_speed_kmh", "acc_ms2", "stop_phase"])
    motion = part[~part["stop_phase"]].copy()

    if motion.empty:
        continue

    # Re-zero the time axis so every microtrip starts at t = 0.
    motion["t_rel"] = motion["elapsed_s"] - motion["elapsed_s"].iloc[0]
    frames.append(motion)

if not frames:
    print("No motion-phase data loaded. Check that microtrip Parquets exist.")
    raise SystemExit(1)

data = pd.concat(frames, ignore_index=True)
n_samples = len(data)
print(f"  Motion samples loaded: {n_samples:,}")

t_all = data["t_rel"].to_numpy()
v_all = data["smooth_speed_kmh"].to_numpy()
a_all = data["acc_ms2"].to_numpy()

# ── Figure 1 — v-a Density Cloud (disabled by default) ───────────────────────
# Set ENABLE_VA_DENSITY = True at the top of this file to activate.
if ENABLE_VA_DENSITY:
    fig1, ax1 = plt.subplots(figsize=(8, 5))

    hb = ax1.hexbin(
        v_all,
        a_all,
        gridsize=40,
        cmap="YlOrRd",
        mincnt=1,
    )
    fig1.colorbar(hb, ax=ax1, label="Sample count")
    ax1.axhline(0, color="k", linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.set_xlabel("Speed (km/h)")
    ax1.set_ylabel("Acceleration (m/s²)")
    ax1.set_title(f"v-a Density Cloud — Cluster {CLUSTER_ID}")
    ax1.text(
        0.98,
        0.97,
        f"n = {n_microtrips} microtrips\n{n_samples:,} samples",
        transform=ax1.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
    )
    plt.tight_layout()

    va_path = REPORTS_DIR / f"cluster_{CLUSTER_ID}_va_density.png"
    fig1.savefig(va_path, dpi=150)
    print(f"  Saved: {va_path}")
else:
    print("  Figure 1 (v-a density) disabled — set ENABLE_VA_DENSITY = True to activate.")

# %%
# ── Figure 2 — v-t Scatter Cloud ─────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(10, 5))

ax2.scatter(
    t_all,
    v_all,
    s=4,
    alpha=0.15,
    linewidths=0,
    color="steelblue",
    rasterized=True,  # keeps PDF/SVG export sizes manageable
)

ax2.set_xlabel("Relative time (s)")
ax2.set_ylabel("Speed (km/h)")
ax2.set_title(f"v-t Scatter Cloud — Cluster {CLUSTER_ID}")
ax2.text(
    0.98,
    0.97,
    (
        f"Cluster {CLUSTER_ID}\n"
        f"n = {n_microtrips} microtrips\n"
        f"{n_samples:,} samples\n"
        f"mean speed: {v_all.mean():.1f} km/h\n"
        f"max speed:  {v_all.max():.1f} km/h"
    ),
    transform=ax2.transAxes,
    ha="right",
    va="top",
    fontsize=8,
    bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
)
plt.tight_layout()

vt_path = REPORTS_DIR / f"cluster_{CLUSTER_ID}_vt_scatter.png"
fig2.savefig(vt_path, dpi=150)
print(f"  Saved: {vt_path}")

# ── Markdown report ───────────────────────────────────────────────────────────
mean_speed_cluster = cluster_df["mean_speed_kmh"].mean()
mean_duration_cluster = cluster_df["duration_s"].mean()

_va_section = (
    f"## v-a Density Cloud\n\n![v-a density](cluster_{CLUSTER_ID}_va_density.png)\n"
    if ENABLE_VA_DENSITY
    else (
        "## v-a Density Cloud\n\n"
        "_Disabled. Set `ENABLE_VA_DENSITY = True` and re-run to generate._\n"
    )
)

report = f"""\
# Cluster {CLUSTER_ID} — Visualisation Report

## Summary

| Metric | Value |
| --- | --- |
| Microtrips | {n_microtrips} |
| Motion samples | {n_samples:,} |
| Mean speed (km/h) | {mean_speed_cluster:.2f} |
| Mean duration (s) | {mean_duration_cluster:.1f} |

## v-t Scatter Cloud

Every motion-phase sample plotted as (relative time from microtrip start, speed).
Stop-phase samples excluded.

![v-t scatter](cluster_{CLUSTER_ID}_vt_scatter.png)

{_va_section}
"""

report_path = REPORTS_DIR / f"cluster_{CLUSTER_ID}_visualisation_report.md"
report_path.write_text(report, encoding="utf-8")
print(f"  Report: {report_path}")

# %%
plt.show()
