import pytest
import pandas as pd
import numpy as np
from drive_cycle_calculator.metrics._computations import gps_to_duration_seconds


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
