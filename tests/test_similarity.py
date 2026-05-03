"""Tests for the similarity subpackage: Protocol contract and all three measures."""

from __future__ import annotations

import numpy as np
import pytest
from conftest import make_raw_obd_df

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.similarity import (
    SimilarityMeasure,
    cosine_similarity,
    pct_deviation,
    z_score_distance,
)
from drive_cycle_calculator.trip_collection import TripCollection


# ── Helpers ───────────────────────────────────────────────────────────────────

def fleet1d(values: list[float]) -> np.ndarray:
    """Wrap a list of scalars into a (n, 1) fleet matrix."""
    return np.array([[v] for v in values])


def fleet(*rows: tuple[float, ...]) -> np.ndarray:
    """Build a (n, m) fleet matrix from row tuples."""
    return np.array(rows, dtype=float)


# ── Protocol satisfaction ─────────────────────────────────────────────────────


class TestProtocol:
    def test_plain_function_satisfies_protocol(self):
        def my_measure(f: np.ndarray, t: np.ndarray) -> float:
            return 42.0

        df = make_raw_obd_df(n=20, speed_kmh=30.0)
        tc = TripCollection([OBDFile(df, "t").to_trip()])
        scores = tc.similarity_scores(measure=my_measure)
        assert len(scores) == 1
        assert list(scores.values()) == [42.0]

    def test_lambda_satisfies_protocol(self):
        df = make_raw_obd_df(n=20, speed_kmh=30.0)
        tc = TripCollection([OBDFile(df, "t").to_trip()])
        scores = tc.similarity_scores(measure=lambda f, t: 99.0)
        assert len(scores) == 1
        assert list(scores.values()) == [99.0]


# ── pct_deviation ─────────────────────────────────────────────────────────────


class TestPctDeviation:
    def test_perfect_match_returns_100(self):
        assert pct_deviation(fleet1d([30.0, 30.0]), np.array([30.0])) == pytest.approx(100.0)

    def test_zero_fleet_zero_trip_returns_100(self):
        assert pct_deviation(fleet1d([0.0, 0.0]), np.array([0.0])) == pytest.approx(100.0)

    def test_zero_fleet_nonzero_trip_returns_0(self):
        assert pct_deviation(fleet1d([0.0, 0.0]), np.array([5.0])) == pytest.approx(0.0)

    def test_20pct_off_returns_80(self):
        # mean = 10, trip = 12 → 20% deviation → score 80
        assert pct_deviation(fleet1d([10.0, 10.0]), np.array([12.0])) == pytest.approx(80.0)

    def test_large_deviation_clamped_to_0(self):
        assert pct_deviation(fleet1d([10.0, 10.0]), np.array([100.0])) == pytest.approx(0.0)

    def test_nan_fleet_component_scores_0(self):
        assert pct_deviation(fleet1d([np.nan, np.nan]), np.array([5.0])) == pytest.approx(0.0)

    def test_negative_trip_clamped(self):
        # |−5 − 10| / 10 * 100 = 150% → clamped to 0
        assert pct_deviation(fleet1d([10.0, 10.0]), np.array([-5.0])) == pytest.approx(0.0)

    def test_multidimensional_average(self):
        # metric 0: perfect (100); metric 1: 50% off (50) → mean = 75
        f = fleet([10.0, 20.0], [10.0, 20.0])
        t = np.array([10.0, 30.0])
        assert pct_deviation(f, t) == pytest.approx(75.0)

    def test_output_in_range(self):
        rng = np.random.default_rng(0)
        f = rng.random((10, 7)) * 100
        t = rng.random(7) * 100
        score = pct_deviation(f, t)
        assert 0.0 <= score <= 100.0


# ── cosine_similarity ─────────────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_direction_returns_100(self):
        f = fleet([3.0, 4.0], [3.0, 4.0])
        t = np.array([3.0, 4.0])
        assert cosine_similarity(f, t) == pytest.approx(100.0)

    def test_parallel_scaled_returns_100(self):
        # Cosine measures direction only — scaling does not change the score.
        f = fleet([1.0, 0.0], [1.0, 0.0])
        t = np.array([5.0, 0.0])
        assert cosine_similarity(f, t) == pytest.approx(100.0)

    def test_orthogonal_returns_0(self):
        f = fleet([1.0, 0.0], [1.0, 0.0])
        t = np.array([0.0, 1.0])
        assert cosine_similarity(f, t) == pytest.approx(0.0)

    def test_anti_parallel_clamped_to_0(self):
        f = fleet([1.0, 0.0], [1.0, 0.0])
        t = np.array([-1.0, 0.0])
        assert cosine_similarity(f, t) == pytest.approx(0.0)

    def test_zero_fleet_returns_0(self):
        f = fleet([0.0, 0.0], [0.0, 0.0])
        t = np.array([1.0, 1.0])
        assert cosine_similarity(f, t) == 0.0

    def test_zero_trip_returns_0(self):
        f = fleet([1.0, 1.0], [1.0, 1.0])
        t = np.array([0.0, 0.0])
        assert cosine_similarity(f, t) == 0.0

    def test_output_in_range(self):
        rng = np.random.default_rng(1)
        f = rng.random((8, 7)) * 100
        t = rng.random(7) * 100
        score = cosine_similarity(f, t)
        assert 0.0 <= score <= 100.0


