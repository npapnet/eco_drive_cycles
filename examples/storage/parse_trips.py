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

spatial_metadata = obd._trip_spatial_metadata()
print(spatial_metadata)
# TODO: when creating a trip pass this as metadata to the trip object.
# %%

tr = obd.to_trip()
# %%
print(f"Date: {tr.date}")


# metrics = tr.metrics
metrics.update(spatial_metadata)

metrics2 = obd.get_metrics()

# %%
metrics_lst = []
for pq_file in pq_files:
    logging.info(f"Reading metadata from: {pq_file}")
    obd = OBDFile.from_parquet(pq_file)
    metrics = obd.get_metrics()
    metrics['name'] = pq_file.stem
    tr = obd.to_trip()
    metrics['date'] = tr.date
    metrics_lst.append(metrics)
    # logging.info(f"Metrics: {metrics}")


# %%
metrics_df = pd.DataFrame(metrics_lst)
print(metrics_df)
# %%
FNAME_OUT = ROOTDIR / "data" / "trips_metrics.csv"
metrics_df.to_csv(FNAME_OUT, index=False)
# %%
