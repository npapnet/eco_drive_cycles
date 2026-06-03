"""Markov chain state discretisation and transition matrix construction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from drive_cycle_calculator.schema import MarkovConfig


def _state_label(v_bin: int, a_bin: int, config: MarkovConfig) -> str:
    """Convert integer bin indices to a human-readable state string.

    The label encodes the lower bound of each bin so that states are
    interpretable in the output matrices without needing the config.
    Format: ``v{v_lo:03d}_a{a_lo:+.1f}`` — e.g. ``v030_a+0.2`` means the
    speed bin starting at 30 km/h and the acceleration bin starting at
    +0.2 m/s². The sign prefix on the acceleration makes negative bins
    (deceleration) immediately distinguishable: ``v010_a-0.4``.

    Parameters
    ----------
    v_bin : int
        Zero-based speed bin index.
    a_bin : int
        Zero-based acceleration bin index (0 = most-negative bin).
    config : MarkovConfig
        Binning parameters used to recover the physical lower-bound values.
    """
    v_lo = int(v_bin * config.speed_bin_width_kmh)
    a_lo = -config.acc_range_ms2 + a_bin * config.acc_bin_width_ms2
    return f"v{v_lo:03d}_a{a_lo:+.1f}"


def discretize_states(df: pd.DataFrame, config: MarkovConfig) -> pd.Series:
    """Discretize (speed, acc) samples into state labels.

    Parameters
    ----------
    df : pd.DataFrame
        Sample-level DataFrame with ``smooth_speed_kmh`` (or ``speed_kmh``)
        and ``acc_ms2`` columns.
    config : MarkovConfig
        Binning parameters.

    Returns
    -------
    pd.Series
        String state label per row in *df*, same index as *df*.
    """
    acc_min = -config.acc_range_ms2
    acc_max = config.acc_range_ms2
    n_acc_bins = round((acc_max - acc_min) / config.acc_bin_width_ms2)

    col = "smooth_speed_kmh" if "smooth_speed_kmh" in df.columns else "speed_kmh"
    v = pd.to_numeric(df[col], errors="coerce").fillna(0.0).clip(lower=0.0)
    a = pd.to_numeric(df["acc_ms2"], errors="coerce").fillna(0.0).clip(acc_min, acc_max)

    v_bins = (v / config.speed_bin_width_kmh).astype(int)
    a_bins = ((a - acc_min) / config.acc_bin_width_ms2).clip(upper=n_acc_bins - 1).astype(int)

    labels = [
        _state_label(int(vb), int(ab), config)
        for vb, ab in zip(v_bins, a_bins)
    ]
    return pd.Series(labels, index=df.index, name="state")


def build_transition_matrix(states: pd.Series) -> pd.DataFrame:
    """Build a normalised row-stochastic transition matrix from a state sequence.

    Consecutive pairs within *states* are treated as (from → to) transitions.
    Each row is normalised to sum to 1; rows with no outgoing transitions
    remain all-zero.

    Parameters
    ----------
    states : pd.Series
        Sequence of state label strings from a **single** continuous trajectory
        (one microtrip). Do **not** concatenate multiple microtrips — cross-
        boundary pairs create spurious transitions.

    Returns
    -------
    pd.DataFrame
        Row-stochastic matrix indexed and columned by state labels.
        Empty DataFrame when *states* has fewer than 2 elements.
    """
    if len(states) < 2:
        return pd.DataFrame(dtype=float)

    frm = states.iloc[:-1].values
    to = states.iloc[1:].values
    counts = pd.DataFrame({"from": frm, "to": to})
    count_matrix = counts.groupby(["from", "to"]).size().unstack(fill_value=0)
    return count_matrix.div(count_matrix.sum(axis=1), axis=0).fillna(0.0)


def frobenius_distance(m1: pd.DataFrame, m2: pd.DataFrame) -> float:
    """Normalised Frobenius distance between two transition matrices.

    Only from-states present in *m1* that also appear in *m2* are compared.
    The result is divided by the number of shared from-states so values are
    comparable across microtrips of different length. Returns 1.0 when there
    are no shared from-states.

    Parameters
    ----------
    m1 : pd.DataFrame
        Row-stochastic transition matrix (e.g. a per-microtrip matrix).
    m2 : pd.DataFrame
        Reference row-stochastic matrix (e.g. the global matrix).
    """
    shared_from = m1.index.intersection(m2.index)
    if len(shared_from) == 0:
        return 1.0
    all_to = m1.columns.union(m2.columns)
    sub1 = m1.loc[shared_from].reindex(columns=all_to, fill_value=0.0)
    sub2 = m2.loc[shared_from].reindex(columns=all_to, fill_value=0.0)
    return float(np.linalg.norm(sub1.values - sub2.values, "fro")) / len(shared_from)


def _compute_markov_distances(
    paths: list[Path],
    config: MarkovConfig,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build global T and per-microtrip Frobenius distances.

    Loads each microtrip Parquet, discretises its motion-phase samples, and
    collects all within-microtrip transitions to form the global matrix.
    Returns a mapping ``path_str → markov_distance`` for use in selection.

    Parameters
    ----------
    paths : list[Path]
        Microtrip Parquet paths (from ``mc.summary["path"]``).
    config : MarkovConfig
        Binning and lambda parameters.

    Returns
    -------
    global_T : pd.DataFrame
        Global row-stochastic transition matrix.
    distances : dict[str, float]
        Frobenius distance keyed by path string.  1.0 for microtrips that
        could not be loaded or had fewer than 2 motion samples.
    """
    from drive_cycle_calculator.microtrip import Microtrip

    all_frm: list[str] = []
    all_to: list[str] = []
    per_mt: dict[str, tuple[list[str], list[str]]] = {}

    for p in paths:
        pkey = str(p)
        try:
            mt = Microtrip.from_parquet(Path(p))
            motion = mt.samples
        except Exception:
            per_mt[pkey] = ([], [])
            continue

        if len(motion) < 2:
            per_mt[pkey] = ([], [])
            continue

        states = discretize_states(motion, config)
        frm_list = states.iloc[:-1].tolist()
        to_list = states.iloc[1:].tolist()
        all_frm.extend(frm_list)
        all_to.extend(to_list)
        per_mt[pkey] = (frm_list, to_list)

    if not all_frm:
        global_T: pd.DataFrame = pd.DataFrame(dtype=float)
    else:
        counts = pd.DataFrame({"from": all_frm, "to": all_to})
        count_matrix = counts.groupby(["from", "to"]).size().unstack(fill_value=0)
        global_T = count_matrix.div(count_matrix.sum(axis=1), axis=0).fillna(0.0)

    distances: dict[str, float] = {}
    for pkey, (frm_list, to_list) in per_mt.items():
        if not frm_list:
            distances[pkey] = 1.0
            continue
        mt_counts = (
            pd.DataFrame({"from": frm_list, "to": to_list})
            .groupby(["from", "to"])
            .size()
            .unstack(fill_value=0)
        )
        mt_T = mt_counts.div(mt_counts.sum(axis=1), axis=0).fillna(0.0)
        distances[pkey] = frobenius_distance(mt_T, global_T)

    return global_T, distances
