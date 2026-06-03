"""Tests for synthesis.targets — compute_targets."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from drive_cycle_calculator.synthesis.targets import compute_targets

_WEIGHTS: dict[str, float] = {
    "mean_speed_kmh": 1.0,
    "rpa": 2.0,
    "idle_fraction": 0.5,
    "speed_95th_kmh": 0.5,
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_summary(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal summary DataFrame for testing."""
    return pd.DataFrame(rows)


# ── compute_targets ───────────────────────────────────────────────────────────


class TestComputeTargets:
    def test_returns_all_metric_keys(self):
        """Each group entry contains the four standard metric keys."""
        df = _make_summary([
            {"group": "A", "duration_s": 30.0, "stop_duration_s": 10.0,
             "distance_m": 200.0, "mean_speed_kmh": 24.0,
             "rpa": 0.1, "speed_95th_kmh": 35.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        assert set(result["A"].keys()) == {
            "mean_speed_kmh", "rpa", "idle_fraction", "speed_95th_kmh"
        }

    def test_duration_weighted_mean_speed(self):
        """mean_speed_kmh is the duration-weighted mean across microtrips."""
        df = _make_summary([
            {"group": "A", "duration_s": 30.0, "stop_duration_s": 10.0,
             "distance_m": 150.0, "mean_speed_kmh": 20.0, "rpa": 0.0,
             "speed_95th_kmh": 25.0},
            {"group": "A", "duration_s": 10.0, "stop_duration_s": 0.0,
             "distance_m": 100.0, "mean_speed_kmh": 60.0, "rpa": 0.0,
             "speed_95th_kmh": 65.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        # total_duration_s = 40 and 10 → weighted mean = (20*40 + 60*10) / 50 = 28.0
        assert result["A"]["mean_speed_kmh"] == pytest.approx(28.0)

    def test_rpa_is_distance_weighted(self):
        """rpa target is distance-weighted, not duration-weighted."""
        df = _make_summary([
            {"group": "A", "duration_s": 20.0, "stop_duration_s": 0.0,
             "distance_m": 100.0, "mean_speed_kmh": 18.0,
             "rpa": 0.2, "speed_95th_kmh": 25.0},
            {"group": "A", "duration_s": 20.0, "stop_duration_s": 0.0,
             "distance_m": 300.0, "mean_speed_kmh": 54.0,
             "rpa": 0.4, "speed_95th_kmh": 65.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        # distance-weighted: (0.2*100 + 0.4*300) / 400 = 140/400 = 0.35
        assert result["A"]["rpa"] == pytest.approx(0.35)

    def test_idle_fraction_derived_from_stop_duration(self):
        """idle_fraction is computed from stop_duration_s when absent."""
        df = _make_summary([
            {"group": "A", "duration_s": 30.0, "stop_duration_s": 10.0,
             "distance_m": 200.0, "mean_speed_kmh": 24.0,
             "rpa": 0.1, "speed_95th_kmh": 35.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        # total_duration = 40 s; stop = 10 s → idle_fraction = 0.25
        assert result["A"]["idle_fraction"] == pytest.approx(0.25)

    def test_idle_fraction_used_when_present(self):
        """Pre-computed idle_fraction column is used directly."""
        df = _make_summary([
            {"group": "A", "duration_s": 30.0, "stop_duration_s": 10.0,
             "total_duration_s": 40.0, "idle_fraction": 0.5,
             "distance_m": 200.0, "mean_speed_kmh": 24.0,
             "rpa": 0.1, "speed_95th_kmh": 35.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        assert result["A"]["idle_fraction"] == pytest.approx(0.5)

    def test_missing_rpa_column_yields_nan(self):
        """When rpa is absent from summary, the target is nan."""
        df = _make_summary([
            {"group": "A", "duration_s": 20.0, "stop_duration_s": 5.0,
             "distance_m": 100.0, "mean_speed_kmh": 18.0, "speed_95th_kmh": 25.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        assert math.isnan(result["A"]["rpa"])

    def test_missing_speed_95th_column_yields_nan(self):
        """When speed_95th_kmh is absent, the target is nan."""
        df = _make_summary([
            {"group": "A", "duration_s": 20.0, "stop_duration_s": 5.0,
             "distance_m": 100.0, "mean_speed_kmh": 18.0, "rpa": 0.1},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        assert math.isnan(result["A"]["speed_95th_kmh"])

    def test_multiple_groups(self):
        """Targets are computed independently per group."""
        df = _make_summary([
            {"group": "low", "duration_s": 30.0, "stop_duration_s": 10.0,
             "distance_m": 100.0, "mean_speed_kmh": 20.0,
             "rpa": 0.1, "speed_95th_kmh": 30.0},
            {"group": "high", "duration_s": 20.0, "stop_duration_s": 5.0,
             "distance_m": 500.0, "mean_speed_kmh": 90.0,
             "rpa": 0.3, "speed_95th_kmh": 110.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        assert set(result.keys()) == {"low", "high"}
        assert result["high"]["mean_speed_kmh"] > result["low"]["mean_speed_kmh"]

    def test_zero_total_duration_yields_nan(self):
        """When total_duration_s is zero, duration-weighted metrics are nan."""
        df = _make_summary([
            {"group": "A", "duration_s": 0.0, "stop_duration_s": 0.0,
             "distance_m": 0.0, "mean_speed_kmh": 0.0,
             "rpa": 0.0, "speed_95th_kmh": 0.0},
        ])
        result = compute_targets(df, "group", _WEIGHTS)
        import math
        assert math.isnan(result["A"]["mean_speed_kmh"])
