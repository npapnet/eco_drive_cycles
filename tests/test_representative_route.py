import pytest
import numpy as np
import pandas as pd
from drive_cycle_calculator.metrics import (
    similarity,
    compute_session_metrics,
    find_representative_sheet,
)


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
# compute_session_metrics
# ────────────────────────────────────────────────────────────────

class TestComputeSessionMetrics:
    def _make_df(self, **kwargs):
        return pd.DataFrame(kwargs)

    def test_happy_path(self):
        df = pd.DataFrame({
            "elapsed_s": [300.0, 600.0],
            "speed_ms": [8.0, 9.0],
            "acceleration_ms2": [0.3, 0.5],
            "deceleration_ms2": [-0.2, -0.4],
        })
        result = compute_session_metrics(df, stop_threshold_kmh=2.0)
        assert result["duration"] == pytest.approx(600.0)
        assert result["mean_speed"] == pytest.approx(8.5 * 3.6, abs=0.01)
        assert result["mean_acc"] == pytest.approx(0.4, abs=0.01)
        assert result["mean_dec"] == pytest.approx(-0.3, abs=0.01)

    def test_missing_duration_gives_nan(self):
        df = pd.DataFrame({"speed_ms": [5.0, 6.0]})
        result = compute_session_metrics(df)
        assert np.isnan(result["duration"])

    def test_missing_acceleration_gives_nan(self):
        df = pd.DataFrame({"speed_ms": [5.0, 6.0]})
        result = compute_session_metrics(df)
        assert np.isnan(result["mean_acc"])
        assert np.isnan(result["mean_dec"])

    def test_stop_pct_calculation(self):
        # 2 of 4 values are below 2.0 km/h → 50%
        # values in m/s: 0.1 m/s = 0.36 km/h (below 2.0), 5.0 m/s = 18 km/h
        df = pd.DataFrame({"speed_ms": [0.1, 5.0, 0.1, 5.0]})
        result = compute_session_metrics(df, stop_threshold_kmh=2.0)
        assert result["stop_pct"] == pytest.approx(50.0)
        assert result["stops"] == 2


# ────────────────────────────────────────────────────────────────
# find_representative_sheet
# ────────────────────────────────────────────────────────────────

class TestFindRepresentativeSheet:
    def test_empty_dict_raises_value_error(self):
        with pytest.raises(ValueError, match="No data sheets"):
            find_representative_sheet({})

    def test_single_sheet_returns_it_with_100(self):
        df = pd.DataFrame({
            "elapsed_s": [300.0, 600.0],
            "speed_ms": [8.0, 9.0],
            "acceleration_ms2": [0.3, 0.4],
            "deceleration_ms2": [-0.2, -0.3],
        })
        best, score = find_representative_sheet({"2025-05-14_Morning": df})
        assert best == "2025-05-14_Morning"
        assert score == pytest.approx(100.0)

    def test_selects_closest_sheet(self):
        # Morning: metrics in the middle of the distribution → should win
        # Evening: extreme values far from the average
        close_df = pd.DataFrame({
            "elapsed_s": [600.0, 600.0, 600.0],
            "speed_ms": [10.0, 12.0, 11.0],
            "acceleration_ms2": [0.5, 0.6, 0.55],
            "deceleration_ms2": [-0.4, -0.5, -0.45],
        })
        far_df = pd.DataFrame({
            "elapsed_s": [1.0, 1.0, 1.0],
            "speed_ms": [0.1, 0.1, 0.1],
            "acceleration_ms2": [0.01, 0.01, 0.01],
            "deceleration_ms2": [-0.01, -0.01, -0.01],
        })
        sheets = {"2025-05-14_Morning": close_df, "2025-05-14_Evening": far_df}
        best, score = find_representative_sheet(sheets)
        assert best == "2025-05-14_Morning"
        assert 0.0 <= score <= 100.0

    def test_score_is_in_valid_range(self):
        df1 = pd.DataFrame({"speed_ms": [5.0, 10.0], "acceleration_ms2": [0.3, 0.3], "deceleration_ms2": [-0.2, -0.2]})
        df2 = pd.DataFrame({"speed_ms": [8.0, 12.0], "acceleration_ms2": [0.4, 0.4], "deceleration_ms2": [-0.3, -0.3]})
        _, score = find_representative_sheet({"a": df1, "b": df2})
        assert 0.0 <= score <= 100.0
