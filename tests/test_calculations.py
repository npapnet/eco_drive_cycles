import pytest
import pandas as pd
import numpy as np
from drive_cycle_calculator.calculations import gps_to_duration_seconds, smooth_and_derive


class TestGpsToDurationSeconds:
    def test_numeric_gps_already_seconds(self):
        s = pd.Series([100.0, 101.5, 103.0])
        result = gps_to_duration_seconds(s)
        assert list(result) == [0.0, 1.5, 3.0]

    def test_timestamp_gps_strings(self):
        s = pd.Series(["2019-09-21 10:00:00+00:00", "2019-09-21 10:00:30+00:00"])
        result = gps_to_duration_seconds(s)
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == pytest.approx(30.0, abs=0.1)

    def test_all_nan_input(self):
        s = pd.Series(["not a time", "also not"])
        result = gps_to_duration_seconds(s)
        assert result.isna().all()

    def test_mixed_valid_invalid(self):
        # First value valid numeric, second is NaN; result normalised to 0
        s = pd.Series([50.0, float("nan"), 52.0])
        result = gps_to_duration_seconds(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(2.0)


class TestSmoothAndDerive:
    def test_returns_expected_keys(self):
        speed = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
        result = smooth_and_derive(speed)
        assert set(result.keys()) == {"smooth_speed", "speed_ms", "acceleration", "pos_acc", "neg_acc"}

    def test_smoothing_window_produces_nan_at_edges(self):
        # window=4, center=True, min_periods=4
        # rows 0-1 and 6-7 get NaN; rows 2-5 get valid means
        speed = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
        result = smooth_and_derive(speed)
        assert pd.isna(result["smooth_speed"].iloc[0])
        assert pd.isna(result["smooth_speed"].iloc[1])
        assert result["smooth_speed"].iloc[3] == pytest.approx(15.0, abs=0.1)

    def test_speed_ms_is_smooth_divided_by_3_6(self):
        speed = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
        result = smooth_and_derive(speed)
        valid = result["smooth_speed"].dropna()
        valid_ms = result["speed_ms"].dropna()
        assert len(valid) == len(valid_ms)
        for s_kmh, s_ms in zip(valid, valid_ms):
            assert s_ms == pytest.approx(s_kmh / 3.6, rel=1e-6)

    def test_acceleration_split_no_overlap(self):
        # positive and negative acceleration must not share rows
        speed = pd.Series([0.0, 10.0, 20.0, 15.0, 5.0, 0.0, 5.0, 10.0])
        result = smooth_and_derive(speed)
        pos = result["pos_acc"].dropna()
        neg = result["neg_acc"].dropna()
        assert pos.index.intersection(neg.index).empty
        assert (pos > 0).all()
        assert (neg < 0).all()

    def test_short_series_all_nan(self):
        # Fewer than 4 rows → all NaN smooth_speed due to min_periods=4
        speed = pd.Series([10.0, 20.0, 15.0])
        result = smooth_and_derive(speed)
        assert result["smooth_speed"].isna().all()
