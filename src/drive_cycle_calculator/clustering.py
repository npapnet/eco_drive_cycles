from __future__ import annotations

from typing import Protocol

import pandas as pd

# ── Extension point ───────────────────────────────────────────────────────────
# To add a new clustering algorithm, implement the Clusterer Protocol below.
# Each implementation must expose a single ``fit(summary) -> pd.Series`` method
# that returns integer labels aligned with the summary index.
#
# Planned additions (see TODOS.md — Backlog P2):
#   - DBSCANClusterer   — density-based, auto-determines cluster count
#   - AgglomerativeClusterer — hierarchical, useful for small fleets
# ─────────────────────────────────────────────────────────────────────────────


class Clusterer(Protocol):
    """Protocol for microtrip clustering algorithms.

    Any callable object with a ``fit(summary) -> pd.Series`` signature
    satisfies this protocol.  The returned Series has ``index = summary.index``
    and integer group labels as values.
    """

    def fit(self, summary: pd.DataFrame) -> pd.Series:
        """Assign group labels to microtrips.

        Parameters
        ----------
        summary : pd.DataFrame
            MicrotripCollection summary (one row per microtrip).

        Returns
        -------
        pd.Series
            Integer cluster labels, index aligned with ``summary``.
        """
        ...


class KMeansClusterer:
    """K-Means clustering for microtrip grouping.

    Parameters
    ----------
    n_clusters : int
        Number of clusters.
    features : list[str], optional
        Column names to use as features.  When None, all numeric columns
        except ``microtrip_idx`` are used.
    random_state : int
        Random seed passed to sklearn KMeans.  Default 42.
    """

    def __init__(
        self,
        n_clusters: int,
        features: list[str] | None = None,
        random_state: int = 42,
    ) -> None:
        self.n_clusters = n_clusters
        self.features = features
        self.random_state = random_state

    def fit(self, summary: pd.DataFrame) -> pd.Series:
        """Cluster microtrips and return integer labels.

        Parameters
        ----------
        summary : pd.DataFrame
            MicrotripCollection summary.

        Returns
        -------
        pd.Series
            Integer labels (0-based), index aligned with ``summary``, name
            ``"cluster_id"``.
        """
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        if self.features is not None:
            cols = [c for c in self.features if c in summary.columns]
        else:
            excluded = {"microtrip_idx"}
            cols = [
                c
                for c in summary.select_dtypes(include="number").columns
                if c not in excluded
            ]

        X = summary[cols].fillna(0.0).to_numpy()
        X_scaled = StandardScaler().fit_transform(X)
        km = KMeans(n_clusters=self.n_clusters, random_state=self.random_state, n_init="auto")
        labels = km.fit_predict(X_scaled)
        return pd.Series(labels, index=summary.index, name="cluster_id", dtype=int)
