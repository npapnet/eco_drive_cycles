# %%
"""
WLTP Step 130 — Compute phase-level kinematic targets (GTR 15 §4).

For each phase, computes duration-weighted means of five GTR 15 target metrics
from the microtrip pool.  These become τ_p — the reference statistics that the
stochastic selection step (140) tries to reproduce.

RPA is weighted by distance (energy-consistent); all other metrics weighted by
total microtrip duration (motion + stop).

Output: data/synthesis/phase_targets.csv

Next step: 140_wltp_selection.py
"""

import json
from pathlib import Path

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR    = ROOTDIR / _cfg["output_dir"]
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis"

PHASE_ORDER = ["Low", "Med", "High", "xHigh"]

# GTR 15 §4 default tolerances
TOLERANCES: dict[str, tuple[str, float]] = {
    "mean_speed_kmh": ("abs", 1.0),   # ±1 km/h absolute
    "rpa":            ("rel", 0.05),  # ±5% relative
    "idle_fraction":  ("abs", 0.03),  # ±3% absolute
    "speed_95th_kmh": ("rel", 0.05),  # ±5% relative
}

# ── Load ───────────────────────────────────────────────────────────────────────
phased_path = SYNTHESIS_DIR / "microtrips_phased.csv"
if not phased_path.exists():
    print(f"microtrips_phased.csv not found. Run 110_wltp_phase_assignment.py first.")
    raise SystemExit(1)

df = pd.read_csv(phased_path)

if "total_duration_s" not in df.columns:
    df["total_duration_s"] = df["duration_s"] + df["stop_duration_s"]
if "idle_fraction" not in df.columns:
    df["idle_fraction"] = df["stop_duration_s"] / df["total_duration_s"].replace(0.0, float("nan"))

# ── Compute targets per phase ──────────────────────────────────────────────────
rows = []
for phase in PHASE_ORDER:
    grp = df[df["phase"] == phase].copy()
    if grp.empty:
        continue

    w_dur  = grp["total_duration_s"]
    w_dist = grp["distance_m"]
    s_dur  = w_dur.sum()
    s_dist = w_dist.sum()

    # RPA: distance-weighted; exclude zero-distance or NaN rows
    rpa_grp = grp[grp["rpa"].notna() & (grp["distance_m"] > 0)]
    rpa_target = (
        float((rpa_grp["rpa"] * rpa_grp["distance_m"]).sum() / rpa_grp["distance_m"].sum())
        if len(rpa_grp) > 0 else float("nan")
    )

    mean_speed = float((grp["mean_speed_kmh"] * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")
    idle_frac  = float((grp["idle_fraction"].fillna(0) * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")
    v_95       = float((grp["speed_95th_kmh"] * w_dur).sum() / s_dur) if s_dur > 0 else float("nan")

    row: dict = {
        "phase":           phase,
        "n_microtrips":    len(grp),
        "total_distance_m": round(s_dist, 1),
        "mean_speed_kmh":  round(mean_speed, 3),
        "rpa":             round(rpa_target, 5) if rpa_target == rpa_target else float("nan"),
        "idle_fraction":   round(idle_frac, 4),
        "speed_95th_kmh":  round(v_95, 3),
    }

    # Tolerance bounds
    for metric, (kind, tol) in TOLERANCES.items():
        val = row[metric]
        if kind == "abs":
            row[f"{metric}_tol_lo"] = round(val - tol, 5)
            row[f"{metric}_tol_hi"] = round(val + tol, 5)
        else:
            row[f"{metric}_tol_lo"] = round(val * (1 - tol), 5)
            row[f"{metric}_tol_hi"] = round(val * (1 + tol), 5)

    rows.append(row)

targets_df = pd.DataFrame(rows).set_index("phase")

# ── Save ───────────────────────────────────────────────────────────────────────
out_path = SYNTHESIS_DIR / "phase_targets.csv"
targets_df.to_csv(out_path)
print(f"Saved: {out_path}")

print("\nPhase targets:")
print(
    targets_df[["n_microtrips", "total_distance_m", "mean_speed_kmh",
                "rpa", "idle_fraction", "speed_95th_kmh"]].to_string()
)
# %%
