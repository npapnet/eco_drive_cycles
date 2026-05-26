"""Tests for MicrotripCollection and KMeansClusterer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from drive_cycle_calculator.clustering import KMeansClusterer
from drive_cycle_calculator.microtrip_collection import MicrotripCollection
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter
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


_SPEEDS: list[float] = [0.0] * 5 + [30.0] * 21 + [0.0] * 4 + [50.0] * 25 + [0.0] * 5


def _make_trip(name: str, speeds: list[float] | None = None) -> Trip:
    return Trip(_make_processed_df(speeds or _SPEEDS), name)


@pytest.fixture
def persisted_collection(tmp_path) -> MicrotripCollection:
    """Two trips × 1 microtrip each, saved to tmp_path/mts/ and loaded back."""
    trips = [_make_trip("trip_a"), _make_trip("trip_b")]
    tc = TripCollection(trips)
    segmenter = MicrotripSegmenter(SegmentationConfig())
    result = segmenter.segment_collection(tc)
    mt_dir = tmp_path / "mts"
    segmenter.export_collection(result, mt_dir)
    return MicrotripCollection.from_parquets(mt_dir)


@pytest.fixture
def bound_collection() -> MicrotripCollection:
    """Non-persisted collection built directly from live Trip objects."""
    trips = [_make_trip("trip_a"), _make_trip("trip_b")]
    tc = TripCollection(trips)
    segmenter = MicrotripSegmenter(SegmentationConfig())
    return MicrotripCollection.from_trip_collection(tc, segmenter)


# ── from_parquets ─────────────────────────────────────────────────────────────


class TestFromParquets:
    def test_length_matches_parquet_count(self, tmp_path):
        """from_parquets() length == number of .parquet files in directory."""
        trips = [_make_trip(f"trip_{i}") for i in range(3)]
        tc = TripCollection(trips)
        segmenter = MicrotripSegmenter(SegmentationConfig())
        result = segmenter.segment_collection(tc)
        mt_dir = tmp_path / "mts"
        segmenter.export_collection(result, mt_dir)

        n_files = len(list(mt_dir.glob("*.parquet")))
        mc = MicrotripCollection.from_parquets(mt_dir)
        assert len(mc) == n_files

    def test_summary_row_count_matches_length(self, persisted_collection):
        """summary has one row per microtrip."""
        mc = persisted_collection
        assert len(mc.summary) == len(mc)

    def test_is_persisted_true(self, persisted_collection):
        """from_parquets() → is_persisted is True."""
        assert persisted_collection.is_persisted is True

    def test_all_paths_are_valid_files(self, persisted_collection):
        """Every mt.path exists on disk."""
        for mt in persisted_collection:
            assert mt.path is not None
            assert mt.path.exists()

    def test_summary_path_column_matches_mt_paths(self, persisted_collection):
        """summary['path'] entries match the actual mt.path values."""
        mc = persisted_collection
        summary_paths = set(mc.summary["path"])
        mt_paths = {str(mt.path) for mt in mc}
        assert summary_paths == mt_paths

    def test_summary_has_metric_columns(self, persisted_collection):
        """summary contains duration_s, distance_m, mean_speed_kmh."""
        cols = set(persisted_collection.summary.columns)
        assert {"duration_s", "distance_m", "mean_speed_kmh"}.issubset(cols)

    def test_summary_csv_extra_columns_merged(self, tmp_path, persisted_collection):
        """summary_csv extra columns (e.g. cluster_id) are merged in."""
        mc = persisted_collection
        aug = mc.summary[["path"]].copy()
        aug["cluster_id"] = range(len(aug))
        csv_path = tmp_path / "aug.csv"
        aug.to_csv(csv_path, index=False)

        # Reload with the summary_csv
        mt_dir = Path(mc.summary["path"].iloc[0]).parent
        mc2 = MicrotripCollection.from_parquets(mt_dir, summary_csv=csv_path)
        assert "cluster_id" in mc2.summary.columns


# ── from_trip_collection ──────────────────────────────────────────────────────


class TestFromTripCollection:
    def test_is_persisted_false(self, bound_collection):
        """from_trip_collection() → is_persisted is False."""
        assert bound_collection.is_persisted is False

    def test_length_and_summary_consistent(self, bound_collection):
        """len() and summary row count are equal."""
        mc = bound_collection
        assert len(mc) == len(mc.summary)

    def test_no_path_set_on_microtrips(self, bound_collection):
        """Non-persisted microtrips have path == None."""
        for mt in bound_collection:
            assert mt.path is None


# ── Container interface ───────────────────────────────────────────────────────


class TestContainerInterface:
    def test_iter_yields_microtrips(self, persisted_collection):
        """Iterating over the collection yields Microtrip objects."""
        from drive_cycle_calculator.microtrip import Microtrip
        for mt in persisted_collection:
            assert isinstance(mt, Microtrip)

    def test_summary_returns_copy(self, persisted_collection):
        """summary property returns a copy; mutating it doesn't affect the collection."""
        mc = persisted_collection
        s = mc.summary
        s["_test"] = 99
        assert "_test" not in mc.summary.columns


