from __future__ import annotations

import pandas as pd
import pytest

from drive_cycle_calculator.obd_file import OBDFile


def make_raw_obd_df(n: int = 10, speed_kmh: float = 30.0) -> pd.DataFrame:
    """Minimal raw OBD DataFrame with all CURATED_COLS and GPS columns."""
    timestamps = [f"Mon Sep 22 10:30:{i:02d} +0300 2019" for i in range(n)]
    return pd.DataFrame(
        {
            "GPS Time": timestamps,
            "Speed (OBD)(km/h)": [speed_kmh] * n,
            "CO₂ in g/km (Average)(g/km)": [120.0] * n,
            "Engine Load(%)": [50.0] * n,
            "Fuel flow rate/hour(l/hr)": [2.0] * n,
            "Longitude": [24.0] * n,
            "Latitude": [60.0] * n,
            "Altitude": [100.0] * n,
        }
    )


@pytest.fixture
def archive_parquet(tmp_path):
    """Factory fixture: call to write a v2 archive Parquet and get back its Path.

    Usage: archive_parquet("trip.parquet", speed_kmh=30.0, n=20)
           archive_parquet(full_path, df=custom_df)
    """
    def _write(name="trip.parquet", speed_kmh=30.0, n=20, df=None):
        path = tmp_path / name if isinstance(name, str) else name
        path.parent.mkdir(parents=True, exist_ok=True)
        OBDFile(
            df if df is not None else make_raw_obd_df(n=n, speed_kmh=speed_kmh),
            path.stem,
        ).to_parquet(path)
        return path
    return _write


@pytest.fixture
def raw_xlsx(tmp_path):
    """Factory fixture: call to write a raw OBD xlsx and get back its Path.

    Usage: raw_xlsx("trip.xlsx", speed_kmh=30.0, n=20)
           raw_xlsx(full_path)
    """
    def _write(name="trip.xlsx", speed_kmh=30.0, n=20):
        path = tmp_path / name if isinstance(name, str) else name
        path.parent.mkdir(parents=True, exist_ok=True)
        make_raw_obd_df(n=n, speed_kmh=speed_kmh).to_excel(path, index=False)
        return path
    return _write
