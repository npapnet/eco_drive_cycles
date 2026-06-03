# %%
"""
Cluster Synthesis Step 220 — Build global Markov transition matrix.

Loads every microtrip parquet, discretises (smooth_speed_kmh, acc_ms2) into a
coarse (v, a) state space, and builds:
  1. Global transition probability matrix T across all microtrips
  2. Per-microtrip Frobenius distance D(T_i, T) — used as the Markov similarity
     signal in the stochastic selection step (240)

State encoding (coarse binning, recommended for < 400 microtrips):
  v bins : 10 km/h wide starting at 0
  a bins : 0.2 m/s² wide, range ±1.5 m/s² (values outside are clamped)

Outputs:
  data/synthesis-cluster/markov/global_matrix.csv       — T[from_state, to_state]
  data/synthesis-cluster/markov/microtrip_distances.csv — filename, markov_distance

Next step: 240_cluster_selection.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg  = json.loads((Path(__file__).parent.parent / "config.json").read_text())
_syn  = json.loads((Path(__file__).parent.parent / "config_syn_cluster.json").read_text())

OUTPUT_DIR     = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR  = OUTPUT_DIR / "synthesis-cluster"
MARKOV_DIR     = SYNTHESIS_DIR / "markov"

SPEED_BIN  = float(_syn["speed_bin_width_kmh"])
ACC_BIN    = float(_syn["acc_bin_width_ms2"])
ACC_MIN    = -float(_syn["acc_range_ms2"])
ACC_MAX    =  float(_syn["acc_range_ms2"])
N_ACC_BINS = round((ACC_MAX - ACC_MIN) / ACC_BIN)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _state_label(v_bin: int, a_bin: int) -> str:
    v_lo = int(v_bin * SPEED_BIN)
    a_lo = ACC_MIN + a_bin * ACC_BIN
    return f"v{v_lo:03d}_a{a_lo:+.1f}"


def _encode_states(motion: pd.DataFrame) -> list[str]:
    col = "smooth_speed_kmh" if "smooth_speed_kmh" in motion.columns else "speed_kmh"
    v = motion[col].fillna(0.0).clip(lower=0.0)
    a = motion["acc_ms2"].fillna(0.0).clip(ACC_MIN, ACC_MAX)
    v_bins = (v / SPEED_BIN).astype(int)
    a_bins = ((a - ACC_MIN) / ACC_BIN).clip(upper=N_ACC_BINS - 1).astype(int)
    return [_state_label(int(vb), int(ab)) for vb, ab in zip(v_bins, a_bins)]


def _frobenius_distance(mt_T: pd.DataFrame, global_T: pd.DataFrame) -> float:
    """Normalised Frobenius distance between a microtrip sub-matrix and global T."""
    shared_from = mt_T.index.intersection(global_T.index)
    if len(shared_from) == 0:
        return 1.0
    all_to = mt_T.columns.union(global_T.columns)
    mt_sub = mt_T.loc[shared_from].reindex(columns=all_to, fill_value=0.0)
    g_sub  = global_T.loc[shared_from].reindex(columns=all_to, fill_value=0.0)
    return float(np.linalg.norm(mt_sub.values - g_sub.values, "fro")) / len(shared_from)


# ── Load clustered summary ─────────────────────────────────────────────────────
clustered_path = SYNTHESIS_DIR / "microtrips_clustered.csv"
if not clustered_path.exists():
    print("microtrips_clustered.csv not found. Run 210_cluster_assignment.py first.")
    raise SystemExit(1)

clustered_df = pd.read_csv(clustered_path)
print(f"Building Markov chain from {len(clustered_df)} microtrips ...")

# ── First pass: collect all transitions ───────────────────────────────────────
all_from: list[str] = []
all_to:   list[str] = []
per_mt: dict[str, tuple[list[str], list[str]]] = {}

for _, row in clustered_df.iterrows():
    fpath = MICROTRIPS_DIR / row["filename"]
    if not fpath.exists():
        print(f"  WARNING: missing parquet {fpath.name} — skipped")
        per_mt[row["filename"]] = ([], [])
        continue
    try:
        df = pd.read_parquet(fpath)
    except Exception as exc:
        print(f"  WARNING: failed to read {fpath.name}: {exc} — skipped")
        per_mt[row["filename"]] = ([], [])
        continue

    motion = df[~df["stop_phase"]]
    if len(motion) < 2:
        per_mt[row["filename"]] = ([], [])
        continue

    states = _encode_states(motion)
    frm, to = states[:-1], states[1:]
    all_from.extend(frm)
    all_to.extend(to)
    per_mt[row["filename"]] = (frm, to)

print(f"Collected {len(all_from):,} transitions.")

# ── Build global T ─────────────────────────────────────────────────────────────
counts = pd.DataFrame({"from": all_from, "to": all_to})
count_matrix = counts.groupby(["from", "to"]).size().unstack(fill_value=0)
T = count_matrix.div(count_matrix.sum(axis=1), axis=0).fillna(0.0)

n_states  = len(T)
zero_rows = int((T == 0.0).all(axis=1).sum())
print(f"Global T: {n_states} states, {zero_rows} zero rows ({100*zero_rows/max(n_states,1):.0f}%)")
if zero_rows / max(n_states, 1) > 0.5:
    print(
        "  WARNING: > 50% zero rows - consider wider bins "
        "(speed_bin_width_kmh in config_syn_cluster.json)"
    )

MARKOV_DIR.mkdir(parents=True, exist_ok=True)
T.to_csv(MARKOV_DIR / "global_matrix.csv")
print(f"Saved: {MARKOV_DIR / 'global_matrix.csv'}")

# ── Second pass: per-microtrip Frobenius distance ─────────────────────────────
dist_rows = []
for fname, (frm, to) in per_mt.items():
    if not frm:
        dist_rows.append({"filename": fname, "markov_distance": 1.0, "n_transitions": 0})
        continue

    mt_counts = (
        pd.DataFrame({"from": frm, "to": to})
        .groupby(["from", "to"])
        .size()
        .unstack(fill_value=0)
    )
    mt_T = mt_counts.div(mt_counts.sum(axis=1), axis=0).fillna(0.0)
    d = _frobenius_distance(mt_T, T)
    dist_rows.append({"filename": fname, "markov_distance": round(d, 6), "n_transitions": len(frm)})

dist_df = pd.DataFrame(dist_rows)
dist_df.to_csv(MARKOV_DIR / "microtrip_distances.csv", index=False)
print(f"Saved: {MARKOV_DIR / 'microtrip_distances.csv'}")

print("\nMarkov distance distribution:")
print(dist_df["markov_distance"].describe().round(4).to_string())
# %%
