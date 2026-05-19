# WLTP Drive Cycle Synthesis — Implementation Plan

*Based on `microtrip-WLTP-GTR15.md` (UNECE GTR No. 15, Annex 1)*

---

## Prerequisites

Run the existing workflow pipeline through step 03 first:

```
01_ingest.py          → data/trips/*.parquet
02_extract_analyze.py → data/metrics.duckdb
03_build_microtrips.py → data/microtrips/summary.csv
                         data/microtrips/<trip>_mt<NN>.parquet
```

The synthesis scripts pick up from `data/microtrips/` and write to a new sibling
directory `data/synthesis/`.

---

## Output Layout

```
data/synthesis/
├── microtrips_phased.csv          ← step 010  phase label + boundary flag per microtrip
├── markov/
│   ├── global_matrix.csv          ← step 020  T[from_state, to_state]
│   └── microtrip_distances.csv    ← step 020  D(T_i, T) per microtrip (Frobenius)
├── phase_targets.csv              ← step 030  τ_p: weighted-mean targets per phase
├── selected/
│   ├── phase_Low_sequence.csv     ← step 040  selected microtrip list for Low phase
│   ├── phase_Med_sequence.csv
│   ├── phase_High_sequence.csv
│   └── phase_xHigh_sequence.csv
├── selection_report.csv           ← step 040  F_p score and convergence info per phase
├── final_cycle.csv                ← step 050  v(t) at 1 Hz, full assembled cycle
├── final_cycle.png                ← step 050  speed–time plot
└── validation_report.md           ← step 050  per-phase tolerance checks
```

---

## Scripts

| Script | GTR15 section | Input | Key output |
|---|---|---|---|
| `100_wltp_010_phase_assignment.py` | §2 | `microtrips/summary.csv` | `synthesis/microtrips_phased.csv` |
| `100_wltp_020_markov_chain.py` | §3 | `microtrips/*.parquet` | `synthesis/markov/` |
| `100_wltp_030_phase_targets.py` | §4 | `synthesis/microtrips_phased.csv` | `synthesis/phase_targets.csv` |
| `100_wltp_040_selection.py` | §5 | phased, markov, targets | `synthesis/selected/` |
| `100_wltp_050_assembly.py` | §6 | selected sequences + parquets | `synthesis/final_cycle.*` |
| `100_microtrips_synthesis_wltp.py` | all | — | orchestrator |

---

## Step 010 — Phase Assignment (`microtrip-WLTP-GTR15.md` §2)

**Input:** `data/microtrips/summary.csv` (`max_speed_kmh` column already computed by step 03)

**Logic:**

| Phase | Label | v_max range (km/h) |
|---|---|---|
| 1 | Low | ≤ 56.5 |
| 2 | Med | 56.5 < v_max ≤ 76.6 |
| 3 | High | 76.6 < v_max ≤ 97.4 |
| 4 | xHigh | > 97.4 |

Boundary flag: any microtrip whose `max_speed_kmh` is within ±2 km/h of a boundary
is flagged (`boundary_flag = True`). Still assigned to lower phase; eligible for swap
during optimization.

**Output:** `synthesis/microtrips_phased.csv` — `summary.csv` plus `phase` and
`boundary_flag` columns.

---

## Step 020 — Markov Chain Construction (`microtrip-WLTP-GTR15.md` §3)

**Input:** every `data/microtrips/<trip>_mt*.parquet` (filenames from `summary.csv`)

**State space (coarse binning for small datasets):**
- Speed: 10 km/h bins from 0 to max observed speed
- Acceleration: 0.2 m/s² bins from −1.5 to +1.5 m/s² (clamp outliers)
- Uses `smooth_speed_kmh` and `acc_ms2` columns (motion samples only, `stop_phase == False`)

**Transition counting:**
For each consecutive sample pair within a microtrip, increment `C[s_from, s_to]`.
Normalize each row: `T[i, j] = C[i, j] / Σ_j C[i, j]`. Rows with zero counts → 0.

**Per-microtrip Frobenius distance:**

```
D(T_i, T) = ‖T_i[shared] − T[shared]‖_F / n_shared_states
```

where `shared` = states present in both `T_i` and `T`. Normalized by the number of
shared "from" states so distances are comparable across microtrips of different lengths.

**Output:**
- `synthesis/markov/global_matrix.csv` — T as a pivot table (state labels as index/columns)
- `synthesis/markov/microtrip_distances.csv` — `filename`, `markov_distance` columns

---

## Step 030 — Phase Targets (`microtrip-WLTP-GTR15.md` §4)

**Input:** `synthesis/microtrips_phased.csv`

**Computation:** For each phase p, compute duration-weighted means of the five GTR 15
target metrics. Weight = `total_duration_s = duration_s + stop_duration_s`.

| Target metric | Source column | Weight |
|---|---|---|
| `mean_speed_kmh` | `mean_speed_kmh` | `total_duration_s` |
| `rpa` | `rpa` | `distance_m` (energy-consistent) |
| `idle_fraction` | `stop_duration_s / total_duration_s` | `total_duration_s` |
| `speed_95th_kmh` | `speed_95th_kmh` | `total_duration_s` |
| `total_distance_m` | sum of `distance_m` (informational only) | — |

Microtrips with `rpa = NaN` (zero distance or no positive acceleration) are excluded
from the RPA weighted mean.

