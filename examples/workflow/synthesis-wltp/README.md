# WLTP-based Drive Cycle Synthesis (GTR 15)

This subfolder contains the scripts to synthesize a representative drive cycle by grouping microtrips using the fixed speed-phase boundaries defined in the WLTP (Worldwide Harmonized Light Vehicles Test Procedure) GTR 15 standard.

## Prerequisites

Before running the synthesis pipeline, run the core workflow scripts first:

```bash
uv run python examples/workflow/010_ingest.py
uv run python examples/workflow/020_extract_analyze.py
uv run python examples/workflow/030_build_microtrips.py
```

These steps generate the necessary microtrips and their statistical summaries.

## Running the full pipeline

You can run the entire synthesis pipeline in sequence using the orchestrator:

```bash
uv run python examples/workflow/synthesis-wltp/100_microtrips_synthesis_wltp.py
```

## Running Individual Steps

For partial re-runs (e.g. to try a different stochastically-selected sequence without re-building the Markov chain), run the steps individually:

| Script | Description |
|---|---|
| `110_wltp_phase_assignment.py` | Assign microtrips to Low/Med/High/xHigh phases based on GTR 15 speed boundaries |
| `120_wltp_markov_chain.py` | Build the global Markov transition matrix T and compute Frobenius distance metrics |
| `130_wltp_phase_targets.py` | Compute target kinematic parameters (e.g. duration, distance, mean speed) for each phase |
| `140_wltp_selection.py` | Perform stochastic selection of microtrips guiding on targets and Markov transitions |
| `150_wltp_assembly.py` | Assemble selected microtrips, smooth transitions, and validate the resulting cycle |

## Configuration

The scripts in this folder read configuration parameters from the parent directory:

1. **`../config.json`** — General output folder and segmentation settings.
2. **`../config_wltp.json`** — WLTP synthesis-specific settings (weights, random seeds, target tolerances, and bin widths).

## Outputs (`data/synthesis/`)

The output files are saved under the `data/synthesis/` directory:

```
data/synthesis/
├── microtrips_phased.csv      — Microtrips with phase assignment labels
├── target_kinematics.csv      — Kinematic targets for each phase
├── markov/
│   ├── global_matrix.csv       — Global Markov transition matrix T
│   └── microtrip_distances.csv — Frobenius distances from the global matrix
├── selected/
│   └── phase_<phase>_sequence.csv — Selected microtrips sequence for each phase
├── selection_report.csv       — Final objective score and values for selection
├── final_cycle.csv            — Assembled 1-Hz drive cycle (t_s, speed_kmh, phase)
├── final_cycle.png            — Speed-time plot showing the synthesized cycle
└── validation_report.md       — Kinematic validation report (Pass/Fail table)
```
