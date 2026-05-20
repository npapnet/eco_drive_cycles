# %%
"""
Cluster Synthesis Step 250 — Assemble final cycle, smooth junctions, validate.

Loads the selected microtrip sequences from step 240, reads each microtrip's
speed trace from data/microtrips/, and concatenates them into a single 1-Hz
speed-time trace:
  - Within each cluster: linear ramp at junctions where Δv > 2 km/h (max 3 s)
  - Between clusters: idle segment of inter_cluster_idle_s seconds

Clusters are assembled in ascending cluster_id order.

The assembled cycle is validated against cluster_targets.csv tolerances.
If any cluster fails, re-run 240_cluster_selection.py with higher n_trials
or lower f_threshold.

Outputs:
  data/synthesis-cluster/final_cycle.csv      — t_s, speed_kmh, cluster_id (1-Hz)
  data/synthesis-cluster/final_cycle.png      — speed–time plot with cluster bands
  data/synthesis-cluster/validation_report.md — pass/fail per metric per cluster
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())
_syn = json.loads((Path(__file__).parent / "config_syn_cluster.json").read_text())

OUTPUT_DIR     = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR  = OUTPUT_DIR / "synthesis-cluster"
SELECTED_DIR   = SYNTHESIS_DIR / "selected"

IDLE_S = int(_syn["inter_cluster_idle_s"])

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_speed_trace(filename: str) -> np.ndarray:
    """Full 1-Hz speed array (km/h) for one microtrip parquet (motion + stop)."""
    p = MICROTRIPS_DIR / filename
    df = pd.read_parquet(p)
    col = "smooth_speed_kmh" if "smooth_speed_kmh" in df.columns else "speed_kmh"
    return df[col].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)


def _smooth_junction(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return a linear bridge between end of a and start of b if Δv > 2 km/h."""
    v_end   = float(a[-1]) if len(a) else 0.0
    v_start = float(b[0])  if len(b) else 0.0
    if abs(v_end - v_start) <= 2.0:
        return np.empty(0, dtype=float)
    n = min(math.ceil(abs(v_end - v_start)), 3)
    return np.linspace(v_end, v_start, n + 2)[1:-1]


def _cluster_stats(v: np.ndarray) -> dict:
    """Kinematic statistics from a 1-Hz speed array (km/h)."""
    if len(v) == 0:
        return {}
    v_ms = v / 3.6
    acc  = np.diff(v_ms, prepend=v_ms[0])
    dist_m = float(np.trapezoid(v_ms, dx=1.0))
    motion = v > 0
    return {
        "duration_s":     len(v),
        "distance_m":     round(dist_m, 1),
        "mean_speed_kmh": round(float(v[motion].mean()), 3) if motion.any() else 0.0,
        "idle_fraction":  round(float((~motion).sum()) / len(v), 4),
        "speed_95th_kmh": round(float(np.percentile(v, 95)), 3),
        "rpa":            round(float(np.sum(v_ms * acc * (acc > 0)) / dist_m), 5)
                          if dist_m > 0 else float("nan"),
    }


# ── Discover available cluster sequences ──────────────────────────────────────
seq_files = sorted(SELECTED_DIR.glob("cluster_*_sequence.csv"))
if not seq_files:
    print(f"No sequence files found in {SELECTED_DIR}. Run 240_cluster_selection.py first.")
    raise SystemExit(1)

# Extract cluster IDs from filenames and sort them
def _cluster_id_from_path(p: Path) -> str:
    # filename: cluster_<id>_sequence.csv
    return p.stem.split("_")[1]

cluster_order = sorted([_cluster_id_from_path(f) for f in seq_files], key=lambda x: str(x))
print(f"Found sequences for clusters: {cluster_order}")

# ── Load targets ───────────────────────────────────────────────────────────────
targets_path = SYNTHESIS_DIR / "cluster_targets.csv"
if not targets_path.exists():
    print(f"cluster_targets.csv not found. Run 230_cluster_targets.py first.")
    raise SystemExit(1)

targets_df = pd.read_csv(targets_path, index_col="cluster_id")
targets_df.index = targets_df.index.astype(str)

# ── Assign colors to clusters from a colormap ─────────────────────────────────
_cmap = cm.get_cmap("tab10", len(cluster_order))
CLUSTER_COLOURS = {c: _cmap(i) for i, c in enumerate(cluster_order)}

# ── Assemble ───────────────────────────────────────────────────────────────────
cluster_segments: list[dict] = []

