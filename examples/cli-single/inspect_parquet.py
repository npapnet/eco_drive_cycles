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
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotnine as p9

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
# Torque often exports numeric columns as strings with "-" placeholders for sensor-off values. This converts the Speed (OBD)(km/h) column to numeric, coercing errors to NaN (which will convert the "-" to NaN).
df["Speed (OBD)(km/h)"] = pd.to_numeric(df["Speed (OBD)(km/h)"], errors="coerce")

for col in ["Speed (OBD)(km/h)", "Engine Load(%)", "Engine RPM(rpm)"]:
    try:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    except KeyError:
        print("'%s' column is missing.", col)
# %%
df.columns
# %%

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
p2 = (
    p9.ggplot(df)
    + p9.geom_point(
        # p9.aes(x="Acceleration Sensor(X axis)(g)", y="Acceleration Sensor(Y axis)(g)"),
        p9.aes(x="Acceleration Sensor(Total)(g)", y="Acceleration Sensor(X axis)(g)"),
        alpha=0.5,
        shape=".",
    )
    + p9.geom_point(
        # p9.aes(x="Acceleration Sensor(X axis)(g)", y="Acceleration Sensor(Y axis)(g)"),
        p9.aes(x="Acceleration Sensor(Total)(g)", y="Acceleration Sensor(Y axis)(g)"),
        alpha=0.5,
        shape=".",
        color="red",
    )
    + p9.geom_point(
        # p9.aes(x="Acceleration Sensor(X axis)(g)", y="Acceleration Sensor(Y axis)(g)"),
        p9.aes(x="Acceleration Sensor(Total)(g)", y="Acceleration Sensor(Z axis)(g)"),
        alpha=0.5,
        shape=".",
        color="green",
    )
    + p9.theme_bw()
    + p9.labs(
        title="Acceleration X, Y vs Total", x="Acceleration Total(g)", y="Acceleration X, Y (g)"
    )
)

p2.draw()
# %%
SPEED_COLs = ["GPS Speed (Meters/second)", "Speed (OBD)(km/h)", "Speed (GPS)(km/h)"]
# this verifies that the GPS Speed (Meters/second) column is consistent with the Speed (GPS)(km/h) column, after converting from m/s to km/h

plt.figure(figsize=(10, 6))
plt.plot(df["elapsed_s"], df["GPS Speed (Meters/second)"] * 3.6, label="GPS Speed (Meters/second)")
plt.plot(df["elapsed_s"], df["Speed (GPS)(km/h)"], label="GPS Speed (Meters/second)")
plt.title("Speed vs Elapsed Time")
plt.xlabel("Elapsed Time (s)")
plt.ylabel("Speed")
plt.legend()
plt.show()


# %%
plt.figure(figsize=(10, 6))
plt.plot(df["Speed (OBD)(km/h)"], df["Speed (GPS)(km/h)"], ".")
plt.show()

# %%
plt.plot(df["Speed (OBD)(km/h)"], df["Acceleration Sensor(Total)(g)"], ".")
plt.xlabel("Speed [kph]")
plt.ylabel("Acceleration [g]")
plt.show()
# %% bivraite distribution

# _df_3 = df.loc[:,["Speed (OBD)(km/h)","Acceleration Sensor(Total)(g)"]].dropna()

# p3_kde2d = (p9.ggplot(df, p9.aes(x="Speed (OBD)(km/h)", y="Acceleration Sensor(Total)(g)"))
#             # +p9.geom_density_2d(na_rm=True)
#             + p9.geom_density_2d(na_rm=True)
#             # + p9.stat_density_2d(na_rm=True, bins=15, geom="text", p9.aes(label="..level.."), color="black", size=8)
#             + p9.theme_bw()
#             + p9.labs(title="2D KDE: Speed vs Acceleration (with iso lines)", x="Speed (OBD)(km/h)", y="Acceleration Sensor(Total)(g)")
#             )

# p3_kde2d.draw()

from scipy.stats import gaussian_kde

# 1. Clean data and extract variables
df_clean = df.dropna(subset=["Speed (OBD)(km/h)", "Acceleration Sensor(Total)(g)"])
x = df_clean["Speed (OBD)(km/h)"]
y = df_clean["Acceleration Sensor(Total)(g)"]

# 2. Calculate the 2D KDE using scipy
xy = np.vstack([x, y])
kde = gaussian_kde(xy)

# Create a grid to evaluate the KDE
xmin, xmax = x.min(), x.max()
ymin, ymax = y.min(), y.max()
xx, yy = np.mgrid[xmin:xmax:100j, ymin:ymax:100j]
positions = np.vstack([xx.ravel(), yy.ravel()])

# Evaluate KDE on the grid
z = np.reshape(kde(positions).T, xx.shape)

# 3. Plotting
fig, ax = plt.subplots(figsize=(12, 8))

# Draw the contour lines (isolines)
# Adjust levels=15 to change the number of isolines
contour = ax.contour(xx, yy, z, levels=15, cmap="viridis")

# Add the labels natively
# clabel inherently limits to one label per continuous line segment
ax.clabel(contour, inline=True, fontsize=10, fmt="%.4f")

# 4. Formatting
ax.set_title("2D KDE: Speed vs Acceleration (with iso lines)")
ax.set_xlabel("Speed (OBD)(km/h)")
ax.set_ylabel("Acceleration Sensor(Total)(g)")
ax.grid(True, linestyle="--", alpha=0.5)

plt.tight_layout()
plt.show()

# %%
obd.curated_df.columns
# %% Generate Trip from OBDFile
trip = obd.to_trip()
trip.metadata
# %%

print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")

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
