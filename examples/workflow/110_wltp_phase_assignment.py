# %%
"""
WLTP Step 110 — Assign microtrips to WLTP phases (GTR 15 §2).

Reads data/microtrips/summary.csv, adds three columns:
  - phase          : "Low" / "Med" / "High" / "xHigh"  (based on max_speed_kmh)
  - boundary_flag  : True when v_max is within ±2 km/h of a phase boundary
  - total_duration_s, idle_fraction  (derived columns used by later steps)

Output: data/synthesis/microtrips_phased.csv

Next step: 120_wltp_markov_chain.py (and 130_wltp_phase_targets.py, independently)
"""

import json
from pathlib import Path

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis"

# GTR 15 §2.1 — fixed phase boundaries (km/h); lower bound exclusive, upper inclusive
PHASE_BOUNDARIES = [
    ("Low",    0.0,   56.5),
    ("Med",   56.5,   76.6),
    ("High",  76.6,   97.4),
    ("xHigh", 97.4, float("inf")),
]
BOUNDARY_SPEEDS = [56.5, 76.6, 97.4]
BOUNDARY_TOL_KMH = 2.0
PHASE_ORDER = ["Low", "Med", "High", "xHigh"]

# ── Load ───────────────────────────────────────────────────────────────────────
summary_path = MICROTRIPS_DIR / "summary.csv"
if not summary_path.exists():
    print(f"summary.csv not found at {summary_path}.")
    print("Run 03_build_microtrips.py first.")
    raise SystemExit(1)

df = pd.read_csv(summary_path)
print(f"Loaded {len(df)} microtrips from {summary_path}")

if "max_speed_kmh" not in df.columns:
    print("ERROR: 'max_speed_kmh' column missing — re-run 03_build_microtrips.py.")
    raise SystemExit(1)

# ── Phase assignment ───────────────────────────────────────────────────────────
def _assign_phase(v: float) -> str:
    for label, lo, hi in PHASE_BOUNDARIES:
        if lo < v <= hi:
            return label
    return "Low"  # v == 0 edge case

df["phase"] = df["max_speed_kmh"].apply(_assign_phase)

# ── Boundary flag ──────────────────────────────────────────────────────────────
df["boundary_flag"] = df["max_speed_kmh"].apply(
    lambda v: any(abs(v - b) <= BOUNDARY_TOL_KMH for b in BOUNDARY_SPEEDS)
)

# ── Derived columns for later steps ───────────────────────────────────────────
df["total_duration_s"] = df["duration_s"] + df["stop_duration_s"]
df["idle_fraction"] = df["stop_duration_s"] / df["total_duration_s"].replace(0.0, float("nan"))

# ── Save ───────────────────────────────────────────────────────────────────────
SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
out_path = SYNTHESIS_DIR / "microtrips_phased.csv"
df.to_csv(out_path, index=False)
print(f"Saved: {out_path}")

# ── Report ─────────────────────────────────────────────────────────────────────
summary = (
    df.groupby("phase")
    .agg(
        count=("phase", "size"),
        boundary=("boundary_flag", "sum"),
        mean_vmax=("max_speed_kmh", "mean"),
        min_vmax=("max_speed_kmh", "min"),
        max_vmax=("max_speed_kmh", "max"),
    )
    .reindex(PHASE_ORDER)
    .dropna(how="all")
    .round(1)
)

print("\nPhase distribution:")
print(summary.to_string())

small_phases = summary[summary["count"] < 10].index.tolist()
if small_phases:
    print(f"\nWARNING: Small phase pools (< 10 microtrips): {small_phases}")
    print("  Microtrip reuse will be required in the selection step.")
# %%
