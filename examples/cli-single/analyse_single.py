#%%
from pathlib import Path
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
#%%
ROOTDIR = Path(__file__).parents[2]
DATADIR = ROOTDIR / 'data'/'trips'

assert DATADIR.exists(), "Data directory does not exist"

parquet_files = list(DATADIR.glob("*.parquet"))
if not parquet_files:
    raise FileNotFoundError(f"No parquet files found in {DATADIR}. Run ingest.py first.")

[print(f.stem) for f in parquet_files]


# %% load parquet file
FNAME = parquet_files[0]
df = pd.read_parquet(FNAME)
# %%
ren_dict = {
    'elapsed_s' :'elapsed_s', 
    'co2' : 'CO₂ in g/km (Average)(g/km)', 
    'engine_load' : 'Engine Load(%)',
    'fuel_rate_lph' : 'Fuel flow rate/hour(l/hr)', 
    'v_smooth':'smooth_speed_kmh',
    'v_mps' : 'speed_ms', 
    'a_mps2' : 'a(m/s2)',
    'accel':'acceleration_ms2', 
    'decel':'deceleration_ms2'
}

rev_dict = {value: key for key, value in ren_dict.items()}

df.rename(columns=rev_dict, inplace=True)

df.columns
# %%
plt.plot(df["elapsed_s"], df["co2"])
plt.xlabel("Time (s)")
plt.ylabel("CO₂ (g/km)")
plt.title("CO₂ vs Time")
# %%

plt.plot(df["elapsed_s"], df["a_mps2"])
plt.plot(df["elapsed_s"], df["accel"],'.')
plt.plot(df["elapsed_s"], df["decel"],'.')
plt.xlabel("Time (s)")
plt.ylabel("Acceleration (m/s²)")
plt.title("Acceleration vs Time")
# %%
plt.plot(df["elapsed_s"], df["v_mps"])
plt.plot(df["elapsed_s"], df["v_smooth"]/3.6,'.')
plt.xlabel("Time (s)")
plt.ylabel("Speed (m/s)")

# %%
from drive_cycle_calculator.metrics.trip import Trip

# Load via TripCollection.from_parquet or construct directly after reading df
# Note: Trip(df, name) requires a processed DataFrame and a name string.
# This cell is a placeholder — use TripCollection.from_parquet() to load a folder.
t1 = Trip(df=pd.read_parquet(FNAME), name=FNAME.stem)




# %%
