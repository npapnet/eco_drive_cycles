# %%
"""
WLTP Drive Cycle Synthesis.

Loads the persisted microtrip collection, assigns microtrips to WLTP phases
(GTR 15 §2.1 boundaries), and synthesises a representative 1-Hz speed-time
cycle via the package's Markov-guided stochastic selection + assembly pipeline.

Prerequisites:
  Run 010_ingest.py → 030_build_microtrips.py first.
  Parameters are in config.json (shared) and config_wltp.json (WLTP-specific).

Outputs:
  OUTPUT_DIR/synthesis/final_cycle.csv  — t_s, speed_kmh, group (1-Hz)
  OUTPUT_DIR/synthesis/final_cycle.png  — speed-time plot with phase bands
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt

from drive_cycle_calculator.microtrip_collection import MicrotripCollection
from drive_cycle_calculator.schema import WLTPSynthesisConfig
from drive_cycle_calculator.synthesis import synthesize
from drive_cycle_calculator.synthesis.wltp import assign_wltp_phases

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg  = json.loads((Path(__file__).parent.parent / "config.json").read_text())
_wltp = json.loads((Path(__file__).parent.parent / "config_wltp.json").read_text())

OUTPUT_DIR     = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR  = OUTPUT_DIR / "synthesis"
SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)

config = WLTPSynthesisConfig.model_validate(_wltp)

PHASE_ORDER   = ["Low", "Med", "High", "xHigh"]
PHASE_COLOURS = {"Low": "#4dac26", "Med": "#f1b619", "High": "#d01c8b", "xHigh": "#0571b0"}

# ── Load microtrips ────────────────────────────────────────────────────────────
if not MICROTRIPS_DIR.is_dir():
    print(f"microtrips/ not found under {OUTPUT_DIR}. Run 030_build_microtrips.py first.")
    raise SystemExit(1)

mc = MicrotripCollection.from_parquets(MICROTRIPS_DIR)
print(f"Loaded {len(mc)} microtrips.")

# ── Assign WLTP phases ────────────────────────────────────────────────────────
assignments = assign_wltp_phases(mc.summary)
phase_counts = assignments.value_counts().to_dict()
print(f"Phase distribution: {phase_counts}")
small = [p for p, n in phase_counts.items() if n < 10]
if small:
    print(f"  WARNING: small phase pools (< 10): {small} — reuse will occur during selection.")

# ── Synthesize ────────────────────────────────────────────────────────────────
print("Running synthesis …")
cycle = synthesize(mc, assignments, config)
print(f"Cycle: {len(cycle)} s = {len(cycle) / 60:.1f} min")

# ── Save CSV ──────────────────────────────────────────────────────────────────
csv_path = SYNTHESIS_DIR / "final_cycle.csv"
cycle.to_csv(csv_path, index=False)
print(f"Saved: {csv_path}")

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 4))
v_max = cycle["speed_kmh"].max()

for phase in PHASE_ORDER:
    grp_df = cycle[cycle["group"] == phase]
    if grp_df.empty:
        continue
    colour = PHASE_COLOURS[phase]
    start, end = int(grp_df["t_s"].min()), int(grp_df["t_s"].max()) + 1
    ax.axvspan(start, end, alpha=0.12, color=colour, lw=0)
    ax.text(
        (start + end) / 2, v_max * 0.92, phase,
        ha="center", va="bottom", fontsize=8, color=colour, fontweight="bold",
    )

ax.plot(cycle["t_s"], cycle["speed_kmh"], lw=0.8, color="#222")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Speed (km/h)")
ax.set_title("Synthesised WLTP Drive Cycle")
ax.set_xlim(0, cycle["t_s"].max())
ax.set_ylim(0)
plt.tight_layout()

png_path = SYNTHESIS_DIR / "final_cycle.png"
fig.savefig(png_path, dpi=150)
print(f"Saved: {png_path}")
plt.show()
# %%
