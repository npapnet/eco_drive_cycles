# %%[markdown]
"""
Inspect a raw OBD parquet file before any processing.

Shows the unmodified DataFrame exactly as Torque exported it — raw column
names, dtypes, sensor-off markers ("-"), and a sample of values. Useful
for diagnosing data-quality issues or understanding what the ingest pipeline
receives as input.

Usage:
    python examples/cli-single/inspect_raw.py <path/to/file.parquet>

Example:
    python examples/cli-single/inspect_raw.py data/trackLog-2019-Sep-20_10-49-22.xlsx
"""

# %%
# import sys
from pathlib import Path

from drive_cycle_calculator.obd_file import OBDFile

# %%

# if len(sys.argv) < 2:
#     # Requires at least one argument
#     print("Usage: python examples/cli/inspect_raw.py <path/to/file.xlsx>")
#     sys.exit(1)
# else:
#     path = Path(sys.argv[1])

# %% For use with interactive system
ROOTDIR = Path(__file__).parents[2]
DATADIR = ROOTDIR / "data" / "trips"
assert DATADIR.exists()

# find all xlsx files in DATADIR
parquet_files = list(DATADIR.glob("*.parquet"))
assert len(parquet_files) > 0

# pick one file
path = parquet_files[0]
print(path)
# %%

print(f"Loading raw file: {path}\n")

obd = OBDFile.from_parquet(path)

df = obd.full_df
# %%
df.columns
# %%
import pandas as pd
import matplotlib.pyplot as plt
import plotnine as p9

# plot accelerations vs elapsed time
df["elapsed_s"] = (df["GPS Time"] - df["GPS Time"][0]).dt.total_seconds()

p1 = (
    p9.ggplot(df)
    # + p9.geom_line(p9.aes(x="elapsed_s", y="G(x)"), color="blue")
    # + p9.geom_line(p9.aes(x="elapsed_s", y="G(calibrated)"), color="green")
    # + p9.geom_line(p9.aes(x="elapsed_s", y="G(y)"))
    + p9.geom_line(p9.aes(x="elapsed_s", y="Acceleration Sensor(X axis)(g)"), color="red")
    + p9.geom_line(p9.aes(x="elapsed_s", y="Acceleration Sensor(Y axis)(g)"), color="blue")
    + p9.geom_line(p9.aes(x="elapsed_s", y="Acceleration Sensor(Total)(g)"), color="green")
    + p9.theme_bw()
    + p9.labs(title="Acceleration vs Elapsed Time", x="Elapsed Time (s)", y="Acceleration (g)")
)

p1.draw()

# %%
obd.curated_df.columns
# %% Generate Trip from OBDFile
trip = obd.to_trip()
trip.metadata
# %%

print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")

# %%
print("── Columns, dtypes, and non-null counts ─────────────────────────────────")
for col in df.columns:
    n_non_null = df[col].notna().sum()
    # Count how many are the Torque "-" placeholder
    n_dash = (df[col] == "-").sum() if df[col].dtype == object else 0
    dash_note = f"  ({n_dash} sensor-off '-')" if n_dash else ""
    print(
        f"  {col!r:50s}  dtype={str(df[col].dtype):8s}  non-null={n_non_null}/{len(df)}{dash_note}"
    )

# %%
print("\n── First 5 rows (key OBD columns) ──────────────────────────────────────")
key_cols = [
    c
    for c in df.columns
    if any(
        k in c
        for k in [
            "GPS Time",
            "Speed (OBD)",
            "CO",
            "Engine Load",
            "Fuel flow",
        ]
    )
]
print(df[key_cols].head(5).to_string())
# %%
print("\n── Sample unique values per key column ─────────────────────────────────")
for col in key_cols:
    sample = df[col].dropna().unique()[:5].tolist()
    print(f"  {col!r}: {sample}")

# %%
