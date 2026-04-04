import pytest
import pandas as pd
import numpy as np
from drive_cycle_calculator.metrics import (
    compute_average_speed,
    compute_average_speed_without_stops,
    compute_maximum_speed,
    compute_average_acceleration,
    compute_average_deceleration,
    compute_stop_percentage,
    compute_number_of_stops,
    compute_total_stop_percentage,
    compute_engine_load,
    compute_fuel_consumption,
    compute_co2_emissions,
    compute_speed_profile,
)


# ────────────────────────────────────────────────────────────────
# compute_average_speed
# ────────────────────────────────────────────────────────────────

class TestComputeAverageSpeed:
    def test_morning_evening_grouping(self):
        sheets = {
            "2025-05-14_Morning": pd.DataFrame({"Ταχ m/s": [10.0, 12.0]}),
            "2025-05-14_Evening": pd.DataFrame({"Ταχ m/s": [8.0, 6.0]}),
        }
        result = compute_average_speed(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(11.0 * 3.6, abs=0.01)
        assert result["2025-05-14"]["Evening"] == pytest.approx(7.0 * 3.6, abs=0.01)

    def test_missing_column_returns_empty(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"other": [1.0]})}
        result = compute_average_speed(sheets)
        assert result == {}

    def test_empty_series_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Ταχ m/s": pd.Series([], dtype=float)})}
        result = compute_average_speed(sheets)
        assert result["2025-05-14"]["Morning"] == 0.0

    def test_sheet_name_without_underscore(self):
        sheets = {"NoUnderscore": pd.DataFrame({"Ταχ m/s": [5.0]})}
        result = compute_average_speed(sheets)
        assert "NoUnderscore" in result
        assert "Unknown" in result["NoUnderscore"]


# ────────────────────────────────────────────────────────────────
# compute_maximum_speed
# ────────────────────────────────────────────────────────────────

