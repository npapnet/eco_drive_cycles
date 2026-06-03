"""Stochastic microtrip selection per group (GTR 15 §5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from drive_cycle_calculator.schema import SynthesisSelectionConfig


def _seq_stats(seq_df: pd.DataFrame) -> dict[str, float]:
    """Compute weighted-mean kinematic statistics for a microtrip sequence.

    Mirrors the objective-metric computation in the workflow scripts.
    Returns an empty dict when total duration or distance is zero (degenerate
    sequences produce an infinite objective via the caller).

    All means are weighted by ``total_duration_s`` except RPA, which is
    distance-weighted (energy-consistent per GTR 15 §4).

    Parameters
    ----------
    seq_df : pd.DataFrame
        Rows from the candidates DataFrame corresponding to a proposed
        sequence.  Must have ``total_duration_s``, ``distance_m``,
        ``mean_speed_kmh``, ``idle_fraction`` columns.  ``rpa`` and
        ``speed_95th_kmh`` are optional.
    """
    s_dur = float(seq_df["total_duration_s"].sum())
    s_dist = float(seq_df["distance_m"].sum())
    if s_dur == 0 or s_dist == 0:
        return {}

    dur = seq_df["total_duration_s"]

    if "rpa" in seq_df.columns:
        rpa_ok = seq_df[seq_df["rpa"].notna() & (seq_df["distance_m"] > 0)]
        rpa: float = (
            float(
                (rpa_ok["rpa"] * rpa_ok["distance_m"]).sum()
                / rpa_ok["distance_m"].sum()
            )
            if len(rpa_ok) > 0
            else 0.0
        )
    else:
        rpa = 0.0

    result: dict[str, float] = {
        "mean_speed_kmh": float((seq_df["mean_speed_kmh"] * dur).sum() / s_dur),
        "rpa": rpa,
        "idle_fraction": float(
            (seq_df["idle_fraction"].fillna(0.0) * dur).sum() / s_dur
        ),
    }
    if "speed_95th_kmh" in seq_df.columns:
        result["speed_95th_kmh"] = float(
            (seq_df["speed_95th_kmh"] * dur).sum() / s_dur
        )
    return result


def _objective(
    seq_df: pd.DataFrame,
    target: dict[str, float],
    metric_weights: dict[str, float],
) -> float:
    """Weighted relative squared error between sequence statistics and targets.

    The objective is:

        F = Σ_m  w_m · ((ĥ_m − τ_m) / τ_m)²

    where ``ĥ_m`` is the achieved value, ``τ_m`` the target, and ``w_m``
    the weight for metric ``m``.  Metrics with a zero or missing target are
    skipped.  Returns ``inf`` for degenerate sequences.

    Parameters
    ----------
    seq_df : pd.DataFrame
        Proposed microtrip sequence (rows from candidates).
    target : dict[str, float]
        Target values from ``compute_targets``.
    metric_weights : dict[str, float]
        Per-metric weights from ``SynthesisSelectionConfig.metric_weights``.
    """
    stats = _seq_stats(seq_df)
    if not stats:
        return float("inf")
    F = 0.0
    for metric, hat in stats.items():
        tau = target.get(metric)
        w = metric_weights.get(metric, 1.0)
        if tau and tau != 0:
            F += w * ((hat - tau) / tau) ** 2
    return F


def select_microtrips(
    candidates: pd.DataFrame,
    group: str,
    target: dict[str, float],
    global_matrix: pd.DataFrame,
    config: SynthesisSelectionConfig,
    min_distance_m: float = 600.0,
    markov_lambda: float = 1.0,
    rng: np.random.Generator | None = None,
) -> list[str]:
    """Stochastic selection of microtrips for one group.

    Runs ``config.n_trials`` random assemblies and returns the sequence with
    the lowest objective ``F``.  Stops early when ``F < config.f_threshold``.

    **Sampling weights** are proportional to ``exp(−λ · D_i)`` where ``D_i``
    is the pre-computed Frobenius distance stored in the ``markov_distance``
    column of *candidates*.  Microtrips that are missing a distance value
    receive ``D_i = 1.0`` (lowest priority).

    **Reuse control**: within each trial, any microtrip whose share of total
    accumulated duration exceeds ``config.max_reuse_fraction`` is temporarily
    zeroed out to prevent a single dominant microtrip.  If all candidates are
    suppressed the base weights are restored for that draw.

    Parameters
    ----------
    candidates : pd.DataFrame
        Subset of ``mc.summary`` for this group. Must have ``path``,
        ``distance_m``, ``total_duration_s`` (or ``duration_s`` +
        ``stop_duration_s``), ``mean_speed_kmh``, ``idle_fraction`` columns.
        A ``markov_distance`` column is expected but not required — missing
        values default to 1.0.
    group : str
        Group label used in error messages.
    target : dict[str, float]
        Kinematic targets from ``compute_targets``.
    global_matrix : pd.DataFrame
        Global transition matrix (retained for API completeness; Frobenius
        distances are read from the ``markov_distance`` column of *candidates*
        rather than recomputed here).
    config : SynthesisSelectionConfig
        Selection hyper-parameters.
    min_distance_m : float
        Minimum total distance (m) the assembled sequence must cover before
        the trial is scored.
    markov_lambda : float
        Exponential decay rate for Markov-distance sampling weights
        (``λ`` in ``exp(−λ · D)``).  Comes from ``MarkovConfig.markov_lambda``.
    rng : np.random.Generator, optional
        Random number generator.  Created from ``config.random_seed`` when
        not supplied.

    Returns
    -------
    list[str]
        Ordered parquet path strings for the best-found microtrip sequence.

    Raises
    ------
    ValueError
        If *candidates* is empty or has no ``path`` column.
    """
    if candidates.empty:
        raise ValueError(f"No candidates for group {group!r}")
    if "path" not in candidates.columns:
        raise ValueError(
            f"candidates DataFrame has no 'path' column for group {group!r}"
        )

    if rng is None:
        rng = np.random.default_rng(config.random_seed)

    cands = candidates.reset_index(drop=True).copy()

    if "total_duration_s" not in cands.columns:
        stop = (
            cands["stop_duration_s"]
            if "stop_duration_s" in cands.columns
            else pd.Series(0.0, index=cands.index)
        )
        cands["total_duration_s"] = cands["duration_s"] + stop

    if "idle_fraction" not in cands.columns:
        total = cands["total_duration_s"].replace(0.0, float("nan"))
        stop = (
            cands["stop_duration_s"]
            if "stop_duration_s" in cands.columns
            else pd.Series(0.0, index=cands.index)
        )
        cands["idle_fraction"] = stop / total

    n = len(cands)
    dists = cands.get("markov_distance", pd.Series(1.0, index=cands.index)).fillna(1.0).values
    base_w = np.exp(-markov_lambda * dists)
    base_w /= base_w.sum()

    durations = cands["total_duration_s"].values
    distances = cands["distance_m"].values

    best_seq: list[int] = []
    best_F = float("inf")

    for _ in range(config.n_trials):
        seq: list[int] = []
        total_dist = 0.0
        total_dur = 0.0
        usage_dur = np.zeros(n, dtype=float)

        while total_dist < min_distance_m:
            w = base_w.copy()
            if total_dur > 0:
                w[usage_dur / total_dur > config.max_reuse_fraction] = 0.0
                if w.sum() == 0.0:
                    w = base_w.copy()
            w /= w.sum()

            chosen = int(rng.choice(n, p=w))
            seq.append(chosen)
            total_dist += distances[chosen]
            total_dur += durations[chosen]
            usage_dur[chosen] += durations[chosen]

        F = _objective(cands.iloc[seq], target, config.metric_weights)
        if F < best_F:
            best_F = F
            best_seq = seq[:]
            if F < config.f_threshold:
                break

    return [str(cands.iloc[i]["path"]) for i in best_seq]
