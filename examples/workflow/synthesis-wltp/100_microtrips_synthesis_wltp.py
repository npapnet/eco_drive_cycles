# %%
"""
WLTP Cycle Synthesis — Orchestrator.

Runs the full GTR 15-based drive cycle synthesis pipeline in order:

  110_wltp_phase_assignment.py  — phase labelling from max_speed_kmh
  120_wltp_markov_chain.py      — global Markov transition matrix
  130_wltp_phase_targets.py     — phase kinematic targets τ_p
  140_wltp_selection.py         — stochastic microtrip selection per phase
  150_wltp_assembly.py          — cycle assembly, smoothing, validation

Prerequisites:
  Run 01_ingest.py → 02_extract_analyze.py → 03_build_microtrips.py first.
  All algorithm parameters live in config_wltp.json (same directory).

For partial re-runs (e.g. retry selection without rebuilding the Markov matrix):
  uv run python examples/workflow/140_wltp_selection.py
  uv run python examples/workflow/150_wltp_assembly.py
"""

import subprocess
import sys
from pathlib import Path

STEPS = [
    "110_wltp_phase_assignment.py",
    "120_wltp_markov_chain.py",
    "130_wltp_phase_targets.py",
    "140_wltp_selection.py",
    "150_wltp_assembly.py",
]

SCRIPT_DIR = Path(__file__).parent

# ── Run ────────────────────────────────────────────────────────────────────────
for step in STEPS:
    script = SCRIPT_DIR / step
    print(f"\n{'-' * 60}")
    print(f"  {step}")
    print("-" * 60)
    result = subprocess.run([sys.executable, str(script)], check=False)
    if result.returncode != 0:
        print(f"\n[ERROR]  {step} failed (exit {result.returncode}) - pipeline aborted.")
        sys.exit(result.returncode)

print("\n[SUCCESS]  WLTP synthesis complete - outputs in data/synthesis/")
# %%
