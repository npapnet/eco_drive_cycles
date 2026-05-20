# %%
"""
Cluster Synthesis Step 230 — Compute per-cluster kinematic targets.

For each cluster, computes duration-weighted means of five target metrics
from the microtrip pool.  These become τ_c — the reference statistics that
the stochastic selection step (240) tries to reproduce.

RPA is weighted by distance (energy-consistent); all other metrics weighted
by total microtrip duration (motion + stop).

Output: data/synthesis-cluster/cluster_targets.csv

Next step: 240_cluster_selection.py
"""

import json
from pathlib import Path

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR    = ROOTDIR / _cfg["output_dir"]
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis-cluster"

# Default tolerances (mirroring GTR 15 §4)
TOLERANCES: dict[str, tuple[str, float]] = {
    "mean_speed_kmh": ("abs", 1.0),   # ±1 km/h absolute
    "rpa":            ("rel", 0.05),  # ±5% relative
    "idle_fraction":  ("abs", 0.03),  # ±3% absolute
    "speed_95th_kmh": ("rel", 0.05),  # ±5% relative
}

# ── Load ───────────────────────────────────────────────────────────────────────
clustered_path = SYNTHESIS_DIR / "microtrips_clustered.csv"
if not clustered_path.exists():
    print(f"microtrips_clustered.csv not found. Run 210_cluster_assignment.py first.")
    raise SystemExit(1)

df = pd.read_csv(clustered_path)

if "total_duration_s" not in df.columns:
    df["total_duration_s"] = df["duration_s"] + df["stop_duration_s"]
if "idle_fraction" not in df.columns:
    df["idle_fraction"] = df["stop_duration_s"] / df["total_duration_s"].replace(0.0, float("nan"))

# Sort clusters so the output CSV has a stable order
cluster_order = sorted(df["cluster_id"].unique(), key=lambda x: str(x))

# ── Compute targets per cluster ────────────────────────────────────────────────
rows = []
for cluster in cluster_order:
    grp = df[df["cluster_id"] == cluster].copy()
    if grp.empty:
        continue

    w_dur  = grp["total_duration_s"]
    w_dist = grp["distance_m"]
    s_dur  = w_dur.sum()
    s_dist = w_dist.sum()

    rpa_grp = grp[grp["rpa"].notna() & (grp["distance_m"] > 0)]
    rpa_target = (
        float((rpa_grp["rpa"] * rpa_grp["distance_m"]).sum() / rpa_grp["distance_m"].sum())
        if len(rpa_grp) > 0 else float("nan")
    )

    mean_speed = float((grp["mean_speed_kmh"] * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")
    idle_frac  = float((grp["idle_fraction"].fillna(0) * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")
    v_95       = float((grp["speed_95th_kmh"] * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")

    row: dict = {
        "cluster_id":       cluster,
        "n_microtrips":     len(grp),
        "total_distance_m": round(s_dist, 1),
        "mean_speed_kmh":   round(mean_speed, 3),
        "rpa":              round(rpa_target, 5) if rpa_target == rpa_target else float("nan"),
        "idle_fraction":    round(idle_frac, 4),
        "speed_95th_kmh":   round(v_95, 3),
    }

    for metric, (kind, tol) in TOLERANCES.items():
        val = row[metric]
        if kind == "abs":
            row[f"{metric}_tol_lo"] = round(val - tol, 5)
            row[f"{metric}_tol_hi"] = round(val + tol, 5)
        else:
            row[f"{metric}_tol_lo"] = round(val * (1 - tol), 5)
            row[f"{metric}_tol_hi"] = round(val * (1 + tol), 5)

    rows.append(row)

targets_df = pd.DataFrame(rows).set_index("cluster_id")

# ── Save ───────────────────────────────────────────────────────────────────────
out_path = SYNTHESIS_DIR / "cluster_targets.csv"
targets_df.to_csv(out_path)
print(f"Saved: {out_path}")

print("\nCluster targets:")
print(
    targets_df[["n_microtrips", "total_distance_m", "mean_speed_kmh",
                "rpa", "idle_fraction", "speed_95th_kmh"]].to_string()
)
# %%
