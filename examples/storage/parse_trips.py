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

import tempfile
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import plotnine as p9

def plot_trip_vicinity(df: pd.DataFrame, xlims:list = (19, 29), ylims:list=(34, 42), sigma_multiplier: float = 6.0, force_download:bool = False) -> ggplot:
    """ 

    Args:
        df (pd.DataFrame): _description_
        xlims (list, optional): _description_. Defaults to (19, 29).
        ylims (list, optional): _description_. Defaults to (34, 42).
        sigma_multiplier (float, optional): _description_. Defaults to 6.0.
        force_download (bool, optional): _description_. Defaults to False.
        TODO: Add figure size as an argument.
    Returns:
        ggplot: _description_
    """
    # Use cross-platform temporary directory for caching
    cache_dir = Path(tempfile.gettempdir()) / "map_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / "ne_110m_admin_0_countries.zip"
    # url =  "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip" # Low detail
    url = "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip"

    if not file_path.exists() or force_download:
        logging.info(f"Downloading map data from {url} to {file_path}")
        urllib.request.urlretrieve(url, file_path)

    world = gpd.read_file(f"zip://{file_path.absolute()}")
    greece = world[world["ADMIN"] == "Greece"]

    theta = np.linspace(0, 2 * np.pi, 100)
    ellipses = []

    for idx, row in df.iterrows():
        mean_lon = row['lon_mean']
        mean_lat = row['lat_mean']
        
        # Apply standard deviation multiplier (defaults to user's original * 6 logic)
        std_lon = row['lon_std'] * sigma_multiplier
        std_lat = row['lat_std'] * sigma_multiplier

        lat_rad = np.radians(mean_lat)
        lon_std_dev = std_lon / np.cos(lat_rad)

        # Correction for physical distance distortion at this latitude
        circle_data = pd.DataFrame({
            "lon": mean_lon + lon_std_dev * np.cos(theta),
            "lat": mean_lat + std_lat * np.sin(theta),
            "group": idx
        })
        ellipses.append(circle_data)
    
    circle_df = pd.concat(ellipses, ignore_index=True)

    p = (
        p9.ggplot()
        + p9.geom_map(greece, fill="#d3d3d3", color="white")
        + p9.geom_polygon(circle_df, p9.aes(x="lon", y="lat", group="group"), fill="red", alpha=0.3, color="darkred", size=1)
        + p9.coord_fixed(xlim=xlims, ylim=ylims)
        + p9.theme_minimal()
        # + p9.theme(figure_size=(7, 6))
    )
    
    return p

plot_trip_vicinity(metrics_df, force_download=False)

# %%
plot_trip_vicinity(metrics_df, xlims=(23.5,26.5), ylims=(34.8,35.86), force_download=False)
# %%