class TestComputeMaximumSpeed:
    def test_returns_max(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Ταχ m/s": [5.0, 10.0, 8.0]})}
        result = compute_maximum_speed(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(10.0 * 3.6, abs=0.01)

    def test_missing_column_returns_empty(self):
        assert compute_maximum_speed({"s": pd.DataFrame({"x": [1.0]})}) == {}


# ────────────────────────────────────────────────────────────────
# compute_average_speed_without_stops
# ────────────────────────────────────────────────────────────────

class TestComputeAverageSpeedWithoutStops:
    def test_excludes_stop_rows(self):
        # 1.0 m/s = 3.6 km/h → below threshold 5.0 → excluded
        # 10.0 m/s = 36.0 km/h → above threshold → included
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Ταχ m/s": [1.0, 10.0, 10.0]})}
        result = compute_average_speed_without_stops(sheets, stop_threshold_kmh=5.0)
        assert result["2025-05-14"]["Morning"] == pytest.approx(36.0, abs=0.01)

    def test_all_stopped_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Ταχ m/s": [0.1, 0.2]})}
        result = compute_average_speed_without_stops(sheets, stop_threshold_kmh=2.0)
        assert result["2025-05-14"]["Morning"] == 0.0


# ────────────────────────────────────────────────────────────────
# compute_average_acceleration / deceleration
# ────────────────────────────────────────────────────────────────

class TestComputeAverageAcceleration:
    def test_mean_of_positive_values(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Επιταχυνση": [0.3, 0.5, float("nan")]})}
        result = compute_average_acceleration(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(0.4, abs=0.01)

    def test_empty_column_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Επιταχυνση": pd.Series([], dtype=float)})}
        result = compute_average_acceleration(sheets)
        assert result["2025-05-14"]["Morning"] == 0.0


class TestComputeAverageDeceleration:
    def test_only_negative_values_included(self):
        # positive values should be excluded; mean of [-0.4, -0.6] = -0.5
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Επιβραδυνση": [0.3, -0.4, -0.6]})}
        result = compute_average_deceleration(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(-0.5, abs=0.01)

    def test_no_negative_values_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Επιβραδυνση": [0.0, 0.3, 0.5]})}
        result = compute_average_deceleration(sheets)
        assert result["2025-05-14"]["Morning"] == 0.0


# ────────────────────────────────────────────────────────────────
# compute_number_of_stops  (state machine — NOT row counting)
# ────────────────────────────────────────────────────────────────

class TestComputeNumberOfStops:
    def test_counts_transitions_not_rows(self):
        # 3 transitions: moving→stop at indices 2, 5, 8
        speeds = [10.0, 8.0, 1.0, 5.0, 9.0, 1.0, 7.0, 6.0, 1.0]
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": speeds})}
        result = compute_number_of_stops(sheets)
        assert result["2025-05-14"]["Morning"] == 3

    def test_all_above_threshold_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": [10.0, 12.0, 8.0]})}
        result = compute_number_of_stops(sheets)
        assert result["2025-05-14"]["Morning"] == 0

    def test_empty_column_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": pd.Series([], dtype=float)})}
        result = compute_number_of_stops(sheets)
        assert result["2025-05-14"]["Morning"] == 0

    def test_consecutive_stops_count_as_one(self):
        # Moving, then 3 stop rows in a row → only 1 transition
        speeds = [10.0, 1.0, 0.5, 0.0, 10.0]
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": speeds})}
        result = compute_number_of_stops(sheets)
        assert result["2025-05-14"]["Morning"] == 1


# ────────────────────────────────────────────────────────────────
# compute_stop_percentage  (unit heuristic preserved)
# ────────────────────────────────────────────────────────────────

class TestComputeStopPercentage:
    def test_normal_path_fifty_percent(self):
        # 3 of 6 values are <= 2.0 → 50%
        speeds = [0.0, 5.0, 30.0, 50.0, 1.5, 0.0]
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": speeds})}
        result = compute_stop_percentage(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(50.0)

    def test_unit_heuristic_triggers_when_max_below_threshold(self):
        # All values well below 2.0 → heuristic fires (multiplies by 3.6)
        # After *=3.6: 0.3→1.08, 0.4→1.44, 0.5→1.8, 0.3→1.08 (all <= 2.0)
        speeds = [0.3, 0.4, 0.5, 0.3]
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": speeds})}
        result = compute_stop_percentage(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(100.0)

    def test_empty_returns_zero(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Εξομαλυνση": pd.Series([], dtype=float)})}
        result = compute_stop_percentage(sheets)
        assert result["2025-05-14"]["Morning"] == 0.0


# ────────────────────────────────────────────────────────────────
# compute_total_stop_percentage
# ────────────────────────────────────────────────────────────────

class TestComputeTotalStopPercentage:
    def test_returns_correct_split(self):
        # 2 stops out of 4 total across all sheets → 50% stop
        sheets = {
            "s1": pd.DataFrame({"Εξομαλυνση": [1.0, 10.0]}),
            "s2": pd.DataFrame({"Εξομαλυνση": [1.0, 10.0]}),
        }
        pct_stop, pct_move = compute_total_stop_percentage(sheets)
        assert pct_stop == pytest.approx(50.0)
        assert pct_move == pytest.approx(50.0)

    def test_no_data_returns_zeros(self):
        sheets = {"s1": pd.DataFrame({"Εξομαλυνση": pd.Series([], dtype=float)})}
        pct_stop, pct_move = compute_total_stop_percentage(sheets)
        assert pct_stop == 0.0
        assert pct_move == 0.0

    def test_sum_is_100(self):
        sheets = {"s1": pd.DataFrame({"Εξομαλυνση": [5.0, 10.0, 20.0, 1.0, 0.5]})}
        pct_stop, pct_move = compute_total_stop_percentage(sheets)
        assert pct_stop + pct_move == pytest.approx(100.0)


# ────────────────────────────────────────────────────────────────
# OBD channel metrics
# ────────────────────────────────────────────────────────────────

class TestComputeEngineLoad:
    def test_mean_per_session(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Engine Load(%)": [40.0, 60.0]})}
        result = compute_engine_load(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(50.0)

    def test_missing_column_skipped(self):
        sheets = {"s": pd.DataFrame({"x": [1.0]})}
        assert compute_engine_load(sheets) == {}


class TestComputeFuelConsumption:
    def test_mean_per_session(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"Fuel flow rate/hour(l/hr)": [2.0, 4.0]})}
        result = compute_fuel_consumption(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(3.0)


class TestComputeCo2Emissions:
    def test_mean_per_session(self):
        sheets = {"2025-05-14_Morning": pd.DataFrame({"CO₂ in g/km (Average)(g/km)": [120.0, 140.0]})}
        result = compute_co2_emissions(sheets)
        assert result["2025-05-14"]["Morning"] == pytest.approx(130.0)


# ────────────────────────────────────────────────────────────────
# compute_speed_profile
# ────────────────────────────────────────────────────────────────

def _speed_profile_sheet(smooth_col_name: str, n: int = 8) -> pd.DataFrame:
    """Minimal DataFrame suitable for compute_speed_profile."""
    return pd.DataFrame({
        "Ταχ m/s": [3.0] * n,
        "Διάρκεια (sec)": list(range(n)),
        smooth_col_name: [30.0] * n,
    })


class TestComputeSpeedProfile:
    def test_no_accent_variant_column(self):
        """Column name without accent mark is found and returned correctly."""
        sheets = {"2025-05-14_Morning": _speed_profile_sheet("Εξομαλυνση")}
        name, x, y = compute_speed_profile(sheets)
        assert name == "2025-05-14_Morning"
        assert len(x) == len(y)
        assert list(y) == pytest.approx([30.0] * len(y))

    def test_accent_variant_column(self):
        """Column name WITH accent mark is found as fallback."""
        sheets = {"2025-05-14_Morning": _speed_profile_sheet("Εξομάλυνση")}
        name, x, y = compute_speed_profile(sheets)
        assert name == "2025-05-14_Morning"
        assert len(y) > 0

    def test_missing_smooth_column_raises(self):
        """RuntimeError raised when neither accent variant exists."""
        df = pd.DataFrame({
            "Ταχ m/s": [3.0] * 5,
            "Διάρκεια (sec)": list(range(5)),
            "WrongColumn": [1.0] * 5,
        })
        with pytest.raises(RuntimeError, match="not found"):
            compute_speed_profile({"2025-05-14_Morning": df})
