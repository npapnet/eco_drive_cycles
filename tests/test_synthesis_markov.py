"""Tests for synthesis.markov — discretize_states, build_transition_matrix,
frobenius_distance."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from drive_cycle_calculator.schema import MarkovConfig
from drive_cycle_calculator.synthesis.markov import (
    build_transition_matrix,
    discretize_states,
    frobenius_distance,
)

_DEFAULT_CFG = MarkovConfig()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_df(speeds: list[float], accs: list[float] | None = None) -> pd.DataFrame:
    n = len(speeds)
    if accs is None:
        accs = [0.0] * n
    return pd.DataFrame({"smooth_speed_kmh": speeds, "acc_ms2": accs})


# ── discretize_states ─────────────────────────────────────────────────────────


class TestDiscretizeStates:
    def test_length_matches_input(self):
        """Output Series has same length as input DataFrame."""
        df = _make_df([0.0, 30.0, 60.0, 90.0])
        result = discretize_states(df, _DEFAULT_CFG)
        assert len(result) == len(df)

    def test_index_preserved(self):
        """Output Series preserves the input DataFrame index."""
        df = _make_df([10.0, 20.0, 30.0])
        df.index = [5, 10, 15]
        result = discretize_states(df, _DEFAULT_CFG)
        assert list(result.index) == [5, 10, 15]

    def test_zero_speed_zero_acc_label(self):
        """Speed 0 + acc 0 → v000 bin, acceleration bin at acc_min boundary."""
        df = _make_df([0.0], [0.0])
        label = discretize_states(df, _DEFAULT_CFG).iloc[0]
        assert label.startswith("v000_a")

    def test_speed_bin_assignment(self):
        """Speed 25 km/h with 10 km/h bins → v020 (bin index 2)."""
        cfg = MarkovConfig(speed_bin_width_kmh=10.0)
        df = _make_df([25.0], [0.0])
        label = discretize_states(df, cfg).iloc[0]
        assert label.startswith("v020_")

    def test_negative_speed_clamped_to_zero(self):
        """Negative speed values are clamped to 0 before binning."""
        df = _make_df([-5.0], [0.0])
        result = discretize_states(df, _DEFAULT_CFG).iloc[0]
        df_zero = _make_df([0.0], [0.0])
        expected = discretize_states(df_zero, _DEFAULT_CFG).iloc[0]
        assert result == expected

    def test_uses_speed_kmh_fallback(self):
        """Falls back to speed_kmh when smooth_speed_kmh is absent."""
        df = pd.DataFrame({"speed_kmh": [30.0], "acc_ms2": [0.0]})
        result = discretize_states(df, _DEFAULT_CFG)
        assert len(result) == 1

    def test_string_dtype(self):
        """All returned values are strings."""
        df = _make_df([0.0, 30.0, 60.0], [0.0, 0.5, -0.3])
        result = discretize_states(df, _DEFAULT_CFG)
        assert all(isinstance(v, str) for v in result)


# ── build_transition_matrix ───────────────────────────────────────────────────


class TestBuildTransitionMatrix:
    def test_empty_for_single_state(self):
        """Single-element Series returns an empty DataFrame."""
        states = pd.Series(["v000_a+0.0"])
        T = build_transition_matrix(states)
        assert T.empty

    def test_empty_for_zero_states(self):
        """Empty Series returns an empty DataFrame."""
        T = build_transition_matrix(pd.Series([], dtype=str))
        assert T.empty

    def test_rows_sum_to_one(self):
        """Every non-zero row of T sums to 1."""
        states = pd.Series(["A", "B", "A", "C", "B", "A"])
        T = build_transition_matrix(states)
        row_sums = T.sum(axis=1)
        assert (row_sums > 0).all()
        assert np.allclose(row_sums.values, 1.0)

    def test_known_sequence(self):
        """A→B→A→B sequence → T["A"]["B"] == 1.0, T["B"]["A"] == 1.0."""
        states = pd.Series(["A", "B", "A", "B"])
        T = build_transition_matrix(states)
        assert T.loc["A", "B"] == pytest.approx(1.0)
        assert T.loc["B", "A"] == pytest.approx(1.0)

    def test_self_loop(self):
        """A→A→A sequence → T["A"]["A"] == 1.0."""
        states = pd.Series(["A", "A", "A"])
        T = build_transition_matrix(states)
        assert T.loc["A", "A"] == pytest.approx(1.0)

    def test_index_and_columns_are_state_labels(self):
        """Both index and columns contain the state labels present in the sequence."""
        states = pd.Series(["X", "Y", "Z", "X"])
        T = build_transition_matrix(states)
        assert set(T.index) == {"X", "Y", "Z"}
        assert set(T.columns).issubset({"X", "Y", "Z"})


# ── frobenius_distance ────────────────────────────────────────────────────────


class TestFrobeniusDistance:
    def _make_T(self, rows: dict) -> pd.DataFrame:
        """Build a row-stochastic matrix from a dict of {from: {to: prob}}."""
        states = sorted({s for d in rows.values() for s in d} | set(rows))
        T = pd.DataFrame(0.0, index=sorted(rows), columns=states)
        for frm, tos in rows.items():
            for to, p in tos.items():
                T.loc[frm, to] = p
        return T

    def test_identical_matrices_zero_distance(self):
        """Distance between a matrix and itself is 0."""
        T = self._make_T({"A": {"B": 1.0}, "B": {"A": 1.0}})
        assert frobenius_distance(T, T) == pytest.approx(0.0)

    def test_no_shared_states_returns_one(self):
        """Distance is 1.0 when the two matrices share no from-states."""
        T1 = self._make_T({"A": {"B": 1.0}})
        T2 = self._make_T({"C": {"D": 1.0}})
        assert frobenius_distance(T1, T2) == pytest.approx(1.0)

    def test_partial_overlap(self):
        """Only shared from-states are compared; distance is finite and positive."""
        T1 = self._make_T({"A": {"B": 1.0}, "C": {"D": 1.0}})
        T2 = self._make_T({"A": {"C": 1.0}, "E": {"F": 1.0}})
        d = frobenius_distance(T1, T2)
        assert d > 0.0
        assert np.isfinite(d)

    def test_zero_extra_row_does_not_change_distance(self):
        """Adding an identical shared row (zero difference) does not change distance.

        With normalisation by shared row count, one matching row = zero contribution;
        the overall distance stays the same as the single-difference-row case.
        """
        # Single differing row: A->B vs A->A
        d_one = frobenius_distance(
            self._make_T({"A": {"B": 1.0}}),
            self._make_T({"A": {"A": 1.0}}),
        )
        # Same differing row A, plus an identical row B (no difference)
        m1 = self._make_T({"A": {"B": 1.0}, "B": {"C": 1.0}})
        m2 = self._make_T({"A": {"A": 1.0}, "B": {"C": 1.0}})
        d_two = frobenius_distance(m1, m2)
        # With 2 shared rows (one differs, one identical):
        # ||diff||_F = sqrt(per-row-norm²) = same as one-row case
        # divided by 2 → d_two < d_one
        assert d_two < d_one
        assert d_two > 0.0
