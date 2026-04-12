import pytest
import numpy as np
import pandas as pd
from drive_cycle_calculator.trip import Trip
from drive_cycle_calculator.trip_collection import similarity


# ────────────────────────────────────────────────────────────────
# similarity
# ────────────────────────────────────────────────────────────────


class TestSimilarity:
    def test_perfect_match(self):
        assert similarity(50.0, 50.0) == 100.0

    def test_zero_overall_zero_rep(self):
        assert similarity(0.0, 0.0) == 100.0

    def test_zero_overall_nonzero_rep(self):
        assert similarity(0.0, 5.0) == 0.0

    def test_clamped_at_zero_not_negative(self):
        # |100-10|/10 * 100 = 900% → clamped to 0
        assert similarity(10.0, 100.0) == 0.0

    def test_nan_overall_returns_zero(self):
        assert similarity(float("nan"), 50.0) == 0.0

    def test_negative_rep_val_clamped(self):
        # mean deceleration is always negative — verify clamping works
        # |(-5)-10|/10*100 = 150% → clamped to 0
        assert similarity(10.0, -5.0) == 0.0

    def test_partial_mismatch_between_0_and_100(self):
        # |12-10|/10*100 = 20% mismatch → similarity = 80
        result = similarity(10.0, 12.0)
        assert result == pytest.approx(80.0)


# ────────────────────────────────────────────────────────────────
# Trip.metrics  (was: compute_session_metrics)
# ────────────────────────────────────────────────────────────────


class TestTripSessionMetrics:
    """compute_session_metrics was inlined into Trip.metrics.
    These tests exercise the same logic via Trip."""

    def test_happy_path(self):
        df = pd.DataFrame(
            {
                "elapsed_s": [300.0, 600.0],
                "speed_ms": [8.0, 9.0],
                "acceleration_ms2": [0.3, 0.5],
                "deceleration_ms2": [-0.2, -0.4],
            }
        )
        result = Trip(df, "t", stop_threshold_kmh=2.0).metrics
        assert result["duration"] == pytest.approx(600.0)
        assert result["mean_speed"] == pytest.approx(8.5 * 3.6, abs=0.01)
        assert result["mean_acc"] == pytest.approx(0.4, abs=0.01)
        assert result["mean_dec"] == pytest.approx(-0.3, abs=0.01)

    def test_missing_duration_gives_nan(self):
        df = pd.DataFrame({"speed_ms": [5.0, 6.0]})
        result = Trip(df, "t").metrics
        assert np.isnan(result["duration"])

    def test_missing_acceleration_gives_nan(self):
        df = pd.DataFrame({"speed_ms": [5.0, 6.0]})
        result = Trip(df, "t").metrics
        assert np.isnan(result["mean_acc"])
        assert np.isnan(result["mean_dec"])

    def test_stop_pct_calculation(self):
        # 2 of 4 values are below 2.0 km/h → 50%
        # values in m/s: 0.1 m/s = 0.36 km/h (below 2.0), 5.0 m/s = 18 km/h
        df = pd.DataFrame({"speed_ms": [0.1, 5.0, 0.1, 5.0]})
        result = Trip(df, "t", stop_threshold_kmh=2.0).metrics
        assert result["stop_pct"] == pytest.approx(50.0)
        assert result["stops"] == 2
