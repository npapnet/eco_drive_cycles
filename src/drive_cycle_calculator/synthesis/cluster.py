"""Cluster assignment adapter.

Extracts pre-computed cluster labels from a microtrip summary DataFrame
and returns them as a pd.Series for use with ``synthesize()``.  The
clustering algorithm (KMeans, DBSCAN, manual, …) is irrelevant here —
only the label column matters.
"""

from __future__ import annotations

import pandas as pd


def assign_clusters(
    summary: pd.DataFrame,
    cluster_col: str = "cluster_id",
) -> pd.Series:
    """Read cluster assignments already present in *summary*.

    Parameters
    ----------
    summary : pd.DataFrame
        Must contain *cluster_col*.  Typically ``mc.summary`` after loading
        a clustered CSV via
        ``MicrotripCollection.from_parquets(..., summary_csv=clustered_csv)``.
    cluster_col : str, optional
        Name of the column holding cluster labels.  Defaults to
        ``"cluster_id"``.

    Returns
    -------
    pd.Series
        Index aligned to *summary*.  Values are cluster labels cast to
        ``str`` so they are source-agnostic (integer KMeans labels, string
        DBSCAN labels, or manual names are all handled uniformly).

    Raises
    ------
    KeyError
        If *cluster_col* is absent from *summary*.
    """
    if cluster_col not in summary.columns:
        raise KeyError(
            f"Column '{cluster_col}' not found in summary. "
            "Run a clustering step (e.g. KMeansClusterer.fit) and save the "
            "result via summary_csv before calling assign_clusters()."
        )
    return summary[cluster_col].astype(str)
