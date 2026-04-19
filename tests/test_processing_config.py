"""Tests for ProcessingConfig and DEFAULT_CONFIG."""

from __future__ import annotations

import pandas as pd
import pytest

from drive_cycle_calculator.processing_config import (
    DEFAULT_CONFIG,
    ProcessingConfig,
)


def _make_curated_df(n: int = 20, speed_kmh: float = 36.0) -> pd.DataFrame:
    """Minimal curated DataFrame with proper timestamp GPS Time."""
    timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
    return pd.DataFrame(
        {
            "GPS Time": timestamps,
            "Speed (OBD)(km/h)": [speed_kmh] * n,
            "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
        }
    )


class TestProcessingConfigApply:
    def test_output_columns_exact(self):
        """apply() produces exactly the expected output columns — no extras."""
        config = ProcessingConfig()
        result = config.apply(_make_curated_df())
        expected = {
            "elapsed_s",
            "smooth_speed_kmh",
            "acc_ms2",
            "speed_kmh",
            "co2_g_per_km",
            "engine_load_pct",
            "fuel_flow_lph",
        }
        assert set(result.columns) == expected

    def test_no_speed_ms_column(self):
        """apply() must NOT produce speed_ms — it was removed as redundant."""
        result = ProcessingConfig().apply(_make_curated_df())
        assert "speed_ms" not in result.columns

    def test_no_acceleration_ms2_deceleration_ms2(self):
        """apply() must NOT produce split acceleration columns — acc_ms2 is full signed."""
        result = ProcessingConfig().apply(_make_curated_df())
        assert "acceleration_ms2" not in result.columns
        assert "deceleration_ms2" not in result.columns

    def test_no_gps_time_column(self):
        """GPS Time is consumed to produce elapsed_s and must not appear in output."""
        result = ProcessingConfig().apply(_make_curated_df())
        assert "GPS Time" not in result.columns

    def test_different_windows_produce_different_smooth_speed(self):
        """window=4 and window=8 produce different smooth_speed_kmh values."""
        # Use varying speed to make the difference visible
        n = 30
        timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
        speeds = [float(i % 5) * 10.0 for i in range(n)]  # varying
        df = pd.DataFrame(
            {
                "GPS Time": timestamps,
                "Speed (OBD)(km/h)": speeds,
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
            }
        )
        result4 = ProcessingConfig(window=4).apply(df)
        result8 = ProcessingConfig(window=8).apply(df)
        # At least some rows should differ (ignoring NaNs from window edges)
        diff = (result4["smooth_speed_kmh"] - result8["smooth_speed_kmh"]).dropna().abs()
        assert diff.sum() > 0.0

    def test_acc_ms2_is_signed(self):
        """acc_ms2 must contain both positive and negative values for varying speed."""
        n = 30
        timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
        speeds = [0.0, 10.0, 20.0, 30.0, 20.0, 10.0, 0.0] * 5  # accel + decel
        df = pd.DataFrame(
            {
                "GPS Time": timestamps[:n],
                "Speed (OBD)(km/h)": speeds[:n],
                "CO\u2082 in g/km (Average)(g/km)": [120.0] * n,
                "Engine Load(%)": [50.0] * n,
                "Fuel flow rate/hour(l/hr)": [2.0] * n,
            }
        )
        result = ProcessingConfig(window=2).apply(df)
        acc = result["acc_ms2"].dropna()
        assert (acc > 0).any(), "Expected some positive acceleration values"
        assert (acc < 0).any(), "Expected some negative (deceleration) values"

    def test_elapsed_s_starts_at_zero(self):
        """elapsed_s first valid value should be 0.0 (relative to first timestamp)."""
        result = ProcessingConfig().apply(_make_curated_df())
        first = result["elapsed_s"].dropna().iloc[0]
        assert first == pytest.approx(0.0)

    def test_passthrough_columns_preserved(self):
        """co2, engine_load, fuel_flow values are preserved from input."""
        df = _make_curated_df()
        result = ProcessingConfig().apply(df)
        assert result["co2_g_per_km"].dropna().iloc[0] == pytest.approx(120.0)
        assert result["engine_load_pct"].dropna().iloc[0] == pytest.approx(50.0)
        assert result["fuel_flow_lph"].dropna().iloc[0] == pytest.approx(2.0)

    def test_missing_required_column_raises(self):
        """apply() raises ValueError with the offending column names when input is incomplete."""
        df = _make_curated_df().drop(columns=["Engine Load(%)", "Fuel flow rate/hour(l/hr)"])
        with pytest.raises(ValueError, match="Engine Load"):
            ProcessingConfig().apply(df)



class TestProcessingConfigHash:
    def test_same_config_same_hash(self):
        """Two configs with identical fields produce the same hash."""
        h1 = ProcessingConfig(window=4, stop_threshold_kmh=2.0).config_hash
        h2 = ProcessingConfig(window=4, stop_threshold_kmh=2.0).config_hash
        assert h1 == h2

    def test_different_window_different_hash(self):
        """Different window values produce different hashes."""
        h4 = ProcessingConfig(window=4).config_hash
        h8 = ProcessingConfig(window=8).config_hash
        assert h4 != h8

    def test_hash_is_eight_chars(self):
        """config_hash is the first 8 hex characters of an md5."""
        h = ProcessingConfig().config_hash
        assert len(h) == 8
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_cached(self):
        """config_hash returns the same value on repeated access."""
        config = ProcessingConfig()
        h1 = config.config_hash
        h2 = config.config_hash
        assert h1 == h2


class TestDefaultConfig:
    def test_default_window(self):
        assert DEFAULT_CONFIG.window == 4

    def test_default_stop_threshold(self):
        assert DEFAULT_CONFIG.stop_threshold_kmh == 2.0

    def test_default_config_is_processing_config_instance(self):
        assert isinstance(DEFAULT_CONFIG, ProcessingConfig)


class TestProcessingConfigPydantic:
    def test_is_pydantic_base_model(self):
        """ProcessingConfig is a Pydantic BaseModel (migrated from @dataclass)."""
        from pydantic import BaseModel

        assert isinstance(ProcessingConfig(), BaseModel)

    def test_model_dump_returns_correct_fields(self):
        """model_dump() returns the two config fields."""
        assert ProcessingConfig(window=4).model_dump() == {
            "window": 4,
            "stop_threshold_kmh": 2.0,
        }

    def test_config_snapshot_is_valid_json(self):
        """config_snapshot is a JSON string with both field names."""
        import json

        snap = ProcessingConfig(window=4, stop_threshold_kmh=2.0).config_snapshot
        d = json.loads(snap)
        assert d["window"] == 4
        assert d["stop_threshold_kmh"] == pytest.approx(2.0)

    def test_config_snapshot_different_values_differ(self):
        """Different field values produce different snapshots."""
        s1 = ProcessingConfig(window=4).config_snapshot
        s2 = ProcessingConfig(window=8).config_snapshot
        assert s1 != s2


