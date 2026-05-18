# %% [markdown]
"""
## Compare Resample Fytros

I want to open a csv file using pandas, map its columns to the OBDFile format,
and then compare the resampled data with the original data.

Use the file from `raw_data/2026-fytros/Δευτέρα 30-3 αυτοκινητόδρομος.csv`
which is highly oversampled (e.g. from an Apple phone).
"""

# %%
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

from drive_cycle_calculator.obd_file import OBDFile

# %%
# Determine the path to the raw data file
current_dir = Path(__file__).parent
root_dir = current_dir.parent.parent
DATA_PATH = root_dir / "raw_data" / "2026-fytros"

csv_file = DATA_PATH / "Δευτέρα 30-3 αυτοκινητόδρομος.csv"

# %%
print(f"Loading file...")
df_fytros = pd.read_csv(csv_file)


print(pd.DataFrame(df_fytros.columns))

# %%


# The column names differ from standard Torque Android exports.
# We map them here so OBDFile can process them.
column_mapping = {
    "time": "GPS Time",
    "Vehicle speed (km/h)": "Speed (OBD)(km/h)",
    "Speed (GPS) (km/h)": "Speed (GPS)(km/h)",
    "Altitude (GPS) (m)": "Altitude",
    "Longtitude": "Longitude",
    "Latitude": "Latitude",
    "Calculated engine load value (%)": "Engine Load(%)",
    "Engine RPM (rpm)": "Engine RPM(rpm)",
    "Calculated instant fuel rate (L/h)": "Fuel flow rate/hour(l/hr)",
}
df_fytros = df_fytros.rename(columns=column_mapping)

# Use strict=False since we may be missing other CURATED_COLS
obd = OBDFile(df_fytros, name=csv_file.stem, strict=False)

# 1. Original data
original_df = obd.full_df

# 2. Resampled data
print("Resampling data to 1Hz...")
resampled_df = obd._resample_to_1hz()

# %%
# 3. Compare the data
print(f"\n--- Shapes ---")
print(f"Original shape: {original_df.shape}")
print(f"Resampled shape: {resampled_df.shape}")

print("\n--- Time Interval (dt) Comparison ---")
orig_dt = original_df["GPS Time"].diff().dt.total_seconds().describe()
res_dt = resampled_df["GPS Time"].diff().dt.total_seconds().describe()

# %%
dt_comparison = pd.DataFrame({"Original dt (s)": orig_dt, "Resampled dt (s)": res_dt})
print(dt_comparison)

col = "Speed (OBD)(km/h)"
if col in original_df.columns:
    print(f"\n--- Statistics Comparison for '{col}' ---")
    comparison_df = pd.DataFrame(
        {
            "Original": original_df[col].describe(),
            "Resampled": resampled_df[col].describe(),
            "Diff": resampled_df[col].describe() - original_df[col].describe(),
        }
    )
    print(comparison_df)

# %%
obd.full_df.head()

# %% [markdown]
""" 
# Visual comparison section
"""

# %%
# Define a time range based on a subset (e.g., first 500 rows to avoid clutter)
start_time = original_df.iloc[0]["GPS Time"]
end_time = original_df.iloc[500]["GPS Time"]

# Select subsets based on GPS Time range
subset_original_df = original_df[
    (original_df["GPS Time"] >= start_time) & (original_df["GPS Time"] <= end_time)
]
subset_resampled_df = resampled_df[
    (resampled_df["GPS Time"] >= start_time) & (resampled_df["GPS Time"] <= end_time)
]

# %%
# comparing GPS Time columns
plt.figure()
plt.plot(subset_original_df["GPS Time"].reset_index(drop=True), label="Original")
plt.plot(subset_resampled_df["GPS Time"].reset_index(drop=True), label="Resampled", alpha=0.7)
plt.xlabel("Index")
plt.ylabel("GPS Time")
plt.title("GPS Time Comparison")
plt.legend()


# %%
def plot_column_comparison(colname):
    if colname not in subset_original_df.columns or colname not in subset_resampled_df.columns:
        return

    plt.figure()
    plt.plot(
        subset_original_df["GPS Time"],
        subset_original_df[colname],
        "r.",
        alpha=0.3,
        label="Original",
    )
    plt.plot(
        subset_resampled_df["GPS Time"],
        subset_resampled_df[colname],
        "k-.",
        alpha=0.3,
        label="Resampled",
    )
    plt.xlabel("GPS Time")
    plt.ylabel(f"{colname}")
    plt.legend()
    plt.title(f"{colname} - GPS Time Comparison")


plot_column_comparison("Speed (OBD)(km/h)")
plot_column_comparison("Engine RPM (rpm)")
plot_column_comparison("Altitude")

plt.savefig("compare_resample_fytros.png")

# %%
