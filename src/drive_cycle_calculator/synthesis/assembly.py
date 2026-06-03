"""Cycle assembly: junction smoothing, concatenation, and validation."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from drive_cycle_calculator.schema import MarkovConfig



def smooth_junction(a: np.ndarray, b: np.ndarray, ramp_s: int = 3) -> np.ndarray:
    """Linear velocity bridge between two adjacent speed traces.

    When the speed at the end of *a* and the start of *b* differ by more than
    2 km/h, a short linear ramp is inserted to avoid an instantaneous velocity
    step.  The ramp length is ``min(ceil(|Δv|), ramp_s)`` samples — at most
    *ramp_s* seconds at 1 Hz — and the endpoints are excluded so the caller
    can concatenate ``[a, bridge, b]`` without duplicating values.

    Returns an empty array when no ramp is needed (|Δv| ≤ 2 km/h), so the
    caller can test ``if len(bridge)`` before appending.

    Parameters
    ----------
    a : np.ndarray
        Speed trace (km/h) ending at the junction.
    b : np.ndarray
        Speed trace (km/h) beginning at the junction.
    ramp_s : int
        Maximum ramp length in samples (seconds at 1 Hz).
    """
    v_end = float(a[-1]) if len(a) else 0.0
    v_start = float(b[0]) if len(b) else 0.0
    if abs(v_end - v_start) <= 2.0:
        return np.empty(0, dtype=float)
    n = min(math.ceil(abs(v_end - v_start)), ramp_s)
    return np.linspace(v_end, v_start, n + 2)[1:-1]


def _load_speed_trace(path: Path) -> np.ndarray:
    """Load the full 1-Hz speed trace (km/h) from a microtrip Parquet.

    Reads both the motion and trailing-stop portions so the assembled cycle
    correctly includes idle time at each microtrip's end.

    Parameters
    ----------
    path : Path
        Microtrip Parquet written by ``Microtrip.to_parquet()``.
    """
    from drive_cycle_calculator.microtrip import Microtrip

    mt = Microtrip.from_parquet(path)
    combined = pd.concat([mt.samples, mt.stop_samples])
    col = "smooth_speed_kmh" if "smooth_speed_kmh" in combined.columns else "speed_kmh"
    return combined[col].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)


def _group_stats(v: np.ndarray) -> dict[str, float]:
    """Kinematic statistics from a 1-Hz speed array (km/h).

    Computes the same metrics used by the validation step so that
    ``validate_cycle`` can compare them against ``compute_targets`` output.
    Returns an empty dict for an empty array.

    Parameters
    ----------
    v : np.ndarray
        1-Hz speed trace in km/h.
    """
    if len(v) == 0:
        return {}
    v_ms = v / 3.6
    acc = np.diff(v_ms, prepend=v_ms[0])
    dist_m = float(np.trapezoid(v_ms, dx=1.0))
    motion = v > 0
    stats: dict[str, float] = {
        "duration_s": float(len(v)),
        "distance_m": round(dist_m, 1),
        "mean_speed_kmh": round(float(v[motion].mean()), 3) if motion.any() else 0.0,
        "idle_fraction": round(float((~motion).sum()) / len(v), 4),
        "speed_95th_kmh": round(float(np.percentile(v, 95)), 3),
        "rpa": (
            round(float(np.sum(v_ms * acc * (acc > 0)) / dist_m), 5)
            if dist_m > 0
            else float("nan")
        ),
    }
    return stats


def assemble_cycle(
    groups: list[tuple[str, list[Path]]],
    idle_s: int,
    config: MarkovConfig,
) -> pd.DataFrame:
    """Assemble a drive cycle from ordered groups of microtrips.

    Within each group, microtrip speed traces are concatenated with linear
    junction smoothing where needed (see ``smooth_junction``).  Between
    groups, a zero-speed idle segment of *idle_s* seconds is inserted.

    The output DataFrame uses the ``group`` column to label each sample with
    its originating group or ``"idle"`` for inter-group gaps.

    Parameters
    ----------
    groups : list[tuple[str, list[Path]]]
        Ordered ``(group_label, [microtrip_paths])`` pairs.  Groups are placed
        in the order given; within each group microtrips are placed in the
        order given.
    idle_s : int
        Duration of the zero-speed idle segment inserted between groups
        (seconds).  Not inserted after the last group.
    config : MarkovConfig
        Markov configuration (retained for API completeness; not used
        internally — speed column selection is handled by ``_load_speed_trace``
        which prefers ``smooth_speed_kmh``).

    Returns
    -------
    pd.DataFrame
        Columns: ``t_s`` (int, 0-based seconds), ``speed_kmh`` (float),
        ``group`` (str).  One row per second.  Empty DataFrame with those
        columns when *groups* is empty.
    """
    group_segments: list[tuple[str, np.ndarray]] = []

    for label, paths in groups:
        traces: list[np.ndarray] = []
        for p in paths:
            trace = _load_speed_trace(Path(p))
            if traces and len(traces[-1]) and len(trace):
                bridge = smooth_junction(traces[-1], trace)
                if len(bridge):
                    traces.append(bridge)
            traces.append(trace)
        group_v = np.concatenate(traces) if traces else np.empty(0, dtype=float)
        group_segments.append((label, group_v))

    if not group_segments:
        return pd.DataFrame(columns=["t_s", "speed_kmh", "group"])

    v_parts: list[np.ndarray] = []
    group_spans: list[tuple[int, int, str]] = []
    cursor = 0

    for i, (label, v) in enumerate(group_segments):
        start = cursor
        v_parts.append(v)
        cursor += len(v)
        group_spans.append((start, cursor, label))
        if i < len(group_segments) - 1:
            v_parts.append(np.zeros(idle_s, dtype=float))
            cursor += idle_s

    final_v = np.concatenate(v_parts)
    group_col = np.full(len(final_v), "idle", dtype=object)
    for start, end, label in group_spans:
        group_col[start:end] = label

    return pd.DataFrame({
        "t_s": np.arange(len(final_v)),
        "speed_kmh": final_v,
        "group": group_col,
    })


def validate_cycle(
    cycle: pd.DataFrame,
    targets: dict[str, dict],
    tolerances: dict[str, float],
) -> dict[str, bool]:
    """Validate the assembled cycle against per-group kinematic targets.

    For each group present in *targets*, extracts the corresponding speed
    trace from *cycle* (using the ``group`` column), computes kinematic
    statistics via ``_group_stats``, and checks each metric against its
    target ± tolerance.

    Parameters
    ----------
    cycle : pd.DataFrame
        Output of ``assemble_cycle``.  Must have ``speed_kmh`` and ``group``
        columns.
    targets : dict[str, dict]
        Per-group kinematic targets from ``compute_targets``.
    tolerances : dict[str, float]
        Relative tolerance per metric key (e.g. ``{"mean_speed_kmh": 0.05}``
        for ±5 %).  Use ``float("inf")`` to accept any value for a metric.
        Metrics not in *tolerances* are skipped.

    Returns
    -------
    dict[str, bool]
        Group label → ``True`` when all checked metrics are within tolerance,
        ``False`` otherwise.  Groups absent from *cycle* are marked ``False``.
    """
    _METRICS = ["mean_speed_kmh", "rpa", "idle_fraction", "speed_95th_kmh"]
    results: dict[str, bool] = {}

    for group_label, group_targets in targets.items():
        mask = cycle["group"] == group_label
        v = cycle.loc[mask, "speed_kmh"].to_numpy(dtype=float)
        achieved = _group_stats(v)
        if not achieved:
            results[group_label] = False
            continue

        all_pass = True
        for m in _METRICS:
            if m not in achieved or m not in group_targets or m not in tolerances:
                continue
            tau = group_targets[m]
            hat = achieved[m]
            tol = tolerances[m]
            if not (abs(hat - tau) <= abs(tau) * tol):
                all_pass = False
                break
        results[group_label] = all_pass

    return results
