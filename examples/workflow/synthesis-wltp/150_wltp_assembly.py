# %%
"""
WLTP Step 150 — Assemble final cycle, smooth junctions, validate (GTR 15 §6).

Loads the selected microtrip sequences from step 140, reads each microtrip's
speed trace from data/microtrips/, and concatenates them into a single 1-Hz
speed-time trace:
  - Within each phase: linear ramp at junctions where Δv > 2 km/h (max 3 s)
  - Between phases: 20-s idle segment (configurable via inter_phase_idle_s)

The assembled cycle is validated against phase_targets.csv tolerances. If any
phase fails, re-run 140_wltp_selection.py with higher n_trials or lower
f_threshold.

Outputs:
  data/synthesis/final_cycle.csv      — t_s, speed_kmh, phase (1-Hz)
  data/synthesis/final_cycle.png      — speed–time plot with phase bands
  data/synthesis/validation_report.md — pass/fail per metric per phase
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[3]
_cfg = json.loads((Path(__file__).parent.parent / "config.json").read_text())
_wltp = json.loads((Path(__file__).parent.parent / "config_wltp.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"
SYNTHESIS_DIR = OUTPUT_DIR / "synthesis"
SELECTED_DIR = SYNTHESIS_DIR / "selected"

PHASE_ORDER = ["Low", "Med", "High", "xHigh"]
PHASE_COLOURS = {"Low": "#4dac26", "Med": "#f1b619", "High": "#d01c8b", "xHigh": "#0571b0"}
IDLE_S = int(_wltp["inter_phase_idle_s"])

# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_speed_trace(filename: str) -> np.ndarray:
    """Full 1-Hz speed array (km/h) for one microtrip parquet (motion + stop)."""
    p = MICROTRIPS_DIR / filename
    df = pd.read_parquet(p)
    col = "smooth_speed_kmh" if "smooth_speed_kmh" in df.columns else "speed_kmh"
    return df[col].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)


def _smooth_junction(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return a linear bridge between end of a and start of b if Δv > 2 km/h."""
    v_end = float(a[-1]) if len(a) else 0.0
    v_start = float(b[0]) if len(b) else 0.0
    if abs(v_end - v_start) <= 2.0:
        return np.empty(0, dtype=float)
    n = min(math.ceil(abs(v_end - v_start)), 3)  # ≤ 3 s at ≤ 1 km/h per step
    return np.linspace(v_end, v_start, n + 2)[1:-1]


def _phase_stats(v: np.ndarray) -> dict:
    """Kinematic statistics from a 1-Hz speed array (km/h)."""
    if len(v) == 0:
        return {}
    v_ms = v / 3.6
    acc = np.diff(v_ms, prepend=v_ms[0])  # m/s² at 1 Hz
    dist_m = float(np.trapezoid(v_ms, dx=1.0))
    motion = v > 0
    return {
        "duration_s": len(v),
        "distance_m": round(dist_m, 1),
        "mean_speed_kmh": round(float(v[motion].mean()), 3) if motion.any() else 0.0,
        "idle_fraction": round(float((~motion).sum()) / len(v), 4),
        "speed_95th_kmh": round(float(np.percentile(v, 95)), 3),
        "rpa": round(float(np.sum(v_ms * acc * (acc > 0)) / dist_m), 5)
        if dist_m > 0
        else float("nan"),
    }


# ── Load targets ───────────────────────────────────────────────────────────────
targets_path = SYNTHESIS_DIR / "phase_targets.csv"
if not targets_path.exists():
    print("phase_targets.csv not found. Run 130_wltp_phase_targets.py first.")
    raise SystemExit(1)

targets_df = pd.read_csv(targets_path, index_col="phase")

# ── Assemble ───────────────────────────────────────────────────────────────────
phase_segments: list[dict] = []

for phase in PHASE_ORDER:
    seq_path = SELECTED_DIR / f"phase_{phase}_sequence.csv"
    if not seq_path.exists():
        continue

    seq_df = pd.read_csv(seq_path)
    traces: list[np.ndarray] = []

    for fname in seq_df["filename"]:
        trace = _load_speed_trace(fname)
        if traces and len(traces[-1]) and len(trace):
            bridge = _smooth_junction(traces[-1], trace)
            if len(bridge):
                traces.append(bridge)
        traces.append(trace)

    phase_v = np.concatenate(traces) if traces else np.empty(0, dtype=float)
    phase_segments.append({"phase": phase, "v": phase_v})
    print(
        f"  {phase}: {len(seq_df)} microtrips -> {len(phase_v)} samples "
        f"({len(phase_v) / 60:.1f} min)"
    )

