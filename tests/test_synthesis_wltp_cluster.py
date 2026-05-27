"""Tests for synthesis.wltp, synthesis.cluster, and end-to-end WLTP/cluster synthesis."""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from drive_cycle_calculator.microtrip_collection import MicrotripCollection
from drive_cycle_calculator.schema import (
    ClusterSynthesisConfig,
    SegmentationConfig,
    WLTPSynthesisConfig,
)
from drive_cycle_calculator.segmentation import MicrotripSegmenter
from drive_cycle_calculator.synthesis import synthesize
from drive_cycle_calculator.synthesis.cluster import assign_clusters
from drive_cycle_calculator.synthesis.wltp import WLTP_PHASE_BOUNDS, assign_wltp_phases
from drive_cycle_calculator.trip import Trip
from drive_cycle_calculator.trip_collection import TripCollection


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


def _make_trip(name: str, speeds: list[float]) -> Trip:
    return Trip(_make_processed_df(speeds), name)


def _summary(max_speeds: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"max_speed_kmh": max_speeds})


# ── assign_wltp_phases ────────────────────────────────────────────────────────


class TestAssignWltpPhases:
    def test_low_phase(self):
        result = assign_wltp_phases(_summary([0.0, 30.0, 56.5]))
        assert list(result) == ["Low", "Low", "Low"]

    def test_med_phase(self):
        result = assign_wltp_phases(_summary([56.501, 76.6]))
        assert list(result) == ["Med", "Med"]

    def test_high_phase(self):
        result = assign_wltp_phases(_summary([76.601, 97.4]))
        assert list(result) == ["High", "High"]

    def test_xhigh_phase(self):
        result = assign_wltp_phases(_summary([97.401, 130.0]))
        assert list(result) == ["xHigh", "xHigh"]

    def test_boundary_values(self):
        # Lower bound exclusive, upper bound inclusive for each phase
        speeds = [56.5, 56.501, 76.6, 76.601, 97.4, 97.401]
        result = assign_wltp_phases(_summary(speeds))
        assert list(result) == ["Low", "Med", "Med", "High", "High", "xHigh"]

    def test_zero_speed_is_low(self):
        assert assign_wltp_phases(_summary([0.0])).iloc[0] == "Low"

    def test_missing_column_raises(self):
        df = pd.DataFrame({"mean_speed_kmh": [30.0]})
        with pytest.raises(KeyError, match="max_speed_kmh"):
            assign_wltp_phases(df)

    def test_index_preserved(self):
        df = _summary([30.0, 80.0])
        df.index = pd.Index([10, 20])
        result = assign_wltp_phases(df)
        assert list(result.index) == [10, 20]

    def test_phase_bounds_constant_has_all_phases(self):
        assert set(WLTP_PHASE_BOUNDS.keys()) == {"Low", "Med", "High", "xHigh"}


# ── assign_clusters ───────────────────────────────────────────────────────────


class TestAssignClusters:
    def test_returns_series_from_column(self):
        df = pd.DataFrame({"cluster_id": [0, 1, 0, 2]})
        result = assign_clusters(df)
        assert list(result) == ["0", "1", "0", "2"]

    def test_values_are_strings(self):
        df = pd.DataFrame({"cluster_id": [0, 1]})
        result = assign_clusters(df)
        assert all(isinstance(v, str) for v in result)

    def test_custom_column_name(self):
        df = pd.DataFrame({"my_group": ["A", "B", "A"]})
        result = assign_clusters(df, cluster_col="my_group")
        assert list(result) == ["A", "B", "A"]

    def test_missing_column_raises(self):
        df = pd.DataFrame({"mean_speed_kmh": [30.0]})
        with pytest.raises(KeyError, match="cluster_id"):
            assign_clusters(df)

    def test_index_preserved(self):
        df = pd.DataFrame({"cluster_id": ["A", "B"]}, index=[5, 10])
        result = assign_clusters(df)
        assert list(result.index) == [5, 10]


# ── WLTPSynthesisConfig phase-name validation ─────────────────────────────────


