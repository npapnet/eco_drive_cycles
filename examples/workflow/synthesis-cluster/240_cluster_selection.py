# %%
"""
Cluster Synthesis Step 240 — Stochastic microtrip selection per cluster.

For each cluster independently, assembles a sequence of microtrips (with
replacement if the pool is small) guided by two objectives:

  1. Markov fidelity — microtrips are drawn with probability proportional to
     exp(−λ · D(T_i, T)), where D is the Frobenius distance computed in step 220.
  2. Kinematic match — the assembled sequence's weighted-mean statistics
     (mean speed, RPA, idle fraction, v_95) should match the cluster targets τ_c
     from step 230 within tolerance.

Search strategy: repeat N_trials random assemblies, keep the sequence with the
lowest objective F_c; break early when F_c < f_threshold.

Outputs:
  data/synthesis-cluster/selected/cluster_<id>_sequence.csv  — one row per selected microtrip
  data/synthesis-cluster/selection_report.csv                — F_c and convergence per cluster

Next step: 250_cluster_assembly.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg  = json.loads((Path(__file__).parent.parent / "config.json").read_text())
_syn  = json.loads((Path(__file__).parent.parent / "config_syn_cluster.json").read_text())

OUTPUT_DIR    = ROOTDIR / _cfg["output_dir"]
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis-cluster"
SELECTED_DIR  = SYNTHESIS_DIR / "selected"

LAM            = float(_syn["markov_lambda"])
N_TRIALS       = int(_syn["n_trials"])
F_THRESH       = float(_syn["f_threshold"])
MAX_REUSE      = float(_syn["max_reuse_fraction"])
MIN_DIST_M     = float(_syn["cluster_min_distance_m"])
METRIC_WEIGHTS = _syn["metric_weights"]
RNG_SEED       = int(_syn.get("random_seed", 42))

# ── Load inputs ────────────────────────────────────────────────────────────────
for path, label in [
    (SYNTHESIS_DIR / "microtrips_clustered.csv",              "microtrips_clustered.csv"),
    (SYNTHESIS_DIR / "markov" / "microtrip_distances.csv",    "microtrip_distances.csv"),
    (SYNTHESIS_DIR / "cluster_targets.csv",                   "cluster_targets.csv"),
]:
    if not path.exists():
        print(f"{label} not found at {path}.")
        raise SystemExit(1)

clustered_df = pd.read_csv(SYNTHESIS_DIR / "microtrips_clustered.csv")
dist_df      = pd.read_csv(SYNTHESIS_DIR / "markov" / "microtrip_distances.csv")
targets_df   = pd.read_csv(SYNTHESIS_DIR / "cluster_targets.csv", index_col="cluster_id")
# Ensure index is string (matches cluster_id dtype in clustered_df)
targets_df.index = targets_df.index.astype(str)

if "total_duration_s" not in clustered_df.columns:
    clustered_df["total_duration_s"] = clustered_df["duration_s"] + clustered_df["stop_duration_s"]
if "idle_fraction" not in clustered_df.columns:
    clustered_df["idle_fraction"] = (
        clustered_df["stop_duration_s"]
        / clustered_df["total_duration_s"].replace(0.0, float("nan"))
    )

clustered_df = clustered_df.merge(
    dist_df[["filename", "markov_distance"]], on="filename", how="left"
)
clustered_df["markov_distance"] = clustered_df["markov_distance"].fillna(1.0)

cluster_order = sorted(clustered_df["cluster_id"].unique(), key=lambda x: str(x))

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

    dur = seq_df["total_duration_s"]
    return {
        "mean_speed_kmh": float((seq_df["mean_speed_kmh"] * dur).sum() / s_dur),
        "rpa":            rpa,
        "idle_fraction":  float((seq_df["idle_fraction"].fillna(0) * dur).sum() / s_dur),
        "speed_95th_kmh": float((seq_df["speed_95th_kmh"] * dur).sum() / s_dur),
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

def _select_cluster(
    cluster_df: pd.DataFrame,
    targets: dict,
    rng: np.random.Generator,
) -> tuple[list[int], float, int, bool]:
    """Return (iloc_indices, best_F, n_trials_run, converged)."""
    n = len(cluster_df)
    dists  = cluster_df["markov_distance"].fillna(1.0).values
    base_w = np.exp(-LAM * dists)
    base_w /= base_w.sum()

    durations = cluster_df["total_duration_s"].values
    distances = cluster_df["distance_m"].values

    best_seq: list[int] = []
    best_F = float("inf")

    for trial in range(N_TRIALS):
        seq: list[int] = []
        total_dist = 0.0
        total_dur  = 0.0
        usage_dur  = np.zeros(n, dtype=float)

        while total_dist < MIN_DIST_M:
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

        F = _objective(cluster_df.iloc[seq], targets)
        if F < best_F:
            best_F   = F
            best_seq = seq[:]
            if F < F_THRESH:
                return best_seq, best_F, trial + 1, True

    return best_seq, best_F, N_TRIALS, False


# ── Run per cluster ────────────────────────────────────────────────────────────

SELECTED_DIR.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(RNG_SEED)
report_rows = []

for cluster in cluster_order:
    cluster_df = clustered_df[clustered_df["cluster_id"] == cluster].reset_index(drop=True)

    if cluster_df.empty:
        print(f"  Cluster {cluster}: no microtrips — skipped.")
        continue
    if str(cluster) not in targets_df.index:
        print(f"  Cluster {cluster}: no target entry — skipped.")
        continue

    targets = targets_df.loc[str(cluster)].to_dict()

    print(f"  Cluster {cluster}: {len(cluster_df)} microtrips, min dist {MIN_DIST_M:.0f} m ...",
          end=" ", flush=True)

    iloc_seq, best_F, n_run, converged = _select_cluster(cluster_df, targets, rng)

    status = "converged" if converged else f"best F={best_F:.5f}"
    print(f"{n_run} trials — {status}")

    out_df = cluster_df.iloc[iloc_seq].copy()
    out_df.insert(0, "sequence_position", range(len(iloc_seq)))
    out_df.to_csv(SELECTED_DIR / f"cluster_{cluster}_sequence.csv", index=False)

    stats = _seq_stats(cluster_df.iloc[iloc_seq])
    report_rows.append({
        "cluster_id":              cluster,
        "F_c":                     round(best_F, 6),
        "n_microtrips_selected":   len(iloc_seq),
        "total_distance_m":        round(cluster_df.iloc[iloc_seq]["distance_m"].sum(), 1),
        "n_trials_run":            n_run,
        "converged":               converged,
        **{f"achieved_{k}": round(v, 4) for k, v in stats.items()},
    })

report_df = pd.DataFrame(report_rows)
report_df.to_csv(SYNTHESIS_DIR / "selection_report.csv", index=False)

print("\nSelection summary:")
cols = ["cluster_id", "F_c", "n_microtrips_selected", "total_distance_m", "converged"]
print(report_df[cols].to_string(index=False))
# %%
