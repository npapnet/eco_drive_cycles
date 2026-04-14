# %%[markdown]
"""
# Getting the metrics from the Archived Parquet Files

TODO: I need to add some more metadata to the Parquet files,
    such as
    - the version of the data format,
    - the user who generated the data,
    - the date and time
    - Processing data
    - ....
    Consider using pydantic to define a schema.
    This will help me to keep track of the data and ensure that I can reproduce the results in the future.
"""

# %%
import pathlib
import pyarrow.parquet as pq
import pandas as pd
import logging

from drive_cycle_calculator import OBDFile


logging.basicConfig(level=logging.INFO)

%load_ext autoreload
%autoreload 2
# %%[markdown]
"""
# Retrieving Data
"""
# %%
ROOTDIR = pathlib.Path(__file__).parent.parent.parent
DATADIR = ROOTDIR / "data" / "trips"
print(ROOTDIR)
print(DATADIR)

pq_files = list(DATADIR.glob("*.parquet"))
FNAME = pq_files[0]
print(f"Reading metadata from: {FNAME}")

# %%

obd = OBDFile.from_parquet(FNAME)
# %%
obd._df.columns
# %%

# longmean, longstd = obd._df["Longitude"].mean(), obd._df["Longitude"].std()
# latmean, latstd = obd._df["Latitude"].mean(), obd._df["Latitude"].std()
# alt_mean, alt_std = obd._df["Altitude"].mean(), obd._df["Altitude"].std()
# print(f"Longitude: mean={longmean}, std={longstd}")
# print(f"Latitude: mean={latmean}, std={latstd}")
# print(f"Altitude: mean={alt_mean}, std={alt_std}")

obd._trip_metadata()

# TODO: when creating a trip pass this as metadata to the trip object.
# %%

tr = obd.to_trip()
# %%
tr.date
tr.duration
tr.max_speed
tr.mean_acceleration
tr.mean_deceleration
tr.mean_speed


# %%
# %%

longser = obd._df["Longitude"]

for i, val in enumerate(longser):
    try:
        float(val)
    except ValueError:
        logging.warning(f"Value at index {i} is not a valid float: {val}")

# %%
obd.name
# %%
import plotnine as p9

p = (
    p9.ggplot(obd._df, p9.aes(x="GPS Time", y="G(z)"))
    + p9.geom_point(alpha=0.5)
    + p9.theme_minimal()
)
p
# %%
