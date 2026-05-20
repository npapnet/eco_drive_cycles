# %%
"""
WLTP Step 140 — Stochastic microtrip selection per phase (GTR 15 §5).

For each phase independently, assembles a sequence of microtrips (with
replacement if the pool is small) guided by two objectives:

  1. Markov fidelity — microtrips are drawn with probability proportional to
     exp(−λ · D(T_i, T)), where D is the Frobenius distance computed in step 120.
  2. Kinematic match — the assembled sequence's weighted-mean statistics
     (mean speed, RPA, idle fraction, v_95) should match the phase targets τ_p
     from step 130 within tolerance.

Search strategy: repeat N_trials random assemblies, keep the sequence with the
lowest objective F_p; break early when F_p < f_threshold.

Outputs:
  data/synthesis/selected/phase_<p>_sequence.csv  — one row per selected microtrip
  data/synthesis/selection_report.csv             — F_p and convergence per phase

Next step: 150_wltp_assembly.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg  = json.loads((Path(__file__).parent / "config.json").read_text())
_wltp = json.loads((Path(__file__).parent / "config_wltp.json").read_text())

OUTPUT_DIR    = ROOTDIR / _cfg["output_dir"]
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis"
SELECTED_DIR  = SYNTHESIS_DIR / "selected"

PHASE_ORDER     = ["Low", "Med", "High", "xHigh"]
LAM             = float(_wltp["markov_lambda"])
N_TRIALS        = int(_wltp["n_trials"])
F_THRESH        = float(_wltp["f_threshold"])
MAX_REUSE       = float(_wltp["max_reuse_fraction"])
MIN_DIST        = _wltp["phase_min_distance_m"]        # dict phase → metres
METRIC_WEIGHTS  = _wltp["metric_weights"]              # dict metric → float
RNG_SEED        = int(_wltp.get("random_seed", 42))

# ── Load inputs ────────────────────────────────────────────────────────────────
for path, label in [
    (SYNTHESIS_DIR / "microtrips_phased.csv",            "microtrips_phased.csv"),
    (SYNTHESIS_DIR / "markov" / "microtrip_distances.csv", "microtrip_distances.csv"),
    (SYNTHESIS_DIR / "phase_targets.csv",                "phase_targets.csv"),
]:
    if not path.exists():
        print(f"{label} not found at {path}.")
        raise SystemExit(1)

phased_df  = pd.read_csv(SYNTHESIS_DIR / "microtrips_phased.csv")
dist_df    = pd.read_csv(SYNTHESIS_DIR / "markov" / "microtrip_distances.csv")
targets_df = pd.read_csv(SYNTHESIS_DIR / "phase_targets.csv", index_col="phase")

if "total_duration_s" not in phased_df.columns:
    phased_df["total_duration_s"] = phased_df["duration_s"] + phased_df["stop_duration_s"]
if "idle_fraction" not in phased_df.columns:
    phased_df["idle_fraction"] = (
        phased_df["stop_duration_s"] / phased_df["total_duration_s"].replace(0.0, float("nan"))
    )

phased_df = phased_df.merge(dist_df[["filename", "markov_distance"]], on="filename", how="left")
phased_df["markov_distance"] = phased_df["markov_distance"].fillna(1.0)

# ── Objective helpers ──────────────────────────────────────────────────────────

def _seq_stats(seq_df: pd.DataFrame) -> dict[str, float]:
    s_dur  = seq_df["total_duration_s"].sum()
    s_dist = seq_df["distance_m"].sum()
    if s_dur == 0 or s_dist == 0:
        return {}

    rpa_ok = seq_df[seq_df["rpa"].notna() & (seq_df["distance_m"] > 0)]
    rpa = (
        float((rpa_ok["rpa"] * rpa_ok["distance_m"]).sum() / rpa_ok["distance_m"].sum())
        if len(rpa_ok) > 0 else 0.0
    )

    return {
        "mean_speed_kmh": float((seq_df["mean_speed_kmh"] * seq_df["total_duration_s"]).sum() / s_dur),
        "rpa":            rpa,
        "idle_fraction":  float((seq_df["idle_fraction"].fillna(0) * seq_df["total_duration_s"]).sum() / s_dur),
        "speed_95th_kmh": float((seq_df["speed_95th_kmh"] * seq_df["total_duration_s"]).sum() / s_dur),
    }


def _objective(seq_df: pd.DataFrame, targets: dict) -> float:
    stats = _seq_stats(seq_df)
    if not stats:
        return float("inf")
    F = 0.0
    for metric, hat in stats.items():
        tau = targets.get(metric)
        w   = METRIC_WEIGHTS.get(metric, 1.0)
        if tau and tau != 0:
            F += w * ((hat - tau) / tau) ** 2
    return F

# ── Stochastic selection ───────────────────────────────────────────────────────

def _select_phase(
    phase_df: pd.DataFrame,
    targets: dict,
    min_dist_m: float,
    rng: np.random.Generator,
) -> tuple[list[int], float, int, bool]:
    """Return (iloc_indices, best_F, n_trials_run, converged)."""
    n = len(phase_df)
    dists     = phase_df["markov_distance"].fillna(1.0).values
    base_w    = np.exp(-LAM * dists)
    base_w   /= base_w.sum()

    durations = phase_df["total_duration_s"].values
    distances = phase_df["distance_m"].values

    best_seq: list[int] = []
    best_F = float("inf")

    for trial in range(N_TRIALS):
        seq: list[int] = []
        total_dist = 0.0
        total_dur  = 0.0
        usage_dur  = np.zeros(n, dtype=float)

        while total_dist < min_dist_m:
            w = base_w.copy()
            if total_dur > 0:
                w[usage_dur / total_dur > MAX_REUSE] = 0.0
                if w.sum() == 0.0:
                    w = base_w.copy()
            w /= w.sum()

            chosen = int(rng.choice(n, p=w))
            seq.append(chosen)
            total_dist        += distances[chosen]
            total_dur         += durations[chosen]
            usage_dur[chosen] += durations[chosen]

        F = _objective(phase_df.iloc[seq], targets)
        if F < best_F:
            best_F   = F
            best_seq = seq[:]
            if F < F_THRESH:
                return best_seq, best_F, trial + 1, True

    return best_seq, best_F, N_TRIALS, False

# ── Run per phase ──────────────────────────────────────────────────────────────

SELECTED_DIR.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(RNG_SEED)
report_rows = []

for phase in PHASE_ORDER:
    phase_df = phased_df[phased_df["phase"] == phase].reset_index(drop=True)

    if phase_df.empty:
        print(f"  {phase}: no microtrips — skipped.")
        continue
    if phase not in targets_df.index:
        print(f"  {phase}: no target entry — skipped.")
        continue

    targets   = targets_df.loc[phase].to_dict()
    min_dist  = float(MIN_DIST.get(phase, 600))

    print(f"  {phase}: {len(phase_df)} microtrips, min dist {min_dist:.0f} m …", end=" ", flush=True)

    iloc_seq, best_F, n_run, converged = _select_phase(phase_df, targets, min_dist, rng)

    status = "converged" if converged else f"best F={best_F:.5f}"
    print(f"{n_run} trials — {status}")

    out_df = phase_df.iloc[iloc_seq].copy()
    out_df.insert(0, "sequence_position", range(len(iloc_seq)))
    out_df.to_csv(SELECTED_DIR / f"phase_{phase}_sequence.csv", index=False)

    stats = _seq_stats(phase_df.iloc[iloc_seq])
    report_rows.append({
        "phase":                phase,
        "F_p":                  round(best_F, 6),
        "n_microtrips_selected": len(iloc_seq),
        "total_distance_m":     round(phase_df.iloc[iloc_seq]["distance_m"].sum(), 1),
        "n_trials_run":         n_run,
        "converged":            converged,
        **{f"achieved_{k}": round(v, 4) for k, v in stats.items()},
    })

report_df = pd.DataFrame(report_rows)
report_df.to_csv(SYNTHESIS_DIR / "selection_report.csv", index=False)

print("\nSelection summary:")
print(report_df[["phase", "F_p", "n_microtrips_selected", "total_distance_m", "converged"]].to_string(index=False))
# %%