**Output:** `synthesis/phase_targets.csv` — one row per phase with all target values
plus tolerance columns (`±1 km/h` mean speed, `±5%` RPA, `±3%` idle fraction).

**Default tolerances:**

| Metric | Tolerance |
|---|---|
| mean_speed_kmh | ±1 km/h |
| rpa | ±5% relative |
| idle_fraction | ±3% absolute |
| speed_95th_kmh | ±5% relative |

---

## Step 040 — Stochastic Microtrip Selection (`microtrip-WLTP-GTR15.md` §5)

**Input:**
- `synthesis/microtrips_phased.csv` (phase membership)
- `synthesis/markov/microtrip_distances.csv` (D per microtrip)
- `synthesis/phase_targets.csv` (τ_p)

**Algorithm (per phase, independently):**

1. Compute sampling weights: `w_i = exp(−λ · D(T_i, T))`
2. Repeat up to `N_trials`:
   a. Sample microtrips with replacement from M_p using weights w_i,
      until `total_distance_m ≥ phase_min_distance_m`
   b. Enforce reuse cap: no single microtrip may contribute > 30% of phase
      total duration (down-weight exceeded microtrips in that trial)
   c. Evaluate objective: `F_p = Σ_m w_m · ((τ̂_m − τ_m) / τ_m)²`
   d. Keep sequence if `F_p < F_best`; break early if `F_p < F_threshold`
3. Return best sequence

**Running statistics** (accumulated incrementally, no need to re-read parquets):
- Mean speed: duration-weighted mean of `mean_speed_kmh`
- RPA: distance-weighted mean of `rpa`
- Idle fraction: duration-weighted mean of `idle_fraction`
- v_95: duration-weighted mean of `speed_95th_kmh` (approximation)

**Key parameters (in `config.json` under `"wltp"`):**

| Parameter | Default | Notes |
|---|---|---|
| `markov_lambda` | 1.0 | Temperature for Markov weight |
| `n_trials` | 1000 | Outer loop restarts |
| `f_threshold` | 0.01 | Early-exit objective threshold |
| `max_reuse_fraction` | 0.30 | Max single-microtrip share of phase duration |
| `phase_min_distance_m` | {Low:800, Med:600, High:600, xHigh:1000} | Minimum assembled length |
| `metric_weights` | {mean_speed:1.0, rpa:2.0, idle:0.5, v95:0.5} | Objective weights |

**Output:**
- `synthesis/selected/phase_<p>_sequence.csv` — list of selected microtrips with
  `filename`, `phase`, `trial_index`, `sequence_position`, and all metric columns
- `synthesis/selection_report.csv` — `phase`, `F_p`, `n_microtrips_selected`,
  `total_distance_m`, `n_trials_run`, `converged`

---

## Step 050 — Cycle Assembly and Validation (`microtrip-WLTP-GTR15.md` §6)

**Input:**
- `synthesis/selected/phase_*_sequence.csv`
- `data/microtrips/<trip>_mt*.parquet` (raw speed traces)
- `synthesis/phase_targets.csv`

**Assembly order:** Low → Med → High → xHigh (skip absent phases)

**Per microtrip:** load full parquet (motion + stop), extract `smooth_speed_kmh`
(fall back to `speed_kmh`). Include trailing stop samples verbatim.

**Junction smoothing:** if speed discontinuity > 2 km/h between end of one microtrip
and start of next, insert linear ramp of ceil(|Δv| / 1.0) seconds (max 3 s) to bridge
at max 1 m/s² jerk.

**Inter-phase idle:** insert `inter_phase_idle_s` (default 20 s) of v = 0 between phases.

**Validation:** for each phase segment of the assembled cycle, compute statistics from
the 1Hz trace and compare against `phase_targets.csv` tolerances. Report pass/fail per
metric per phase.

**Output:**
- `synthesis/final_cycle.csv` — columns `t_s`, `speed_kmh`, `phase`
- `synthesis/final_cycle.png` — v(t) plot with phase colour bands
- `synthesis/validation_report.md` — table of target vs. achieved per phase metric

---

## Configuration additions to `config.json`

```json
"wltp": {
    "speed_bin_width_kmh": 10,
    "acc_bin_width_ms2": 0.2,
    "acc_range_ms2": 1.5,
    "markov_lambda": 1.0,
    "n_trials": 1000,
    "f_threshold": 0.01,
    "max_reuse_fraction": 0.30,
    "inter_phase_idle_s": 20,
    "phase_min_distance_m": {
        "Low": 800,
        "Med": 600,
        "High": 600,
        "xHigh": 1000
    },
    "metric_weights": {
        "mean_speed_kmh": 1.0,
        "rpa": 2.0,
        "idle_fraction": 0.5,
        "speed_95th_kmh": 0.5
    }
}
```

---

## Dependency Chain

```
summary.csv
    └── 010_phase_assignment ─────────────────────────────────┐
                                                               │
    microtrips/*.parquet                                       │
        └── 020_markov_chain ─────────────────────────────┐   │
                                                           │   ▼
                                                  030_phase_targets
                                                           │
                                                    040_selection
                                                           │
                                              microtrips/*.parquet
                                                           │
                                                    050_assembly
                                                           │
                                                   final_cycle.csv
```

Each step is independently re-runnable. Steps 030 and 020 can run in parallel after 010.
