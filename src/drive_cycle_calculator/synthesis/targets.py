"""Per-group kinematic target computation for synthesis."""

from __future__ import annotations

import pandas as pd


def compute_targets(
    summary: pd.DataFrame,
    group_col: str,
    metric_weights: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Compute duration-weighted kinematic targets per group.

    Targets are the reference statistics that the stochastic selection step
    (GTR 15 §5) tries to reproduce.  Four metrics are computed:

    - ``mean_speed_kmh`` — duration-weighted mean of per-microtrip mean speed.
    - ``rpa``            — distance-weighted mean RPA (energy-consistent per
                           GTR 15 §4; microtrips with NaN or zero distance are
                           excluded from the RPA average).
    - ``idle_fraction``  — duration-weighted mean of stop time / total time.
    - ``speed_95th_kmh`` — duration-weighted mean of per-microtrip 95th-
                           percentile speed.

    Parameters
    ----------
    summary : pd.DataFrame
        Microtrip summary with at least ``duration_s``, ``distance_m``,
        ``mean_speed_kmh`` columns.  ``stop_duration_s`` is used to derive
        ``total_duration_s`` and ``idle_fraction`` when those columns are
        absent.  ``rpa`` and ``speed_95th_kmh`` are optional — missing columns
        produce ``nan`` targets for those metrics.
    group_col : str
        Column that partitions microtrips into groups (e.g. ``"cluster_id"``
        or ``"phase"``).
    metric_weights : dict[str, float]
        Metric weights from ``SynthesisSelectionConfig``.  Passed through for
        API consistency; targets are always computed for the full standard set
        regardless of which metrics are weighted.

    Returns
    -------
    dict[str, dict[str, float]]
        Maps each group label to a dict of metric targets:
        ``{"mean_speed_kmh": …, "rpa": …, "idle_fraction": …,
        "speed_95th_kmh": …}``.
    """
    df = summary.copy()

    if "total_duration_s" not in df.columns:
        stop = df["stop_duration_s"] if "stop_duration_s" in df.columns else pd.Series(
            0.0, index=df.index
        )
        df["total_duration_s"] = df["duration_s"] + stop

    if "idle_fraction" not in df.columns:
        total = df["total_duration_s"].replace(0.0, float("nan"))
        stop = df["stop_duration_s"] if "stop_duration_s" in df.columns else pd.Series(
            0.0, index=df.index
        )
        df["idle_fraction"] = stop / total

    targets: dict[str, dict[str, float]] = {}

    for group, grp in df.groupby(group_col):
        w_dur = grp["total_duration_s"]
        s_dur = float(w_dur.sum())

        if "rpa" in grp.columns:
            rpa_ok = grp[grp["rpa"].notna() & (grp["distance_m"] > 0)]
            rpa: float = (
                float(
                    (rpa_ok["rpa"] * rpa_ok["distance_m"]).sum()
                    / rpa_ok["distance_m"].sum()
                )
                if len(rpa_ok) > 0
                else float("nan")
            )
        else:
            rpa = float("nan")

        if s_dur > 0:
            mean_speed = float((grp["mean_speed_kmh"] * w_dur).sum() / s_dur)
            idle_frac = float((grp["idle_fraction"].fillna(0.0) * w_dur).sum() / s_dur)
            v_95: float = (
                float((grp["speed_95th_kmh"] * w_dur).sum() / s_dur)
                if "speed_95th_kmh" in grp.columns
                else float("nan")
            )
        else:
            mean_speed = idle_frac = v_95 = float("nan")

        targets[group] = {
            "mean_speed_kmh": mean_speed,
            "rpa": rpa,
            "idle_fraction": idle_frac,
            "speed_95th_kmh": v_95,
        }

    return targets
