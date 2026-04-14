# %% [markdown]
"""
Code for visualising the vicinity of the trip data
"""

# %%
import numpy as np
import pandas as pd
import geopandas as gpd
from plotnine import ggplot, aes, geom_map, geom_polygon, coord_fixed, theme_minimal

# 1. Fetch map geometry directly from the Natural Earth AWS link (replaces deprecated gpd.datasets)
url = "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip"
world = gpd.read_file(url)

# In the raw Natural Earth data, the country name column is 'ADMIN' (or 'NAME') instead of 'name'
greece = world[world["ADMIN"] == "Greece"]

# 2. User's statistical coordinates (Example: Athens area)


mean_lon = 25.148217720706995
mean_lat = 35.33100725932466
std_lon = 0.02211710983061268 * 6  # Assumed standard deviation in degrees
std_lat = 0.008075757587970387 * 6  # Assumed standard deviation in degrees

# 3. Correcting methodological error: Adjust longitude for physical distance distortion at this latitude
# One degree of longitude is shorter than one degree of latitude by a factor of cos(latitude)
lat_rad = np.radians(mean_lat)
lon_std_dev = std_lon / np.cos(lat_rad)

# 4. Generate parametric coordinates for the statistical boundary (an ellipse in degree-space, a circle physically)
theta = np.linspace(0, 2 * np.pi, 100)
circle_df = pd.DataFrame(
    {"lon": mean_lon + lon_std_dev * np.cos(theta), "lat": mean_lat + std_lat * np.sin(theta)}
)

# 5. Construct the plotnine visualization
p = (
    ggplot()
    + geom_map(greece, fill="#d3d3d3", color="white")
    + geom_polygon(circle_df, aes(x="lon", y="lat"), fill="red", alpha=0.3, color="darkred", size=1)
    + coord_fixed(xlim=(19, 29), ylim=(34, 42))  # Bounding box capturing Greece
    + theme_minimal()
)

p
# %%
