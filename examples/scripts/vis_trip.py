# %%[markdown]
"""
# Visualing a trip

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
#%%
pq_files = list(DATADIR.glob("*.parquet"))
# FNAME = pq_files[0]
# this is the longest trip in the dataset, and has a lot of data points
FNAME = pq_files[41]
FNAME = DATADIR/"t20250816-093151-1384-4a483a.parquet"
print(f"Reading metadata from: {FNAME}")
# %%
obd = OBDFile.from_parquet(FNAME)

# %%
import tempfile
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import plotnine as p9

def plot_trip_path(df: pd.DataFrame, xlims:list = (19, 29), ylims:list=(34, 42), sigma_multiplier: float = 6.0, force_download:bool = False) -> p9.ggplot:
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

    p = (
        p9.ggplot()# df, p9.aes(x="Longitude", y="Latitude"))
        + p9.geom_map(greece, fill="#d3d3d3", color="white")
        # + p9.geom_polygon(df, p9.aes(x="Longitude", y="Latitude"), fill="red", alpha=0.3, color="darkred", size=1)
        + p9.geom_path(df, p9.aes(x="Longitude", y="Latitude"), alpha=0.3, color="darkred", size=1) 
        + p9.coord_cartesian(xlim=xlims, ylim=ylims)
        + p9.theme_minimal()
        + p9.theme(aspect_ratio=(ylims[1] - ylims[0]) / (xlims[1] - xlims[0]))
        + p9.labs(title="Trip Path")
    )
    return p

plot_trip_path(df = obd._df.loc[:,["Longitude", "Latitude"]]
               , xlims=(23.5, 26.5), ylims=(39, 41.0))
#%%
obd._df.columns
# %%