# ── z_score_distance ──────────────────────────────────────────────────────────


class TestZScoreDistance:
    def test_fleet_mean_returns_100(self):
        f = fleet([10.0, 20.0], [20.0, 40.0])
        t = np.array([15.0, 30.0])  # fleet mean
        assert z_score_distance(f, t) == pytest.approx(100.0)

    def test_further_scores_lower(self):
        f = fleet([10.0], [20.0])
        close = np.array([15.0])
        far = np.array([100.0])
        assert z_score_distance(f, close) > z_score_distance(f, far)

    def test_always_positive(self):
        f = fleet([10.0, 20.0], [30.0, 40.0])
        t = np.array([1000.0, 1000.0])
        assert z_score_distance(f, t) > 0.0

    def test_constant_metric_does_not_raise(self):
        # std = 0 for both metrics — safe_std defaults to 1
        f = fleet([10.0, 5.0], [10.0, 5.0])
        t = np.array([10.0, 5.0])
        assert z_score_distance(f, t) == pytest.approx(100.0)

    def test_output_in_range(self):
        rng = np.random.default_rng(2)
        f = rng.random((6, 7)) * 100
        t = rng.random(7) * 100
        score = z_score_distance(f, t)
        assert 0.0 < score <= 100.0

    def test_scale_independence(self):
        # Doubling all values in one metric should not change the score because
        # std scales proportionally — the z-score stays the same.
        f_base = fleet([10.0, 1.0], [20.0, 2.0])
        t_base = np.array([25.0, 1.5])
        f_scaled = fleet([10.0, 10.0], [20.0, 20.0])
        t_scaled = np.array([25.0, 15.0])
        assert z_score_distance(f_base, t_base) == pytest.approx(
            z_score_distance(f_scaled, t_scaled), rel=1e-6
        )


# ── TripCollection integration ────────────────────────────────────────────────


class TestTripCollectionWithMeasure:
    def _make_tc(self, speeds: list[float], archive_parquet) -> TripCollection:
        trips = []
        for i, spd in enumerate(speeds):
            df = make_raw_obd_df(n=30, speed_kmh=spd)
            df["Longitude"] = float(24 + i)
            p = archive_parquet(f"trip_{i}.parquet", df=df)
            trips.append(OBDFile.from_parquet(p).to_trip())
        return TripCollection(trips)

    def test_default_measure_is_pct_deviation(self, archive_parquet):
        tc = self._make_tc([30.0, 40.0, 50.0], archive_parquet)
        scores_default = tc.similarity_scores()
        scores_explicit = tc.similarity_scores(measure=pct_deviation)
        assert scores_default == pytest.approx(scores_explicit)

    def test_cosine_measure_accepted(self, archive_parquet):
        tc = self._make_tc([30.0, 40.0, 50.0], archive_parquet)
        scores = tc.similarity_scores(measure=cosine_similarity)
        assert len(scores) == 3
        assert all(0.0 <= v <= 100.0 for v in scores.values())

    def test_z_score_measure_accepted(self, archive_parquet):
        tc = self._make_tc([30.0, 40.0, 50.0], archive_parquet)
        scores = tc.similarity_scores(measure=z_score_distance)
        assert len(scores) == 3
        assert all(0.0 < v <= 100.0 for v in scores.values())

    def test_find_representative_accepts_measure(self, archive_parquet):
        tc = self._make_tc([10.0, 30.0, 50.0], archive_parquet)
        rep = tc.find_representative(measure=cosine_similarity)
        from drive_cycle_calculator.trip import Trip
        assert isinstance(rep, Trip)

    def test_middle_trip_wins_pct_and_zscore(self, archive_parquet):
        # pct_deviation and z_score_distance both weight magnitude — the trip
        # closest to the fleet mean speed wins. Cosine is direction-only and makes
        # no such guarantee for this data, so it is excluded here.
        tc = self._make_tc([10.0, 30.0, 50.0], archive_parquet)
        for measure in (pct_deviation, z_score_distance):
            rep = tc.find_representative(measure=measure)
            assert rep.mean_speed == pytest.approx(tc.trips[1].mean_speed, rel=0.1), \
                f"Failed for {measure.__name__}"