for cluster in cluster_order:
    seq_path = SELECTED_DIR / f"cluster_{cluster}_sequence.csv"
    seq_df = pd.read_csv(seq_path)
    traces: list[np.ndarray] = []

    for fname in seq_df["filename"]:
        trace = _load_speed_trace(fname)
        if traces and len(traces[-1]) and len(trace):
            bridge = _smooth_junction(traces[-1], trace)
            if len(bridge):
                traces.append(bridge)
        traces.append(trace)

    cluster_v = np.concatenate(traces) if traces else np.empty(0, dtype=float)
    cluster_segments.append({"cluster_id": cluster, "v": cluster_v})
    print(
        f"  Cluster {cluster}: {len(seq_df)} microtrips → "
        f"{len(cluster_v)} samples ({len(cluster_v) / 60:.1f} min)"
    )

# Concatenate with inter-cluster idle
v_parts: list[np.ndarray] = []
cluster_spans: list[tuple[int, int, str]] = []  # (start, end, cluster_id)
cursor = 0

for i, seg in enumerate(cluster_segments):
    start = cursor
    v_parts.append(seg["v"])
    cursor += len(seg["v"])
    cluster_spans.append((start, cursor, seg["cluster_id"]))
    if i < len(cluster_segments) - 1:
        v_parts.append(np.zeros(IDLE_S, dtype=float))
        cursor += IDLE_S

final_v = np.concatenate(v_parts)
final_t = np.arange(len(final_v))

# Build annotated CSV
cluster_col = np.full(len(final_v), "idle", dtype=object)
for start, end, cid in cluster_spans:
    cluster_col[start:end] = cid

cycle_df = pd.DataFrame({"t_s": final_t, "speed_kmh": final_v, "cluster_id": cluster_col})
cycle_df.to_csv(SYNTHESIS_DIR / "final_cycle.csv", index=False)
print(
    f"\nSaved: {SYNTHESIS_DIR / 'final_cycle.csv'}  "
    f"({len(final_v)} s = {len(final_v) / 60:.1f} min)"
)

# ── Validate ───────────────────────────────────────────────────────────────────
METRICS_CHECKED = ["mean_speed_kmh", "rpa", "idle_fraction", "speed_95th_kmh"]

validation: list[dict] = []
all_pass = True

for start, end, cid in cluster_spans:
    if cid not in targets_df.index:
        continue

    achieved = _cluster_stats(final_v[start:end])
    tgt = targets_df.loc[cid]
    checks: list[dict] = []

    for m in METRICS_CHECKED:
        if m not in achieved:
            continue
        hat = achieved[m]
        lo  = float(tgt.get(f"{m}_tol_lo", float("-inf")))
        hi  = float(tgt.get(f"{m}_tol_hi", float("inf")))
        ok  = bool(lo <= hat <= hi)
        if not ok:
            all_pass = False
        checks.append({"metric": m, "target": float(tgt[m]), "achieved": hat,
                        "lo": lo, "hi": hi, "pass": ok})

    validation.append({"cluster_id": cid, "achieved": achieved, "checks": checks})

# Markdown report
md = ["# Cluster Synthesis — Validation Report\n"]
for v in validation:
    cid = v["cluster_id"]
    a   = v["achieved"]
    md.append(f"## Cluster: {cid}")
    md.append(f"- Duration: {a.get('duration_s', '?')} s  |  Distance: {a.get('distance_m', '?')} m\n")
    md.append("| Metric | Target | Tol lo | Tol hi | Achieved | Pass |")
    md.append("|---|---|---|---|---|---|")
    for c in v["checks"]:
        tick = "✓" if c["pass"] else "✗"
        md.append(
            f"| {c['metric']} | {c['target']:.4f} | {c['lo']:.4f} | {c['hi']:.4f} "
            f"| {c['achieved']:.4f} | {tick} |"
        )
    md.append("")

md.append(f"\n**Overall: {'PASS ✓' if all_pass else 'FAIL ✗ — re-run 240_cluster_selection.py'}**")
(SYNTHESIS_DIR / "validation_report.md").write_text("\n".join(md), encoding="utf-8")
print(f"Saved: {SYNTHESIS_DIR / 'validation_report.md'}  ({'PASS' if all_pass else 'FAIL'})")

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 4))

for start, end, cid in cluster_spans:
    colour = CLUSTER_COLOURS.get(cid, "#aaaaaa")
    ax.axvspan(start, end, alpha=0.12, color=colour, lw=0)
    ax.text(
        (start + end) / 2,
        final_v.max() * 0.92,
        f"C{cid}",
        ha="center",
        va="bottom",
        fontsize=8,
        color=colour,
        fontweight="bold",
    )

ax.plot(final_t, final_v, lw=0.8, color="#222")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Speed (km/h)")
ax.set_title("Synthesised Drive Cycle — Cluster-based")
ax.set_xlim(0, len(final_v))
ax.set_ylim(0)
plt.tight_layout()
fig.savefig(SYNTHESIS_DIR / "final_cycle.png", dpi=150)
print(f"Saved: {SYNTHESIS_DIR / 'final_cycle.png'}")
plt.show()
# %%
