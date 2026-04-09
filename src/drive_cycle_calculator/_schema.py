# _schema.py
# ----------
# Dependency-free schema constants for the OBD data pipeline.
# Imported by both obd_file.py and processing_config.py — lives at package root
# to avoid circular imports.

from __future__ import annotations

# Maps raw OBD column names (as exported by Torque) to short English names
# used in the processed DataFrame produced by ProcessingConfig.apply().
# Note: "GPS Time" is NOT here — it is consumed to produce elapsed_s, not renamed.
OBD_COLUMN_MAP: dict[str, str] = {
    "Speed (OBD)(km/h)": "speed_kmh",
    "CO\u2082 in g/km (Average)(g/km)": "co2_g_per_km",
    "Engine Load(%)": "engine_load_pct",
    "Fuel flow rate/hour(l/hr)": "fuel_flow_lph",
}

# The minimum set of OBD columns required for analysis.
# OBDFile.curated_df returns only these columns.
# OBDFile.to_trip() raises ValueError if any are absent.
CURATED_COLS: list[str] = [
    "GPS Time",
    "Speed (OBD)(km/h)",
    "CO\u2082 in g/km (Average)(g/km)",
    "Engine Load(%)",
    "Fuel flow rate/hour(l/hr)",
]
