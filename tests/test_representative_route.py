import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.trip import Trip


# ────────────────────────────────────────────────────────────────
# Trip.metrics
# ────────────────────────────────────────────────────────────────


class TestTripSessionMetrics:
    """Exercises Trip.metrics (the 7-key dict used by similarity scoring)."""

    def test_happy_path(self):
        df = pd.DataFrame(
            {
                "elapsed_s": [300.0, 600.0],
                "smooth_speed_kmh": [28.8, 32.4],
                "acc_ms2": [0.3, 0.5],
            }
        )
        result = Trip(df, "t", stop_threshold_kmh=2.0).metrics
        assert result["duration"] == pytest.approx(600.0)
        assert result["mean_speed"] == pytest.approx(30.6, abs=0.1)
        assert result["mean_acc"] == pytest.approx(0.4, abs=0.01)
        assert result["mean_dec"] != result["mean_acc"]  # dec is negative (braking)

    def test_missing_duration_gives_nan(self):
        df = pd.DataFrame({"smooth_speed_kmh": [28.8, 32.4]})
        result = Trip(df, "t").metrics
        assert np.isnan(result["duration"])

    def test_missing_acceleration_gives_nan(self):
        df = pd.DataFrame({"smooth_speed_kmh": [28.8, 32.4]})
        result = Trip(df, "t").metrics
        assert np.isnan(result["mean_acc"])
        assert np.isnan(result["mean_dec"])

    def test_stop_pct_calculation(self):
        # 2 of 4 values below stop threshold → 50%
        df = pd.DataFrame({"smooth_speed_kmh": [0.5, 30.0, 0.5, 30.0]})
        result = Trip(df, "t", stop_threshold_kmh=2.0).metrics
        assert result["stop_pct"] == pytest.approx(50.0)
        assert result["stops"] == 2
