import pathlib
import tempfile
import urllib.request
import logging
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import geopandas as gpd

from bokeh.plotting import figure, show
from bokeh.models import GeoJSONDataSource, ColumnDataSource
from bokeh.io import output_notebook # Use output_file for standalone HTML if not in a Jupyter environment

from drive_cycle_calculator import OBDFile

logging.basicConfig(level=logging.INFO)

ROOTDIR = pathlib.Path(__file__).parent.parent.parent
DATADIR = ROOTDIR / "data" / "trips"

pq_files = list(DATADIR.glob("*.parquet"))

metrics_lst = []
for pq_file in pq_files:
    logging.info(f"Reading metadata from: {pq_file}")
    obd = OBDFile.from_parquet(pq_file)
    spatial_metadata = obd._trip_spatial_metadata()
    
    metrics = obd.get_metrics()
    metrics.update(spatial_metadata)
    metrics['name'] = pq_file.stem
    
    tr = obd.to_trip()
    metrics['date'] = tr.date
    metrics_lst.append(metrics)

metrics_df = pd.DataFrame(metrics_lst)
FNAME_OUT = ROOTDIR / "data" / "trips_metrics.csv"
metrics_df.to_csv(FNAME_OUT, index=False)

def plot_trip_vicinity(df: pd.DataFrame, xlims: tuple = (19, 29), ylims: tuple = (34, 42), sigma_multiplier: float = 6.0, force_download: bool = False):
    cache_dir = Path(tempfile.gettempdir()) / "map_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / "ne_10m_admin_0_countries.zip"
    url = "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip"

    if not file_path.exists() or force_download:
        logging.info(f"Downloading map data from {url} to {file_path}")
        urllib.request.urlretrieve(url, file_path)

    world = gpd.read_file(f"zip://{file_path.absolute()}")
    greece = world[world["ADMIN"] == "Greece"]

    geo_source = GeoJSONDataSource(geojson=greece.to_json())

    p = figure(
        title="Trip Vicinity",
        x_range=xlims,
        y_range=ylims,
        match_aspect=True,
        width=800,
        height=600,
        tools="pan,wheel_zoom,reset,save",
        background_fill_color="white"
    )

    p.patches(
        xs='xs', 
        ys='ys', 
        source=geo_source, 
        fill_color="#d3d3d3", 
        line_color="white", 
        line_width=1
    )

    theta = np.linspace(0, 2 * np.pi, 100)
    xs_ellipses = []
    ys_ellipses = []

    for idx, row in df.iterrows():
        mean_lon = row['lon_mean']
        mean_lat = row['lat_mean']
        
        std_lon = row['lon_std'] * sigma_multiplier
        std_lat = row['lat_std'] * sigma_multiplier

        lat_rad = np.radians(mean_lat)
        lon_std_dev = std_lon / np.cos(lat_rad)

        lon_coords = mean_lon + lon_std_dev * np.cos(theta)
        lat_coords = mean_lat + std_lat * np.sin(theta)
        
        xs_ellipses.append(lon_coords.tolist())
        ys_ellipses.append(lat_coords.tolist())

    ellipse_source = ColumnDataSource(dict(xs=xs_ellipses, ys=ys_ellipses))

    p.patches(
        xs='xs', 
        ys='ys', 
        source=ellipse_source, 
        fill_color="red", 
        fill_alpha=0.3, 
        line_color="darkred", 
        line_width=1
    )

    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None
    p.axis.visible = False

    return p

p1 = plot_trip_vicinity(metrics_df, force_download=False)
show(p1)

p2 = plot_trip_vicinity(metrics_df, xlims=(23.5, 26.5), ylims=(34.8, 35.86), force_download=False)
show(p2)