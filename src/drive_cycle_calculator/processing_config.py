# processing_config.py
# --------------------
# ProcessingConfig — parameters that control how a curated OBD DataFrame is
# transformed into a processed DataFrame suitable for Trip construction.

from __future__ import annotations

import dataclasses
import hashlib
import json
from functools import cached_property

import pandas as pd

from drive_cycle_calculator._schema import OBD_COLUMN_MAP


@dataclasses.dataclass
class ProcessingConfig:
    """Parameters for the OBD data processing pipeline.

    Attributes
    ----------
    window : int
        Rolling window size for speed smoothing (samples).  Default 4 matches
        the original DriveGUI window.
    stop_threshold_kmh : float
        Speed below which a sample is classified as stopped (km/h).
    """

    window: int = 4
    stop_threshold_kmh: float = 2.0

    def apply(self, curated_df: pd.DataFrame) -> pd.DataFrame:
        """Transform a curated OBD DataFrame into a processed DataFrame.

        Parameters
        ----------
        curated_df : pd.DataFrame
            DataFrame with raw OBD column names (CURATED_COLS subset).
            Produced by ``OBDFile.curated_df``.

        Returns
        -------
        pd.DataFrame
            Processed DataFrame with columns:
            elapsed_s, smooth_speed_kmh, acc_ms2, speed_kmh,
            co2_g_per_km, engine_load_pct, fuel_flow_lph.

            Note: speed_ms, acceleration_ms2, deceleration_ms2 are NOT produced —
            they are redundant and were removed in the v2 pipeline.

        Raises
        ------
        ValueError
            If any column required by this pipeline is absent from *curated_df*.
        """
        from drive_cycle_calculator._schema import CURATED_COLS

        missing = [c for c in CURATED_COLS if c not in curated_df.columns]
        if missing:
            raise ValueError(
                f"ProcessingConfig.apply() received a DataFrame missing required "
                f"column(s): {missing}. Pass a DataFrame produced by OBDFile.curated_df."
            )

        gps_dt = curated_df["GPS Time"]
        if not pd.api.types.is_datetime64_any_dtype(gps_dt):
            gps_dt = pd.to_datetime(gps_dt, errors="coerce", utc=True)
        elapsed_s = (gps_dt - gps_dt.dropna().iloc[0]).dt.total_seconds()

        speed_raw = pd.to_numeric(curated_df["Speed (OBD)(km/h)"], errors="coerce")
        smooth_speed = speed_raw.rolling(
            window=self.window, center=True, min_periods=self.window
        ).mean()
        # acc_ms2 is the full signed acceleration (m/s²), not split into pos/neg.
        # Divide by the actual inter-sample interval so the result is in m/s²
        # regardless of OBD polling rate (Torque samples are NOT guaranteed 1 Hz).
        dt = elapsed_s.diff()  # seconds between consecutive samples
        # Guard: dt=0 (duplicate timestamps) or dt<0 (out-of-order rows) produce
        # ±inf without this mask.  Treat them as NaN so downstream stats stay finite.
        dt = dt.where(dt > 0)
        acc_ms2 = (smooth_speed / 3.6).diff() / dt

        passthrough = curated_df.rename(columns=OBD_COLUMN_MAP)

        return pd.DataFrame(
            {
                "elapsed_s": elapsed_s,
                "smooth_speed_kmh": smooth_speed,
                "acc_ms2": acc_ms2,
                "speed_kmh": passthrough["speed_kmh"],
                "co2_g_per_km": pd.to_numeric(passthrough["co2_g_per_km"], errors="coerce"),
                "engine_load_pct": pd.to_numeric(passthrough["engine_load_pct"], errors="coerce"),
                "fuel_flow_lph": pd.to_numeric(passthrough["fuel_flow_lph"], errors="coerce"),
            }
        )

    @cached_property
    def config_hash(self) -> str:
        """First 8 characters of the md5 of the sorted JSON of config fields.

        Deterministic across instances with identical field values.
        Stored in the DuckDB catalog for reproducibility auditing.
        """
        payload = json.dumps(dataclasses.asdict(self), sort_keys=True)
        return hashlib.md5(payload.encode()).hexdigest()[:8]


# Module-level singleton — the default configuration used when no config is specified.
DEFAULT_CONFIG = ProcessingConfig()


def smooth_and_derive(speed_kmh: pd.Series) -> dict:
    """Apply rolling smoothing and derive acceleration columns.

    TODO: Remove from codebase
    """
    smooth_speed = speed_kmh.rolling(window=4, center=True, min_periods=4).mean()
    speed_ms = smooth_speed / 3.6
    acceleration = speed_ms.diff()
    return dict(
        smooth_speed=smooth_speed,
        speed_ms=speed_ms,
        acceleration=acceleration,
        pos_acc=acceleration.where(acceleration > 0),
        neg_acc=acceleration.where(acceleration < 0),
    )
