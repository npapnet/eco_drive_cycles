# %%[markdown]
"""
# Visualing a trip

"""

# %%
import pathlib
import pyarrow.parquet as pq
import pandas as pd
import logging
import matplotlib.pyplot as plt

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
#%%
pq_files = list(DATADIR.glob("*.parquet"))
# FNAME = pq_files[0]
# this is the longest trip in the dataset, and has a lot of data points
FNAME = pq_files[40]
# FNAME = DATADIR/"t20250816-093151-1384-4a483a.parquet"
print(f"Reading metadata from: {FNAME}")
# %%
obd = OBDFile.from_parquet(FNAME)
# %%
%matplotlib inline

obd._df['Speed (GPS)(km/h)'].plot()
# plt.show()
# %%