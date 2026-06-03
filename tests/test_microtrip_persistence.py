"""Tests for Microtrip persistence (to_parquet / from_parquet)."""

from __future__ import annotations

import gc
from pathlib import Path

import pandas as pd
import pytest

from drive_cycle_calculator.microtrip import Microtrip
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter
from drive_cycle_calculator.trip import Trip


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_processed_df(speeds: list[float]) -> pd.DataFrame:
    """Minimal processed DataFrame from a speed list (1 sample/second)."""
    n = len(speeds)
    return pd.DataFrame({
        "elapsed_s": [float(i) for i in range(n)],
        "smooth_speed_kmh": speeds,
        "acc_ms2": [0.0] * n,
        "speed_kmh": speeds,
        "co2_g_per_km": [120.0 if s > 0 else 50.0 for s in speeds],
        "engine_load_pct": [50.0 if s > 0 else 20.0 for s in speeds],
        "fuel_flow_lph": [2.0 if s > 0 else 0.5 for s in speeds],
    })


# 1 initial stop + 21 motion (30 km/h) + 4 stop + 25 motion (50 km/h) + 5 stop
_SPEEDS: list[float] = [0.0] * 5 + [30.0] * 21 + [0.0] * 4 + [50.0] * 25 + [0.0] * 5


@pytest.fixture
def two_microtrips(tmp_path):
    """Trip with two microtrips; returns (trip, [mt1, mt2])."""
    trip = Trip(_make_processed_df(_SPEEDS), "test_trip", parquet_id="abc123")
    trip._path = tmp_path / "trip.parquet"
    segmenter = MicrotripSegmenter(SegmentationConfig())
    mts = segmenter.segment(trip)
    assert len(mts) == 2, f"Expected 2 microtrips, got {len(mts)}"
    return trip, mts


# ── Round-trip ────────────────────────────────────────────────────────────────


class TestMicrotripRoundtrip:
    def test_roundtrip_preserves_samples_shape(self, tmp_path, two_microtrips):
        """to_parquet → from_parquet: samples row count and columns unchanged."""
        _, (mt, _) = two_microtrips
        original_shape = mt.samples.shape
        original_cols = list(mt.samples.columns)

        dest = tmp_path / "mt0.parquet"
        mt.to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)

        assert loaded.samples.shape == original_shape
        assert list(loaded.samples.columns) == original_cols

    def test_roundtrip_preserves_stop_samples_shape(self, tmp_path, two_microtrips):
        """to_parquet → from_parquet: stop_samples row count unchanged."""
        _, (mt, _) = two_microtrips
        original_stop_shape = mt.stop_samples.shape

        dest = tmp_path / "mt0.parquet"
        mt.to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)

        assert loaded.stop_samples.shape == original_stop_shape

    def test_roundtrip_preserves_speed_values(self, tmp_path, two_microtrips):
        """Speed values in samples are identical after round-trip."""
        _, (mt, _) = two_microtrips
        dest = tmp_path / "mt0.parquet"
        mt.to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)

        pd.testing.assert_series_equal(
            mt.samples["smooth_speed_kmh"].reset_index(drop=True),
            loaded.samples["smooth_speed_kmh"].reset_index(drop=True),
        )

    def test_roundtrip_preserves_traceability_fields(self, tmp_path, two_microtrips):
        """trip_file and parquet_id survive the round-trip."""
        trip, (mt, _) = two_microtrips
        dest = tmp_path / "mt0.parquet"
        mt.to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)

        assert loaded.parquet_id == mt.parquet_id
        assert loaded.trip_file == mt.trip_file

    def test_to_parquet_sets_path(self, tmp_path, two_microtrips):
        """to_parquet() sets mt.path to the destination."""
        _, (mt, _) = two_microtrips
        dest = tmp_path / "mt0.parquet"
        assert mt.path is None
        mt.to_parquet(dest)
        assert mt.path == dest

    def test_from_parquet_sets_path(self, tmp_path, two_microtrips):
        """from_parquet() sets mt.path to the source file."""
        _, (mt, _) = two_microtrips
        dest = tmp_path / "mt0.parquet"
        mt.to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)
        assert loaded.path == dest


# ── D1: bound-mode GC behaviour ───────────────────────────────────────────────


class TestBoundModeGC:
    def test_samples_raises_after_trip_gc(self, tmp_path):
        """Bound microtrip raises RuntimeError on samples access after parent GC."""
        trip = Trip(_make_processed_df(_SPEEDS), "trip_gc")
        segmenter = MicrotripSegmenter(SegmentationConfig())
        mts = segmenter.segment(trip)
        assert mts, "Need at least one microtrip"
        mt = mts[0]

        del trip
        gc.collect()

        with pytest.raises(RuntimeError, match="garbage-collected"):
            _ = mt.samples

    def test_standalone_does_not_raise_after_no_parent(self, tmp_path):
        """Standalone microtrip (from_parquet) works without any parent Trip."""
        trip = Trip(_make_processed_df(_SPEEDS), "trip_standalone")
        segmenter = MicrotripSegmenter(SegmentationConfig())
        mts = segmenter.segment(trip)
        assert mts

        dest = tmp_path / "mt.parquet"
        mts[0].to_parquet(dest)
        loaded = Microtrip.from_parquet(dest)

        del trip, mts
        gc.collect()

        # Must not raise — _df is set, no weakref needed
        samples = loaded.samples
        assert len(samples) > 0
