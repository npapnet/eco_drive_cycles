# %%
"""
Cluster-based Drive Cycle Synthesis — Orchestrator.

Runs the full cluster-based drive cycle synthesis pipeline in order:

  210_cluster_assignment.py   — load KMeans cluster labels (from step 04)
  220_cluster_markov_chain.py — global Markov transition matrix
  230_cluster_targets.py      — per-cluster kinematic targets τ_c
  240_cluster_selection.py    — stochastic microtrip selection per cluster
  250_cluster_assembly.py     — cycle assembly, smoothing, validation

Prerequisites:
  Run 01_ingest.py → 02_extract_analyze.py → 03_build_microtrips.py first.
  Step 04_microtrip_clustering.py is strongly recommended so that
  summary_clustered.csv is available; step 210 will fall back to inline
  KMeans otherwise.

All algorithm parameters live in config_syn_cluster.json (same directory).

For partial re-runs (e.g. retry selection without rebuilding the Markov matrix):
  uv run python examples/workflow-syn-cluster/240_cluster_selection.py
  uv run python examples/workflow-syn-cluster/250_cluster_assembly.py
"""

import subprocess
import sys
from pathlib import Path

STEPS = [
    "210_cluster_assignment.py",
    "220_cluster_markov_chain.py",
    "230_cluster_targets.py",
    "240_cluster_selection.py",
    "250_cluster_assembly.py",
]

SCRIPT_DIR = Path(__file__).parent

for step in STEPS:
    script = SCRIPT_DIR / step
    print(f"\n{'─' * 60}")
    print(f"  {step}")
    print("─" * 60)
    result = subprocess.run([sys.executable, str(script)], check=False)
    if result.returncode != 0:
        print(f"\n✗  {step} failed (exit {result.returncode}) — pipeline aborted.")
        sys.exit(result.returncode)

print("\n✓  Cluster synthesis complete — outputs in data/synthesis-cluster/")
# %%