# ── rank() ────────────────────────────────────────────────────────────────────


class TestRank:
    def test_rank_returns_score_and_rank_columns(self, persisted_collection):
        """rank() adds 'score' and 'rank' columns to the summary."""
        mc = persisted_collection
        mc._summary["group"] = "A"
        ranked = mc.rank(group_col="group")
        assert "score" in ranked.columns
        assert "rank" in ranked.columns

    def test_rank_1_is_highest_score_in_group(self, tmp_path):
        """The microtrip closest to the group mean gets rank 1."""
        trips = [_make_trip(f"t{i}") for i in range(4)]
        tc = TripCollection(trips)
        segmenter = MicrotripSegmenter(SegmentationConfig())
        result = segmenter.segment_collection(tc)
        mt_dir = tmp_path / "mts"
        segmenter.export_collection(result, mt_dir)
        mc = MicrotripCollection.from_parquets(mt_dir)

        mc._summary["group"] = "X"
        ranked = mc.rank(group_col="group")
        best = ranked[ranked["rank"] == 1].iloc[0]
        assert best["score"] >= ranked["score"].max() - 1e-9

    def test_rank_unknown_group_col_raises(self, persisted_collection):
        """rank() raises ValueError for a group_col not in summary."""
        with pytest.raises(ValueError, match="not found"):
            persisted_collection.rank(group_col="nonexistent_col")


# ── KMeansClusterer ───────────────────────────────────────────────────────────


class TestKMeansClusterer:
    def test_fit_returns_series_of_correct_length(self, persisted_collection):
        """KMeansClusterer.fit(summary) returns a Series with len == len(summary)."""
        mc = persisted_collection
        n = len(mc.summary)
        if n < 2:
            pytest.skip("Need at least 2 microtrips for clustering")
        k = min(2, n)
        labels = KMeansClusterer(n_clusters=k).fit(mc.summary)
        assert isinstance(labels, pd.Series)
        assert len(labels) == n

    def test_fit_returns_integer_labels(self, persisted_collection):
        """Cluster labels are integers."""
        mc = persisted_collection
        n = len(mc.summary)
        if n < 2:
            pytest.skip("Need at least 2 microtrips for clustering")
        k = min(2, n)
        labels = KMeansClusterer(n_clusters=k).fit(mc.summary)
        assert labels.dtype == int or pd.api.types.is_integer_dtype(labels)

    def test_fit_label_count_matches_n_clusters(self, persisted_collection):
        """Number of distinct labels equals n_clusters (when n >= n_clusters)."""
        mc = persisted_collection
        n = len(mc.summary)
        if n < 2:
            pytest.skip("Need at least 2 microtrips for clustering")
        k = min(2, n)
        labels = KMeansClusterer(n_clusters=k).fit(mc.summary)
        assert len(labels.unique()) == k

    def test_fit_index_aligned_with_summary(self, persisted_collection):
        """Label Series index matches summary index."""
        mc = persisted_collection
        n = len(mc.summary)
        if n < 2:
            pytest.skip("Need at least 2 microtrips for clustering")
        k = min(2, n)
        labels = KMeansClusterer(n_clusters=k).fit(mc.summary)
        assert list(labels.index) == list(mc.summary.index)

    def test_fit_with_explicit_features(self, persisted_collection):
        """Explicit feature list is respected."""
        mc = persisted_collection
        n = len(mc.summary)
        if n < 2:
            pytest.skip("Need at least 2 microtrips for clustering")
        k = min(2, n)
        labels = KMeansClusterer(
            n_clusters=k, features=["duration_s", "mean_speed_kmh"]
        ).fit(mc.summary)
        assert len(labels) == n
