# %% [markdown]

"""
## Compare Resample

I want to open a xlsx file using the obd_file module and then compare the resampled data with the original data with pandas.

use a file from the raw_data/2019-opsimoulis/ folder


"""

# %%
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

from drive_cycle_calculator.obd_file import OBDFile

# %%
# Determine the path to the raw data file (relative to this script's location)
current_dir = Path(__file__).parent
root_dir = current_dir.parent.parent
DATA_PATH = root_dir / "raw_data" / "2019-opsimoulis"

xlsx_files = list(DATA_PATH.glob("*.xlsx"))


# %%
# Manual mapping approach (most robust across different environments)
greek_months = {
    "Ιαν": "Jan",
    "Φεβ": "Feb",
    "Μαρ": "Mar",
    "Απρ": "Apr",
    "Μάι": "May",
    "Ιούν": "Jun",
    "Ιούλ": "Jul",
    "Αυγ": "Aug",
    "Σεπ": "Sep",
    "Οκτ": "Oct",
    "Νοε": "Nov",
    "Δεκ": "Dec",
}


def convert_greek_dates_to_time(s):

    # 1. Replace all Greek abbreviations in one go using the dictionary
    # regex=True allows it to find the substrings within the full date strings
    s_clean = s.replace(greek_months, regex=True)

    # 2. Convert the entire Series to datetime
    df_dt = pd.to_datetime(s_clean, format="%d-%b-%Y %H:%M:%S.%f")

    # 3. Extract just the time (as a timedelta to keep ms and performance)
    time_of_day = df_dt - df_dt.dt.normalize()
    return time_of_day


def read_filepath_and_return_time(file_path):
    df_xlsx = pd.read_excel(file_path)
    # print(f"Original DataFrame shape: {df_xlsx.shape}")
    s = df_xlsx[" Device Time"]
    return convert_greek_dates_to_time(s)


max_times = [
    (i, file_path.stem, ",", read_filepath_and_return_time(file_path).diff().max())
    for i, file_path in enumerate(xlsx_files)
]
print(max_times)
# %%
xslx_id = 9
file_path = xlsx_files[xslx_id]
df_xlsx = pd.read_excel(file_path)
# %%
s = df_xlsx[" Device Time"]
df_xlsx["time"] = convert_greek_dates_to_time(s)

plt.hist(df_xlsx.time.dt.total_seconds().diff(), log="y")
# %%
print(f"Loading {file_path.name}...")
obd = OBDFile.from_xlsx(file_path)

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

print("\n--- Time Interval (Δt) Comparison ---")
orig_dt = original_df["GPS Time"].diff().dt.total_seconds().describe()
res_dt = resampled_df["GPS Time"].diff().dt.total_seconds().describe()

# %%
dt_comparison = pd.DataFrame({"Original Δt (s)": orig_dt, "Resampled Δt (s)": res_dt})
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

The following section produces a series of plots  comparting the original and 
the resampled data (of the OBD file) for each column. 

To make easier the comparison, this section removed a lot of data points
so that the plots are not too crowded. the removal is based on the 
raw_data/2019-opsimoulis/trackLog-2019-Sep-20_18-37-12.xlsx file, 
which exhibits the greates time interval between data points around time 16:20. 

"""
# %%
# Define the time range based on the current index slice (rows 2400 to 2550)
start_time = original_df.iloc[2400]["GPS Time"]
end_time = original_df.iloc[2550]["GPS Time"]

# Select subsets based on GPS Time range
original_df = original_df[
    (original_df["GPS Time"] >= start_time) & (original_df["GPS Time"] <= end_time)
]
resampled_df = resampled_df[
    (resampled_df["GPS Time"] >= start_time) & (resampled_df["GPS Time"] <= end_time)
]

# %%
# comparig GPS Time columns
plt.figure()
plt.plot(original_df.iloc[:, 0], label="Original")
plt.plot(resampled_df.iloc[:, 0], label="Resampled", alpha=0.7)
plt.xlabel("Index")
plt.ylabel("GPS Time")
plt.title("GPS Time Comparison")
# %%
lst = list(enumerate(original_df.columns))
# %%
item = lst[2]


def plot_column_comparison(item):
    colno, colname = item

    plt.figure()
    plt.plot(original_df.iloc[:, 0], original_df.iloc[:, colno], "r.", alpha=0.3, label="Original")
    plt.plot(
        resampled_df.iloc[:, 0], resampled_df.iloc[:, colno], "k-.", alpha=0.3, label="Resampled"
    )
    plt.xlabel("GPS Time")
    plt.ylabel(f"{colname}")
    plt.legend()
    plt.title(f"{colname}- GPS Time Comparison")


plot_column_comparison(lst[2])

# %%
plot_column_comparison(lst[3])
# %% GPS speed
plot_column_comparison(lst[4])
# %% Speed (GPS)(km/h)
plot_column_comparison(lst[31])
# %% Speed (OBD)(km/h)
plot_column_comparison(lst[32])

# %%