if not phase_segments:
    print("No selected sequences found. Run 140_wltp_selection.py first.")
    raise SystemExit(1)

# Concatenate with inter-phase idle
v_parts: list[np.ndarray] = []
phase_spans: list[tuple[int, int, str]] = []  # (start, end, phase)
cursor = 0

for i, seg in enumerate(phase_segments):
    start = cursor
    v_parts.append(seg["v"])
    cursor += len(seg["v"])
    phase_spans.append((start, cursor, seg["phase"]))
    if i < len(phase_segments) - 1:
        v_parts.append(np.zeros(IDLE_S, dtype=float))
        cursor += IDLE_S

final_v = np.concatenate(v_parts)
final_t = np.arange(len(final_v))

# Build annotated CSV
phase_col = np.full(len(final_v), "idle", dtype=object)
for start, end, ph in phase_spans:
    phase_col[start:end] = ph

cycle_df = pd.DataFrame({"t_s": final_t, "speed_kmh": final_v, "phase": phase_col})
cycle_df.to_csv(SYNTHESIS_DIR / "final_cycle.csv", index=False)
print(
    f"\nSaved: {SYNTHESIS_DIR / 'final_cycle.csv'}  "
    f"({len(final_v)} s = {len(final_v) / 60:.1f} min)"
)

# ── Validate ───────────────────────────────────────────────────────────────────
METRICS_CHECKED = ["mean_speed_kmh", "rpa", "idle_fraction", "speed_95th_kmh"]

validation: list[dict] = []
all_pass = True

for start, end, phase in phase_spans:
    if phase not in targets_df.index:
        continue

    achieved = _phase_stats(final_v[start:end])
    tgt = targets_df.loc[phase]
    checks: list[dict] = []

    for m in METRICS_CHECKED:
        if m not in achieved:
            continue
        hat = achieved[m]
        lo = float(tgt.get(f"{m}_tol_lo", float("-inf")))
        hi = float(tgt.get(f"{m}_tol_hi", float("inf")))
        ok = bool(lo <= hat <= hi)
        if not ok:
            all_pass = False
        checks.append(
            {
                "metric": m,
                "target": float(tgt[m]),
                "achieved": hat,
                "lo": lo,
                "hi": hi,
                "pass": ok,
            }
        )

    validation.append({"phase": phase, "achieved": achieved, "checks": checks})

# Markdown report
md = ["# WLTP Synthesis — Validation Report\n"]
for v in validation:
    ph = v["phase"]
    a = v["achieved"]
    md.append(f"## Phase: {ph}")
    md.append(
        f"- Duration: {a.get('duration_s', '?')} s  |  Distance: {a.get('distance_m', '?')} m\n"
    )
    md.append("| Metric | Target | Tol lo | Tol hi | Achieved | Pass |")
    md.append("|---|---|---|---|---|---|")
    for c in v["checks"]:
        tick = "✓" if c["pass"] else "✗"
        md.append(
            f"| {c['metric']} | {c['target']:.4f} | {c['lo']:.4f} | {c['hi']:.4f} "
            f"| {c['achieved']:.4f} | {tick} |"
        )
    md.append("")

md.append(f"\n**Overall: {'PASS ✓' if all_pass else 'FAIL ✗ — re-run 140_wltp_selection.py'}**")
(SYNTHESIS_DIR / "validation_report.md").write_text("\n".join(md), encoding="utf-8")
print(f"Saved: {SYNTHESIS_DIR / 'validation_report.md'}  ({'PASS' if all_pass else 'FAIL'})")

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 4))

for start, end, phase in phase_spans:
    colour = PHASE_COLOURS.get(phase, "#aaa")
    ax.axvspan(start, end, alpha=0.12, color=colour, lw=0)
    ax.text(
        (start + end) / 2,
        final_v.max() * 0.92,
        phase,
        ha="center",
        va="bottom",
        fontsize=8,
        color=colour,
        fontweight="bold",
    )

ax.plot(final_t, final_v, lw=0.8, color="#222")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Speed (km/h)")
ax.set_title("Synthesised WLTP Drive Cycle")
ax.set_xlim(0, len(final_v))
ax.set_ylim(0)
plt.tight_layout()
fig.savefig(SYNTHESIS_DIR / "final_cycle.png", dpi=150)
print(f"Saved: {SYNTHESIS_DIR / 'final_cycle.png'}")
plt.show()
# %%
