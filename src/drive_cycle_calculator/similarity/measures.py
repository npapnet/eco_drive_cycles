from __future__ import annotations

from typing import Protocol

import numpy as np


class SimilarityMeasure(Protocol):
    """Contract for fleet-level similarity measures.

    Parameters
    ----------
    fleet : np.ndarray, shape (n_trips, n_metrics)
        Full collection metric matrix — one row per trip, one column per metric.
    trip : np.ndarray, shape (n_metrics,)
        Metric vector for the trip being scored.

    Returns
    -------
    float
        Similarity score. Higher means more similar to the fleet centre.
        All built-in measures return values in (0, 100].
    """

    def __call__(self, fleet: np.ndarray, trip: np.ndarray) -> float: ...


def pct_deviation(fleet: np.ndarray, trip: np.ndarray) -> float:
    """Per-component percentage similarity averaged across metrics.

    For each metric k:
        score_k = max(0, 100 - |trip_k - mean_k| / |mean_k| * 100)

    Returns the mean of score_k over all metrics. Range: [0, 100].
    A score of 100 means the trip matches the fleet average exactly on every metric.
    """
    mean = np.nanmean(fleet, axis=0)
    scores: list[float] = []
    for f, t in zip(mean, trip):
        if np.isnan(f):
            scores.append(0.0)
        elif f == 0.0:
            scores.append(100.0 if t == 0.0 else 0.0)
        else:
            scores.append(max(0.0, 100.0 - abs(t - f) / abs(f) * 100.0))
    return float(np.mean(scores))


def cosine_similarity(fleet: np.ndarray, trip: np.ndarray) -> float:
    """Cosine similarity between the trip vector and the fleet centroid.

    cos(θ) = (mean · trip) / (‖mean‖ · ‖trip‖)

    Measures the angular alignment between the trip and the fleet average in
    metric space. Negative cosine values are clamped to 0. Range: [0, 100].

    Note: cosine captures directional similarity only — two trips whose metrics
    differ by a constant factor score 100. Pair with z_score_distance when
    magnitude differences matter.
    """
    mean = np.nanmean(fleet, axis=0)
    norm_mean = float(np.linalg.norm(mean))
    norm_trip = float(np.linalg.norm(trip))
    if norm_mean == 0.0 or norm_trip == 0.0:
        return 0.0
    cos = float(np.dot(mean, trip) / (norm_mean * norm_trip))
    return max(0.0, float(np.clip(cos, -1.0, 1.0))) * 100.0


def z_score_distance(fleet: np.ndarray, trip: np.ndarray) -> float:
    """Similarity based on z-score normalised Euclidean distance from the fleet centroid.

    Steps:
      1. Compute fleet mean μ and std σ per metric.
      2. Normalise the trip: z_k = (trip_k - μ_k) / σ_k.
         Metrics with σ = 0 are left un-normalised (difference divided by 1).
      3. Distance d = ‖z‖ (Euclidean norm of the z-score vector).
      4. Similarity = 100 / (1 + d).

    Range: (0, 100]. A trip identical to the fleet mean scores exactly 100.
    Unlike pct_deviation, this measure is scale-independent: a 10 km/h deviation
    in mean speed is weighted by the fleet spread of that metric.
    """
    mean = np.nanmean(fleet, axis=0)
    std = np.nanstd(fleet, axis=0)
    # Only score metrics where the fleet has valid data and the trip value is finite.
    valid = ~np.isnan(mean) & ~np.isnan(trip)
    if not np.any(valid):
        return 0.0
    safe_std = np.where(std[valid] == 0.0, 1.0, std[valid])
    z = (trip[valid] - mean[valid]) / safe_std
    distance = float(np.linalg.norm(z))
    return 100.0 / (1.0 + distance)
