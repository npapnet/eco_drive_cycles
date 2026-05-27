"""WLTP phase assignment adapter.

Classifies microtrips into the four WLTP phases (GTR 15 §2.1) based on
each microtrip's maximum speed.  The result is a pd.Series of group labels
suitable for passing directly to ``synthesize()``.
"""

from __future__ import annotations

import pandas as pd

# GTR 15 §2.1 — lower bound exclusive, upper inclusive.
# Order matters: the first matching interval wins.
WLTP_PHASE_BOUNDS: dict[str, tuple[float, float]] = {
    "Low": (0.0, 56.5),
    "Med": (56.5, 76.6),
    "High": (76.6, 97.4),
    "xHigh": (97.4, float("inf")),
}


def assign_wltp_phases(summary: pd.DataFrame) -> pd.Series:
    """Classify each microtrip into a WLTP phase based on ``max_speed_kmh``.

    Parameters
    ----------
    summary : pd.DataFrame
        Must contain a ``max_speed_kmh`` column.  Typically ``mc.summary``.

    Returns
    -------
    pd.Series
        Index aligned to *summary*.  Values in ``{"Low", "Med", "High",
        "xHigh"}``.  A microtrip with ``max_speed_kmh == 0`` is classified
        as ``"Low"`` (the edge case at the bottom of the first interval).

    Raises
    ------
    KeyError
        If ``max_speed_kmh`` is absent from *summary*.
    """
    if "max_speed_kmh" not in summary.columns:
        raise KeyError(
            "'max_speed_kmh' column is required for WLTP phase assignment. "
            "Rebuild the microtrip summary via MicrotripSegmenter.export_collection()."
        )

    def _assign(v: float) -> str:
        for label, (lo, hi) in WLTP_PHASE_BOUNDS.items():
            if lo < v <= hi:
                return label
        return "Low"  # v == 0.0: below the low bound of every interval

    return summary["max_speed_kmh"].apply(_assign)
