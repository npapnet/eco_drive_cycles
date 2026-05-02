# processing_config.py
# --------------------
# ProcessingConfig — parameters and signal-processing logic for the OBD pipeline.
# DEFAULT_CONFIG is the package-wide default instance.

from __future__ import annotations

import hashlib
import json

import pandas as pd
from pydantic import BaseModel


class ProcessingConfig(BaseModel):
    """Parameters for the OBD data processing pipeline.

    Attributes
    ----------
    window : int
        Rolling window size for speed smoothing (samples). Default 4.
    stop_threshold_kmh : float
        Speed below which a sample is classified as stopped (km/h).
    """

    window: int = 4
    stop_threshold_kmh: float = 2.0

    @property
    def config_hash(self) -> str:
        """First 8 hex characters of the md5 of the sorted JSON of config fields.

        Deterministic across instances with identical field values.
        Stored in the DuckDB catalog for reproducibility auditing.
        """
        payload = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.md5(payload.encode()).hexdigest()[:8]

    @property
    def config_snapshot(self) -> str:
        """Full field values as a compact JSON string.

        Suitable for storing in DuckDB so past configs are recoverable
        without access to the source code.
        """
        return self.model_dump_json()

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

        Raises
        ------
        ValueError
            If any column required by this pipeline is absent from *curated_df*.
        """
        from drive_cycle_calculator.schema import CURATED_COLS, OBD_COLUMN_MAP

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
        dt = elapsed_s.diff()
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


DEFAULT_CONFIG = ProcessingConfig()

__all__ = ["ProcessingConfig", "DEFAULT_CONFIG"]
