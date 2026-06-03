# WLTP-based Synthesis (GTR 15)

Located in `examples/workflow/synthesis-wltp/`. Groups microtrips into fixed
speed-phase boundaries defined by the WLTP GTR 15 standard (Low / Medium / High /
Extra High) and assembles a synthetic drive cycle via stochastic Markov-guided
selection.

**Prerequisites:** run steps `010`, `020`, `030` first.

---

## Run the Full Pipeline

```bash
uv run python examples/workflow/synthesis-wltp/100_microtrips_synthesis_wltp.py
```

The orchestrator script runs steps 110–150 in sequence.

---

## Step-by-Step

```{mermaid}
flowchart LR
    s110["110\nPhase Assignment\nLow/Med/High/xHigh"] --> s120
    s120["120\nMarkov Chain\nGlobal matrix T\nFrobenius distances"] --> s130
    s130["130\nPhase Targets\nKinematic τ_p per phase"] --> s140
    s140["140\nStochastic Selection\nMarkov-guided per phase"] --> s150
    s150["150\nAssembly & Validation\n1 Hz final_cycle.csv"]
```

### 110 — Phase Assignment

Assigns each microtrip to one of four WLTP speed phases based on its maximum speed:

| Phase | v_max range |
|---|---|
| Low | 0 – 56.5 km/h |
| Medium | 56.5 – 76.6 km/h |
| High | 76.6 – 97.4 km/h |
| Extra High | > 97.4 km/h |

Writes `data/synthesis/microtrips_phased.csv`.

### 120 — Markov Chain

Builds the global Markov transition matrix **T** from the observed microtrip sequence.
Computes per-microtrip Frobenius distances from **T** as a diversity measure.

Writes:
- `data/synthesis/markov/global_matrix.csv`
- `data/synthesis/markov/microtrip_distances.csv`

### 130 — Phase Targets

Computes duration-weighted kinematic targets τ_p (mean speed, stop fraction,
acceleration/deceleration RMS) for each phase from the full microtrip pool.

Writes `data/synthesis/target_kinematics.csv`.

### 140 — Stochastic Selection

Iteratively selects microtrips per phase, guided by:

1. Markov transition probabilities (sequence realism)
2. Deviation from phase kinematic targets
3. Minimum distance constraint per phase (from `config_wltp.json`)

Repeats the selection until targets are met within tolerance or iteration limit is
reached.

Writes `data/synthesis/selected/phase_<phase>_sequence.csv` for each phase, and
`data/synthesis/selection_report.csv`.

### 150 — Assembly & Validation

Concatenates selected microtrip sequences in phase order (Low → Med → High → xHigh),
smooths junctions between adjacent microtrips, and validates the assembled cycle
against GTR 15 kinematic tolerances.

Writes:
- `data/synthesis/final_cycle.csv` — 1 Hz speed profile with columns `t_s`, `speed_kmh`, `phase`
- `data/synthesis/final_cycle.png` — speed-time plot
- `data/synthesis/validation_report.md` — Pass/Fail table per metric per phase

---

## Configuration (`config_wltp.json`)

Key parameters:

| Key | Description |
|---|---|
| `weights` | Relative importance of each kinematic target in the objective |
| `random_seed` | Reproducibility seed for stochastic selection |
| `target_tolerances` | Acceptable deviation (%) per metric |
| `min_distance_per_phase` | Minimum cumulative distance (m) required per phase |
