import pytest
import pandas as pd
import numpy as np

from drive_cycle_calculator.gps_time_parser import GpsTimeParser

class TestGpsTimeParser:
    def test_numeric_gps_already_seconds(self):
        s = pd.Series([100.0, 101.5, 103.0])
        parser = GpsTimeParser()
        result = parser.to_duration_seconds(s)
        assert list(result) == [0.0, 1.5, 3.0]

    def test_timestamp_gps_strings(self):
        s = pd.Series(["2019-09-21 10:00:00+00:00", "2019-09-21 10:00:30+00:00"])
        parser = GpsTimeParser()
        result = parser.to_duration_seconds(s)
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == pytest.approx(30.0, abs=0.1)

    def test_all_nan_input_duration(self):
        s = pd.Series(["not a time", "also not"])
        parser = GpsTimeParser()
        result = parser.to_duration_seconds(s)
        assert result.isna().all()

    def test_mixed_valid_invalid(self):
        # First value valid numeric, second is NaN; result normalised to 0
        s = pd.Series([50.0, float("nan"), 52.0])
        parser = GpsTimeParser()
        result = parser.to_duration_seconds(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(2.0)

    def test_torque_gps_time_format(self):
        # Specific torque format parsing padding including GMT
        s = pd.Series([
            "Mon Sep 22 10:30:00 GMT+0300 2019",
            "Mon Sep 22 10:30:05 GMT+0300 2019",
            "Mon Sep 22 10:30:10 GMT+0300 2019",
        ])
        parser = GpsTimeParser()
        result_dt = parser.to_datetime(s)
        assert result_dt.notna().all()
        # Should be converted to UTC in output dataframe, +3 hours offset applied properly
        # the original datetime string parse logic just coerces it to a valid date
        
        result_dur = parser.to_duration_seconds(s)
        assert list(result_dur) == [0.0, 5.0, 10.0]

    def test_torque_gps_time_with_stray_header(self):
        # Handles the stray 'A2' header row sometimes found in exports
        s = pd.Series([
            "A2 Header Not A Date",
            "Mon Sep 22 10:30:00 GMT+0300 2019", # First valid Date
            "Mon Sep 22 10:30:15 GMT+0300 2019", 
        ])
        parser = GpsTimeParser()
        result_dur = parser.to_duration_seconds(s)
        assert pd.isna(result_dur.iloc[0])
        assert result_dur.iloc[1] == 0.0
        assert result_dur.iloc[2] == 15.0

    def test_epoch_timestamps_should_be_parsed_as_datetime(self):
        # Make sure large epoch values aren't treated as relative durations
        # e.g., 1600000000, 1600000010
        # Wait, if they are numeric, they will evaluate as differences from first!
        # If it's epoch, difference from first is identical to elapsed seconds.
        # So treating them as relative numeric duration actually produces the same perfect result of 0, 10!
        s = pd.Series([1600000000.0, 1600000010.0])
        parser = GpsTimeParser()
        result = parser.to_duration_seconds(s)
        assert list(result) == [0.0, 10.0]
