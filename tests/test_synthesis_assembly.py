"""Tests for synthesis.assembly — smooth_junction, assemble_cycle, validate_cycle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.schema import MarkovConfig, SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter
from drive_cycle_calculator.synthesis.assembly import (
    assemble_cycle,
    smooth_junction,
    validate_cycle,
)
from drive_cycle_calculator.trip import Trip

_CFG = MarkovConfig()
_IDLE_S = 5


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_processed_df(speeds: list[float]) -> pd.DataFrame:
    n = len(speeds)
    return pd.DataFrame({
        "elapsed_s": [float(i) for i in range(n)],
        "smooth_speed_kmh": speeds,
        "acc_ms2": [0.0] * n,
        "speed_kmh": speeds,
        "co2_g_per_km": [0.0] * n,
        "engine_load_pct": [0.0] * n,
        "fuel_flow_lph": [0.0] * n,
    })


_SPEEDS = [0.0] * 5 + [30.0] * 21 + [0.0] * 4 + [50.0] * 25 + [0.0] * 5


@pytest.fixture
def two_mt_paths(tmp_path) -> list[Path]:
    """Persist two microtrips to tmp_path and return their paths."""
    trip = Trip(_make_processed_df(_SPEEDS), "t")
    segmenter = MicrotripSegmenter(SegmentationConfig())
    mts = segmenter.segment(trip)
    assert len(mts) == 2
    paths = []
    for i, mt in enumerate(mts):
        p = tmp_path / f"mt_{i:03d}.parquet"
        mt.to_parquet(p)
        paths.append(p)
    return paths


# ── smooth_junction ───────────────────────────────────────────────────────────


class TestSmoothJunction:
    def test_no_ramp_when_delta_small(self):
        """Returns empty array when |Δv| ≤ 2 km/h."""
        a = np.array([30.0, 30.0, 31.0])
        b = np.array([30.0, 29.0])
        bridge = smooth_junction(a, b)
        assert len(bridge) == 0

    def test_ramp_when_delta_large(self):
        """Returns a non-empty bridge when |Δv| > 2 km/h."""
        a = np.array([50.0, 50.0])
        b = np.array([0.0, 0.0])
        bridge = smooth_junction(a, b)
        assert len(bridge) > 0

    def test_ramp_bounded_by_ramp_s(self):
        """Bridge length does not exceed ramp_s."""
        a = np.array([100.0])
        b = np.array([0.0])
        bridge = smooth_junction(a, b, ramp_s=3)
        assert len(bridge) <= 3

    def test_ramp_values_between_endpoints(self):
        """All bridge values lie strictly between v_end and v_start."""
        a = np.array([60.0])
        b = np.array([0.0])
        bridge = smooth_junction(a, b)
        assert all(0.0 < v < 60.0 for v in bridge)

    def test_empty_a_uses_zero(self):
        """Empty *a* is treated as ending at 0 km/h."""
        bridge = smooth_junction(np.array([]), np.array([30.0]))
        assert len(bridge) > 0  # 30 km/h > 2 km/h threshold

    def test_empty_b_uses_zero(self):
        """Empty *b* is treated as starting at 0 km/h."""
        bridge = smooth_junction(np.array([30.0]), np.array([]))
        assert len(bridge) > 0


# ── assemble_cycle ────────────────────────────────────────────────────────────


class TestAssembleCycle:
    def test_empty_groups_returns_empty_df(self):
        """Empty groups list returns an empty DataFrame with correct columns."""
        cycle = assemble_cycle([], idle_s=_IDLE_S, config=_CFG)
        assert list(cycle.columns) == ["t_s", "speed_kmh", "group"]
        assert len(cycle) == 0

    def test_idle_gap_between_groups(self, two_mt_paths):
        """Idle segment of exactly idle_s seconds is inserted between groups."""
        groups = [
            ("A", [two_mt_paths[0]]),
            ("B", [two_mt_paths[1]]),
        ]
        cycle = assemble_cycle(groups, idle_s=_IDLE_S, config=_CFG)
        idle_rows = cycle[cycle["group"] == "idle"]
        assert len(idle_rows) == _IDLE_S

    def test_no_idle_after_last_group(self, two_mt_paths):
        """No trailing idle segment is added after the last group."""
        groups = [("A", [two_mt_paths[0]])]
        cycle = assemble_cycle(groups, idle_s=_IDLE_S, config=_CFG)
        assert cycle["group"].iloc[-1] != "idle"

    def test_group_labels_present(self, two_mt_paths):
        """Group column contains the provided labels and idle."""
        groups = [("low", [two_mt_paths[0]]), ("high", [two_mt_paths[1]])]
        cycle = assemble_cycle(groups, idle_s=_IDLE_S, config=_CFG)
        assert "low" in cycle["group"].values
        assert "high" in cycle["group"].values

    def test_t_s_is_sequential(self, two_mt_paths):
        """t_s column is a zero-based integer sequence with no gaps."""
        groups = [("A", [two_mt_paths[0]]), ("B", [two_mt_paths[1]])]
        cycle = assemble_cycle(groups, idle_s=_IDLE_S, config=_CFG)
        assert list(cycle["t_s"]) == list(range(len(cycle)))

    def test_speed_kmh_non_negative(self, two_mt_paths):
        """All speed values are ≥ 0."""
        groups = [("A", [two_mt_paths[0]]), ("B", [two_mt_paths[1]])]
        cycle = assemble_cycle(groups, idle_s=_IDLE_S, config=_CFG)
        assert (cycle["speed_kmh"] >= 0).all()


# ── validate_cycle ────────────────────────────────────────────────────────────


class TestValidateCycle:
    def _make_cycle(self, group_label: str, speed: float, n: int) -> pd.DataFrame:
        return pd.DataFrame({
            "t_s": range(n),
            "speed_kmh": [speed] * n,
            "group": [group_label] * n,
        })

    def test_passes_when_within_tolerance(self):
        """Returns True for a group when achieved stats are within tolerance."""
        cycle = self._make_cycle("A", 30.0, 60)
        targets = {"A": {"mean_speed_kmh": 30.0, "idle_fraction": 0.0}}
        tolerances = {"mean_speed_kmh": 0.1, "idle_fraction": 0.1}
        result = validate_cycle(cycle, targets, tolerances)
        assert result["A"] is True

    def test_fails_when_outside_tolerance(self):
        """Returns False for a group when an achieved stat is outside tolerance."""
        cycle = self._make_cycle("A", 60.0, 60)  # achieved mean ~= 60 km/h
        targets = {"A": {"mean_speed_kmh": 30.0}}
        tolerances = {"mean_speed_kmh": 0.05}  # ±5 %
        result = validate_cycle(cycle, targets, tolerances)
        assert result["A"] is False

    def test_absent_group_fails(self):
        """Group present in targets but absent from cycle is marked False."""
        cycle = self._make_cycle("A", 30.0, 60)
        targets = {"B": {"mean_speed_kmh": 30.0}}
        tolerances = {"mean_speed_kmh": 0.1}
        result = validate_cycle(cycle, targets, tolerances)
        assert result["B"] is False

    def test_multiple_groups_independent(self):
        """Validation is independent per group."""
        cycle = pd.concat([
            self._make_cycle("pass_group", 20.0, 40),
            self._make_cycle("fail_group", 80.0, 40),
        ])
        targets = {
            "pass_group": {"mean_speed_kmh": 20.0},
            "fail_group": {"mean_speed_kmh": 20.0},
        }
        tolerances = {"mean_speed_kmh": 0.05}
        result = validate_cycle(cycle, targets, tolerances)
        assert result["pass_group"] is True
        assert result["fail_group"] is False
