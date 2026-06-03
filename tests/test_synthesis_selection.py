"""Tests for synthesis.selection — select_microtrips."""

from __future__ import annotations

import pandas as pd
import pytest

from drive_cycle_calculator.schema import SynthesisSelectionConfig
from drive_cycle_calculator.synthesis.selection import _objective, _seq_stats, select_microtrips

_CFG = SynthesisSelectionConfig(n_trials=20, f_threshold=0.01, random_seed=0)
_WEIGHTS = _CFG.metric_weights
_GLOBAL_T = pd.DataFrame(dtype=float)  # not used in current implementation


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_candidates(n: int, min_dist_per_mt: float = 200.0) -> pd.DataFrame:
    """Build a minimal candidates DataFrame with all required columns."""
    return pd.DataFrame({
        "path": [f"/fake/mt_{i:03d}.parquet" for i in range(n)],
        "duration_s": [30.0] * n,
        "stop_duration_s": [10.0] * n,
        "total_duration_s": [40.0] * n,
        "distance_m": [min_dist_per_mt] * n,
        "mean_speed_kmh": [20.0] * n,
        "idle_fraction": [0.25] * n,
        "speed_95th_kmh": [30.0] * n,
        "rpa": [0.1] * n,
        "markov_distance": [0.1] * n,
    })


def _make_target() -> dict[str, float]:
    return {
        "mean_speed_kmh": 20.0,
        "rpa": 0.1,
        "idle_fraction": 0.25,
        "speed_95th_kmh": 30.0,
    }


# ── _seq_stats ────────────────────────────────────────────────────────────────


class TestSeqStats:
    def test_returns_dict_with_metric_keys(self):
        """_seq_stats returns a dict with mean_speed_kmh, rpa, idle_fraction."""
        df = _make_candidates(2)
        stats = _seq_stats(df)
        assert "mean_speed_kmh" in stats
        assert "rpa" in stats
        assert "idle_fraction" in stats

    def test_empty_for_zero_duration(self):
        """Returns empty dict when total duration is zero."""
        df = _make_candidates(1)
        df["total_duration_s"] = 0.0
        assert _seq_stats(df) == {}

    def test_empty_for_zero_distance(self):
        """Returns empty dict when total distance is zero."""
        df = _make_candidates(1)
        df["distance_m"] = 0.0
        assert _seq_stats(df) == {}


# ── _objective ────────────────────────────────────────────────────────────────


class TestObjective:
    def test_returns_finite_float_for_valid_input(self):
        """Objective returns a finite float for well-formed inputs."""
        df = _make_candidates(3)
        target = _make_target()
        F = _objective(df, target, _WEIGHTS)
        assert isinstance(F, float)
        import math
        assert math.isfinite(F)

    def test_zero_when_stats_match_target(self):
        """Objective is 0 when achieved stats equal the targets exactly."""
        df = _make_candidates(2)
        target = _make_target()
        F = _objective(df, target, _WEIGHTS)
        assert F == pytest.approx(0.0)

    def test_positive_when_stats_differ(self):
        """Objective is positive when achieved stats differ from targets."""
        df = _make_candidates(2)
        df["mean_speed_kmh"] = 50.0  # target is 20.0
        target = _make_target()
        F = _objective(df, target, _WEIGHTS)
        assert F > 0.0

    def test_inf_for_degenerate_sequence(self):
        """Returns inf when sequence stats cannot be computed."""
        df = _make_candidates(1)
        df["total_duration_s"] = 0.0
        F = _objective(df, _make_target(), _WEIGHTS)
        import math
        assert math.isinf(F)


# ── select_microtrips ─────────────────────────────────────────────────────────


class TestSelectMicrotrips:
    def test_returns_list_of_strings(self):
        """select_microtrips returns a list of strings."""
        cands = _make_candidates(4)
        result = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=200.0
        )
        assert isinstance(result, list)
        assert all(isinstance(p, str) for p in result)

    def test_min_distance_constraint(self):
        """Total distance of selected sequence meets min_distance_m."""
        dist_per_mt = 150.0
        cands = _make_candidates(5, min_dist_per_mt=dist_per_mt)
        min_dist = 400.0
        result = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=min_dist
        )
        total_dist = len(result) * dist_per_mt
        assert total_dist >= min_dist

    def test_paths_come_from_candidates(self):
        """All returned paths exist in the candidates path column."""
        cands = _make_candidates(5)
        result = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=100.0
        )
        assert all(p in cands["path"].values for p in result)

    def test_empty_candidates_raises(self):
        """Raises ValueError when candidates is empty."""
        with pytest.raises(ValueError, match="No candidates"):
            select_microtrips(
                pd.DataFrame(), "A", _make_target(), _GLOBAL_T, _CFG
            )

    def test_missing_path_column_raises(self):
        """Raises ValueError when candidates has no path column."""
        cands = _make_candidates(3).drop(columns=["path"])
        with pytest.raises(ValueError, match="path"):
            select_microtrips(
                cands, "A", _make_target(), _GLOBAL_T, _CFG
            )

    def test_single_candidate_selected(self):
        """Works with a single candidate (reuse is unavoidable)."""
        cands = _make_candidates(1)
        result = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=200.0
        )
        assert len(result) >= 1

    def test_rng_reproducibility(self):
        """Same seed produces the same sequence."""
        import numpy as np
        cands = _make_candidates(6)
        r1 = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=300.0,
            rng=np.random.default_rng(42),
        )
        r2 = select_microtrips(
            cands, "A", _make_target(), _GLOBAL_T, _CFG, min_distance_m=300.0,
            rng=np.random.default_rng(42),
        )
        assert r1 == r2