class TestWltpConfigValidation:
    def test_valid_phase_names_pass(self):
        cfg = WLTPSynthesisConfig(phase_min_distance_m={"Low": 500.0, "Med": 400.0})
        assert "Low" in cfg.phase_min_distance_m

    def test_unknown_phase_raises(self):
        with pytest.raises(ValidationError, match="Unknown WLTP phase"):
            WLTPSynthesisConfig(phase_min_distance_m={"UnknownPhase": 500.0})

    def test_partial_subset_of_phases_is_valid(self):
        cfg = WLTPSynthesisConfig(phase_min_distance_m={"Low": 300.0})
        assert cfg.phase_min_distance_m == {"Low": 300.0}

    def test_all_four_phases_valid(self):
        cfg = WLTPSynthesisConfig(
            phase_min_distance_m={"Low": 100.0, "Med": 100.0, "High": 100.0, "xHigh": 100.0}
        )
        assert len(cfg.phase_min_distance_m) == 4


# ── End-to-end synthesis ──────────────────────────────────────────────────────


@pytest.fixture
def low_phase_collection(tmp_path) -> MicrotripCollection:
    """Persisted collection — microtrips all in the Low WLTP phase (max_speed=30)."""
    # 5 idle + 60 motion at 30 km/h ≈ 500 m + 5 trailing stop
    speeds = [0.0] * 5 + [30.0] * 60 + [0.0] * 5
    trips = [_make_trip(f"trip_{i}", speeds) for i in range(3)]
    tc = TripCollection(trips)
    segmenter = MicrotripSegmenter(SegmentationConfig())
    result = segmenter.segment_collection(tc)
    mt_dir = tmp_path / "mts"
    segmenter.export_collection(result, mt_dir)
    return MicrotripCollection.from_parquets(mt_dir)


class TestEndToEnd:
    def test_all_microtrips_assigned_to_low(self, low_phase_collection):
        phases = assign_wltp_phases(low_phase_collection.summary)
        assert set(phases.unique()) == {"Low"}

    def test_wltp_synthesize_returns_dataframe(self, low_phase_collection):
        mc = low_phase_collection
        assignments = assign_wltp_phases(mc.summary)
        config = WLTPSynthesisConfig(
            phase_min_distance_m={"Low": 100.0},
            inter_phase_idle_s=5,
        )
        result = synthesize(mc, assignments, config)
        assert isinstance(result, pd.DataFrame)
        assert {"t_s", "speed_kmh", "group"}.issubset(result.columns)

    def test_wltp_result_contains_low_group(self, low_phase_collection):
        mc = low_phase_collection
        assignments = assign_wltp_phases(mc.summary)
        config = WLTPSynthesisConfig(
            phase_min_distance_m={"Low": 100.0},
            inter_phase_idle_s=5,
        )
        result = synthesize(mc, assignments, config)
        non_idle = set(result.loc[result["group"] != "idle", "group"].unique())
        assert non_idle == {"Low"}

    def test_cluster_synthesize_returns_dataframe(self, low_phase_collection):
        mc = low_phase_collection
        # Manual assignment: all microtrips in cluster "0"
        assignments = pd.Series("0", index=mc.summary.index)
        config = ClusterSynthesisConfig(
            cluster_min_distance_m=100.0,
            inter_cluster_idle_s=5,
        )
        result = synthesize(mc, assignments, config)
        assert isinstance(result, pd.DataFrame)
        non_idle = set(result.loc[result["group"] != "idle", "group"].unique())
        assert non_idle == {"0"}

    def test_non_persisted_collection_raises(self):
        speeds = [0.0] * 5 + [30.0] * 60 + [0.0] * 5
        trips = [_make_trip("trip_a", speeds)]
        tc = TripCollection(trips)
        segmenter = MicrotripSegmenter(SegmentationConfig())
        mc = MicrotripCollection.from_trip_collection(tc, segmenter)
        assignments = pd.Series("Low", index=mc.summary.index)
        config = WLTPSynthesisConfig(phase_min_distance_m={"Low": 100.0})
        with pytest.raises(ValueError, match="persisted"):
            synthesize(mc, assignments, config)
