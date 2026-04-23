"""Tests for microtrip segmentation.

Covers: detect_boundaries, build_microtrips, Trip.segment, Microtrip data-access
properties, and traceability fields.

All tests in the logic-testing classes are expected to fail with
NotImplementedError at this stage — that is the correct failure mode.
Tests in TestMicrotripModelStructure cover the skeleton only and pass immediately.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from drive_cycle_calculator.microtrip import Microtrip
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import (
    SegmentBoundary,
    build_microtrips,
    detect_boundaries,
)
from drive_cycle_calculator.trip import Trip


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_df(speeds: list[float], sample_rate_s: float = 1.0) -> pd.DataFrame:
    """Minimal processed DataFrame from a speed list at uniform sample rate."""
    n = len(speeds)
    elapsed = [i * sample_rate_s for i in range(n)]
    return pd.DataFrame(
        {
            "elapsed_s": elapsed,
            "smooth_speed_kmh": speeds,
            "acc_ms2": [0.0] * n,
            "speed_kmh": speeds,
            "co2_g_per_km": [0.0] * n,
            "engine_load_pct": [0.0] * n,
            "fuel_flow_lph": [0.0] * n,
        }
    )


# ── Synthetic two-stop speed series (1 sample / second) ──────────────────────
#
# idx   0– 4 : speed =  0 km/h  (initial stop,       5 samples)
# idx   5–25 : speed = 30 km/h  (MT1 motion,        21 samples)
# idx  26–29 : speed =  0 km/h  (MT1 trailing stop,  4 samples, elapsed 26–29)
# idx  30–54 : speed = 50 km/h  (MT2 motion,        25 samples)
# idx  55–59 : speed =  0 km/h  (MT2 trailing stop,  5 samples, elapsed 55–59)
#
# Hand-calculated expected values:
#   MT1: 21 motion samples @ 30 km/h, stop_duration_after = 29 − 26 = 3 s
#   MT2: 25 motion samples @ 50 km/h, stop_duration_after = 59 − 55 = 4 s

_TWO_STOP_SPEEDS: list[float] = (
    [0.0] * 5
    + [30.0] * 21
    + [0.0] * 4
    + [50.0] * 25
    + [0.0] * 5
)

# Expected half-open iloc indices [start:end) matching Microtrip / SegmentBoundary spec
_MT1_MOTION_START, _MT1_MOTION_END = 5, 26    # iloc[5:26]  → 21 samples
_MT1_STOP_START,   _MT1_STOP_END   = 26, 30   # iloc[26:30] →  4 samples
_MT2_MOTION_START, _MT2_MOTION_END = 30, 55   # iloc[30:55] → 25 samples
_MT2_STOP_START,   _MT2_STOP_END   = 55, 60   # iloc[55:60] →  5 samples


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def seg_config() -> SegmentationConfig:
    """Lenient config — lower thresholds than production defaults for compact fixtures."""
    return SegmentationConfig(
        stop_threshold_kmh=2.0,
        stop_min_duration_s=2.0,
        microtrip_min_duration_s=10.0,
        microtrip_min_distance_m=10.0,
    )


@pytest.fixture
def two_stop_trip(tmp_path) -> Trip:
    df = _make_df(_TWO_STOP_SPEEDS)
    trip = Trip(df=df, name="two_stop", stop_threshold_kmh=2.0, parquet_id="abc123")
    trip._path = tmp_path / "t20230101-120000-60-abc123.parquet"
    return trip


# ── Microtrip model structure — expected to PASS immediately ──────────────────


class TestMicrotripModelStructure:
    """Smoke-tests for the Pydantic skeleton. No segmentation logic required."""

    def test_microtrip_instantiation_and_fields(self):
        mt = Microtrip(
            trip_file=Path("t.parquet"),
            parquet_id="abc123",
            start_idx=5,
            end_idx=26,
            stop_start_idx=26,
            stop_end_idx=30,
        )
        assert mt.trip_file == Path("t.parquet")
        assert mt.parquet_id == "abc123"
        assert mt.start_idx == 5
        assert mt.end_idx == 26
        assert mt.stop_start_idx == 26
        assert mt.stop_end_idx == 30

    def test_model_dump_excludes_trip_ref(self):
        mt = Microtrip(
            trip_file=Path("t.parquet"),
            parquet_id="abc123",
            start_idx=0,
            end_idx=10,
            stop_start_idx=10,
            stop_end_idx=15,
        )
        d = mt.model_dump()
        assert "_trip_ref" not in d
        assert "trip_file" in d
        assert "parquet_id" in d

    def test_segmentation_config_defaults(self):
        cfg = SegmentationConfig()
        assert cfg.stop_threshold_kmh == 2.0
        assert cfg.stop_min_duration_s == 1.0
        assert cfg.microtrip_min_duration_s == 15.0
        assert cfg.microtrip_min_distance_m == 50.0

    def test_segmentation_config_floor_validator(self):
        with pytest.raises(ValueError, match="5 s floor"):
            SegmentationConfig(microtrip_min_duration_s=4.9)

    def test_segment_boundary_fields(self):
        b = SegmentBoundary(
            motion_start_idx=0,
            motion_end_idx=10,
            stop_start_idx=10,
            stop_end_idx=15,
        )
        assert b.motion_start_idx == 0
        assert b.motion_end_idx == 10
        assert b.stop_start_idx == 10
        assert b.stop_end_idx == 15

    def test_trip_has_parquet_id(self):
        trip = Trip(df=_make_df([30.0] * 5), name="t", parquet_id="xyz999")
        assert trip.parquet_id == "xyz999"

    def test_trip_parquet_id_default_empty(self):
        trip = Trip(df=_make_df([30.0] * 5), name="t")
        assert trip.parquet_id == ""


# ── 1. Basic segmentation — expected to FAIL with NotImplementedError ─────────


class TestBasicSegmentation:

    def test_two_stop_trip_produces_two_microtrips(self, two_stop_trip, seg_config):
        microtrips = two_stop_trip.segment(seg_config)
        assert len(microtrips) == 2

    def test_detect_boundaries_finds_two_boundaries(self, seg_config):
        speed = pd.Series(_TWO_STOP_SPEEDS)
        boundaries = detect_boundaries(speed, seg_config)
        assert len(boundaries) == 2

    def test_mt1_boundary_motion_indices(self, seg_config):
        speed = pd.Series(_TWO_STOP_SPEEDS)
        b = detect_boundaries(speed, seg_config)[0]
        assert b.motion_start_idx == _MT1_MOTION_START
        assert b.motion_end_idx == _MT1_MOTION_END

    def test_mt1_boundary_stop_indices(self, seg_config):
        speed = pd.Series(_TWO_STOP_SPEEDS)
        b = detect_boundaries(speed, seg_config)[0]
        assert b.stop_start_idx == _MT1_STOP_START
        assert b.stop_end_idx == _MT1_STOP_END

    def test_mt2_boundary_motion_indices(self, seg_config):
        speed = pd.Series(_TWO_STOP_SPEEDS)
        b = detect_boundaries(speed, seg_config)[1]
        assert b.motion_start_idx == _MT2_MOTION_START
        assert b.motion_end_idx == _MT2_MOTION_END

    def test_mt2_boundary_stop_indices(self, seg_config):
        speed = pd.Series(_TWO_STOP_SPEEDS)
        b = detect_boundaries(speed, seg_config)[1]
        assert b.stop_start_idx == _MT2_STOP_START
        assert b.stop_end_idx == _MT2_STOP_END

    def test_microtrips_ordered_by_start_idx(self, two_stop_trip, seg_config):
        microtrips = two_stop_trip.segment(seg_config)
        starts = [mt.start_idx for mt in microtrips]
        assert starts == sorted(starts)

    def test_build_microtrips_uses_detect_output(self, two_stop_trip, seg_config):
        """build_microtrips() on pre-computed boundaries returns the correct count."""
        speed = pd.Series(_TWO_STOP_SPEEDS)
        boundaries = detect_boundaries(speed, seg_config)
        microtrips = build_microtrips(two_stop_trip, boundaries, seg_config)
        assert len(microtrips) == 2


# ── 2. Boundary conditions — expected to FAIL with NotImplementedError ────────


class TestBoundaryConditions:

    def test_all_stop_trip_returns_empty(self, seg_config):
        trip = Trip(df=_make_df([0.0] * 30), name="all_stop")
        assert trip.segment(seg_config) == []

    def test_all_stop_detect_boundaries_returns_empty(self, seg_config):
        assert detect_boundaries(pd.Series([0.0] * 30), seg_config) == []

    def test_no_stop_trip_returns_empty(self, seg_config):
        # No trailing stop → no microtrip is closed
        trip = Trip(df=_make_df([30.0] * 30), name="no_stop")
        assert trip.segment(seg_config) == []

    def test_no_stop_detect_boundaries_returns_empty(self, seg_config):
        assert detect_boundaries(pd.Series([30.0] * 30), seg_config) == []

    def test_empty_series_returns_empty(self, seg_config):
        assert detect_boundaries(pd.Series([], dtype=float), seg_config) == []

    def test_segment_below_min_duration_filtered_out(self, seg_config):
        # 1 motion sample → total segment = 3 s < microtrip_min_duration_s=10 s
        speeds = [0.0, 0.0, 30.0, 0.0, 0.0]
        trip = Trip(df=_make_df(speeds), name="single_sample")
        assert trip.segment(seg_config) == []

    def test_unconfirmed_stop_does_not_split_microtrip(self, seg_config):
        # 1-sample speed dip (1 s < stop_min_duration_s=2 s) is not a confirmed stop.
        # Both motion blocks are contiguous → 1 microtrip, not 2.
        speeds = [0.0] * 5 + [30.0] * 20 + [0.0] * 1 + [30.0] * 20 + [0.0] * 5
        trip = Trip(df=_make_df(speeds), name="short_dip")
        assert len(trip.segment(seg_config)) == 1


# ── 3. Traceability — expected to FAIL with NotImplementedError ───────────────


class TestTraceability:

    def test_microtrip_trip_file_matches_parent(self, two_stop_trip, seg_config):
        microtrips = two_stop_trip.segment(seg_config)
        assert all(mt.trip_file == two_stop_trip.file for mt in microtrips)

    def test_microtrip_parquet_id_matches_parent(self, two_stop_trip, seg_config):
        microtrips = two_stop_trip.segment(seg_config)
        assert all(mt.parquet_id == two_stop_trip.parquet_id for mt in microtrips)

    def test_microtrips_serialisable_without_weakref(self, two_stop_trip, seg_config):
        """model_dump() on a live microtrip must not include the weakref."""
        microtrips = two_stop_trip.segment(seg_config)
        for mt in microtrips:
            d = mt.model_dump()
            assert "_trip_ref" not in d
            assert "trip_file" in d
            assert "parquet_id" in d

    def test_bind_establishes_data_access(self, two_stop_trip):
        """After bind(), samples must be accessible (no RuntimeError)."""
        mt = Microtrip(
            trip_file=Path("dummy.parquet"),
            parquet_id="abc123",
            start_idx=_MT1_MOTION_START,
            end_idx=_MT1_MOTION_END,
            stop_start_idx=_MT1_STOP_START,
            stop_end_idx=_MT1_STOP_END,
        )
        mt.bind(two_stop_trip)
        _ = mt.samples  # must not raise after a successful bind


# ── 4. Per-microtrip metrics — expected to FAIL with NotImplementedError ──────


class TestMicrotripMetrics:
    """
    Unit-tests Microtrip.samples, .stop_samples, and .stop_duration_after using
    pre-constructed objects, bypassing detect_boundaries / build_microtrips.

    Hand-calculated expected values
    ────────────────────────────────
    MT1 — motion iloc[5:26], stop iloc[26:30]
      samples : 21 rows, smooth_speed_kmh=30.0, elapsed_s 5..25
      stop     :  4 rows, smooth_speed_kmh= 0.0, elapsed_s 26..29
      stop_duration_after = 29 − 26 = 3 s

    MT2 — motion iloc[30:55], stop iloc[55:60]
      samples : 25 rows, smooth_speed_kmh=50.0, elapsed_s 30..54
      stop     :  5 rows, smooth_speed_kmh= 0.0, elapsed_s 55..59
      stop_duration_after = 59 − 55 = 4 s
    """

    @pytest.fixture
    def mt1(self, two_stop_trip) -> Microtrip:
        mt = Microtrip(
            trip_file=Path("dummy.parquet"),
            parquet_id="abc123",
            start_idx=_MT1_MOTION_START,
            end_idx=_MT1_MOTION_END,
            stop_start_idx=_MT1_STOP_START,
            stop_end_idx=_MT1_STOP_END,
        )
        mt.bind(two_stop_trip)
        return mt

    @pytest.fixture
    def mt2(self, two_stop_trip) -> Microtrip:
        mt = Microtrip(
            trip_file=Path("dummy.parquet"),
            parquet_id="abc123",
            start_idx=_MT2_MOTION_START,
            end_idx=_MT2_MOTION_END,
            stop_start_idx=_MT2_STOP_START,
            stop_end_idx=_MT2_STOP_END,
        )
        mt.bind(two_stop_trip)
        return mt

    # — samples —

    def test_mt1_samples_row_count(self, mt1):
        assert len(mt1.samples) == 21

    def test_mt1_samples_mean_speed(self, mt1):
        assert mt1.samples["smooth_speed_kmh"].mean() == pytest.approx(30.0)

    def test_mt1_samples_elapsed_first(self, mt1):
        assert mt1.samples["elapsed_s"].iloc[0] == pytest.approx(5.0)

    def test_mt1_samples_elapsed_last(self, mt1):
        assert mt1.samples["elapsed_s"].iloc[-1] == pytest.approx(25.0)

    def test_mt2_samples_row_count(self, mt2):
        assert len(mt2.samples) == 25

    def test_mt2_samples_mean_speed(self, mt2):
        assert mt2.samples["smooth_speed_kmh"].mean() == pytest.approx(50.0)

    # — stop_samples —

    def test_mt1_stop_samples_row_count(self, mt1):
        assert len(mt1.stop_samples) == 4

    def test_mt1_stop_samples_speed_zero(self, mt1):
        assert (mt1.stop_samples["smooth_speed_kmh"] == 0.0).all()

    def test_mt1_stop_samples_elapsed_first(self, mt1):
        assert mt1.stop_samples["elapsed_s"].iloc[0] == pytest.approx(26.0)

    def test_mt2_stop_samples_row_count(self, mt2):
        assert len(mt2.stop_samples) == 5

    # — stop_duration_after —

    def test_mt1_stop_duration_after(self, mt1):
        # elapsed_s at stop idx 26..29 → 29 − 26 = 3 s
        assert mt1.stop_duration_after == pytest.approx(3.0)

    def test_mt2_stop_duration_after(self, mt2):
        # elapsed_s at stop idx 55..59 → 59 − 55 = 4 s
        assert mt2.stop_duration_after == pytest.approx(4.0)
