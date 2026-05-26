"""Drive cycle synthesis subpackage.

Public API
----------
synthesize(mc, assignments, config)
    End-to-end synthesis pipeline: Markov chain construction → per-group
    target computation → stochastic microtrip selection → cycle assembly.
    Returns a 1-Hz speed–time DataFrame.

Submodules
----------
markov
    State discretisation (``discretize_states``) and transition matrix
    construction (``build_transition_matrix``, ``frobenius_distance``).
targets
    Per-group kinematic target computation (``compute_targets``).
selection
    Stochastic microtrip selection (``select_microtrips``).
assembly
    Junction smoothing (``smooth_junction``), cycle assembly
    (``assemble_cycle``), and validation (``validate_cycle``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from drive_cycle_calculator.schema import (
    ClusterSynthesisConfig,
    SynthesisConfig,
    WLTPSynthesisConfig,
)
from drive_cycle_calculator.synthesis.assembly import assemble_cycle
from drive_cycle_calculator.synthesis.markov import _compute_markov_distances
from drive_cycle_calculator.synthesis.selection import select_microtrips
from drive_cycle_calculator.synthesis.targets import compute_targets

if TYPE_CHECKING:
    from drive_cycle_calculator.microtrip_collection import MicrotripCollection

__all__ = ["synthesize"]


def synthesize(
    mc: MicrotripCollection,
    assignments: pd.Series,
    config: SynthesisConfig,
) -> pd.DataFrame:
    """Synthesize a representative drive cycle from a persisted MicrotripCollection.

    Orchestrates the full pipeline:

    1. Validates that *mc* is persisted (all microtrips have saved Parquet files).
    2. Merges *assignments* into a working copy of ``mc.summary``.
    3. Derives ``total_duration_s`` and ``idle_fraction`` if absent.
    4. Builds the global Markov transition matrix from all microtrip Parquets
       and computes per-microtrip Frobenius distances.
    5. Computes per-group kinematic targets via ``compute_targets``.
    6. For each group (in sorted order), calls ``select_microtrips`` to find
       the best sequence of microtrips under the configured objective.
    7. Assembles the final cycle with ``assemble_cycle`` and returns it.

    Parameters
    ----------
    mc : MicrotripCollection
        Must satisfy ``mc.is_persisted is True``.  Build it via
        ``MicrotripSegmenter.export_collection()`` then
        ``MicrotripCollection.from_parquets()``.
    assignments : pd.Series
        Group label per microtrip.  Index must align with ``mc.summary.index``.
        Typical sources:

        - WLTP path: ``assign_wltp_phases(mc.summary)``
          (from ``dcc.synthesis.wltp``)
        - Cluster path: ``mc.summary["cluster_id"]``
          (after ``KMeansClusterer.fit`` and saving with ``summary_csv``)

    config : SynthesisConfig
        Either ``WLTPSynthesisConfig`` or ``ClusterSynthesisConfig``.
        Controls Markov binning, selection hyper-parameters, minimum distances,
        and the inter-group idle gap.

    Returns
    -------
    pd.DataFrame
        Columns: ``t_s`` (int), ``speed_kmh`` (float), ``group`` (str).
        One row per second.  Samples between groups are labelled ``"idle"``.

    Raises
    ------
    ValueError
        If ``mc.is_persisted`` is ``False``, or if ``mc.summary`` is missing
        required columns (``path``, ``duration_s``, ``distance_m``,
        ``mean_speed_kmh``).
    """
    if not mc.is_persisted:
        raise ValueError(
            "synthesize() requires a persisted MicrotripCollection. "
            "Call MicrotripSegmenter.export_collection() then "
            "MicrotripCollection.from_parquets() first."
        )

    summary = mc.summary.copy()

    _required = {"path", "duration_s", "distance_m", "mean_speed_kmh"}
    missing = _required - set(summary.columns)
    if missing:
        raise ValueError(
            f"mc.summary is missing required columns: {missing}.  "
            "Re-run MicrotripSegmenter.export_collection() to rebuild the summary."
        )

    summary["_group"] = assignments.reindex(summary.index)
    summary = summary.dropna(subset=["_group"])
    if summary.empty:
        raise ValueError(
            "No microtrips remain after aligning assignments with mc.summary. "
            "Verify that assignments.index matches mc.summary.index."
        )

    if "total_duration_s" not in summary.columns:
        stop = (
            summary["stop_duration_s"]
            if "stop_duration_s" in summary.columns
            else pd.Series(0.0, index=summary.index)
        )
        summary["total_duration_s"] = summary["duration_s"] + stop

    if "idle_fraction" not in summary.columns:
        total = summary["total_duration_s"].replace(0.0, float("nan"))
        stop = (
            summary["stop_duration_s"]
            if "stop_duration_s" in summary.columns
            else pd.Series(0.0, index=summary.index)
        )
        summary["idle_fraction"] = stop / total

    # Build global Markov matrix and per-microtrip Frobenius distances
    paths = [Path(p) for p in summary["path"] if p]
    global_T, dist_map = _compute_markov_distances(paths, config.markov)
    summary["markov_distance"] = summary["path"].map(dist_map).fillna(1.0)

    # Per-group kinematic targets
    group_targets = compute_targets(
        summary, "_group", config.selection.metric_weights
    )

    # Config-specific parameters
    if isinstance(config, WLTPSynthesisConfig):
        def _min_dist(g: str) -> float:
            return config.phase_min_distance_m.get(g, 600.0)
        idle_s = config.inter_phase_idle_s
    else:
        def _min_dist(g: str) -> float:
            return config.cluster_min_distance_m
        idle_s = config.inter_cluster_idle_s

    rng = np.random.default_rng(config.selection.random_seed)
    group_order = sorted(group_targets.keys(), key=str)

    groups_selected: list[tuple[str, list[Path]]] = []
    for group_label in group_order:
        group_cands = summary[summary["_group"] == group_label].copy()
        selected_paths = select_microtrips(
            group_cands,
            str(group_label),
            group_targets[group_label],
            global_T,
            config.selection,
            min_distance_m=_min_dist(str(group_label)),
            markov_lambda=config.markov.markov_lambda,
            rng=rng,
        )
        groups_selected.append((str(group_label), [Path(p) for p in selected_paths]))

    return assemble_cycle(groups_selected, idle_s, config.markov)
