# %% [markdown]

"""
## Compare Resample

I want to open a xlsx file using the obd_file module and then compare the resampled data with the original data with pandas.

use a file from the raw_data/2019-opsimoulis/ folder
"""

# %%
import pandas as pd
from pathlib import Path
from drive_cycle_calculator.obd_file import OBDFile

#%%
# Determine the path to the raw data file (relative to this script's location)
current_dir = Path(__file__).parent
root_dir = current_dir.parent.parent
file_path = root_dir / "raw_data" / "2019-opsimoulis" / "trackLog-2019-Sep-16_10-58-16.xlsx"
if not file_path.exists():
    print(f"File not found: {file_path}")
    
#%%
df_xlsx = pd.read_excel(file_path)
print(f"Original DataFrame shape: {df_xlsx.shape}")
#%%
# Manual mapping approach (most robust across different environments)
greek_months = {
    'Ιαν': 'Jan', 'Φεβ': 'Feb', 'Μαρ': 'Mar', 'Απρ': 'Apr',
    'Μάι': 'May', 'Ιούν': 'Jun', 'Ιούλ': 'Jul', 'Αυγ': 'Aug',
    'Σεπ': 'Sep', 'Οκτ': 'Oct', 'Νοε': 'Nov', 'Δεκ': 'Dec'
}

    
s = df_xlsx[" Device Time"]

    
# 1. Replace all Greek abbreviations in one go using the dictionary
# regex=True allows it to find the substrings within the full date strings
s_clean = s.replace(greek_months, regex=True)

# 2. Convert the entire Series to datetime
df_dt = pd.to_datetime(s_clean, format='%d-%b-%Y %H:%M:%S.%f')

# 3. Extract just the time (as a timedelta to keep ms and performance)
time_of_day = df_dt - df_dt.dt.normalize()

print((time_of_day.diff()).describe())

#%%
print(f"Loading {file_path.name}...")
obd = OBDFile.from_xlsx(file_path)

# 1. Original data
original_df = obd.full_df

# 2. Resampled data
print("Resampling data to 1Hz...")
resampled_df = obd._resample_to_1hz()

# 3. Compare the data
print(f"\n--- Shapes ---")
print(f"Original shape: {original_df.shape}")
print(f"Resampled shape: {resampled_df.shape}")

print("\n--- Time Interval (Δt) Comparison ---")
orig_dt = original_df["GPS Time"].diff().dt.total_seconds().describe()
res_dt = resampled_df["GPS Time"].diff().dt.total_seconds().describe()

dt_comparison = pd.DataFrame({
    'Original Δt (s)': orig_dt,
    'Resampled Δt (s)': res_dt
})
print(dt_comparison)

col = "Speed (OBD)(km/h)"
if col in original_df.columns:
    print(f"\n--- Statistics Comparison for '{col}' ---")
    comparison_df = pd.DataFrame({
        'Original': original_df[col].describe(),
        'Resampled': resampled_df[col].describe(),
        'Diff': resampled_df[col].describe() - original_df[col].describe()
    })
    print(comparison_df)


# %%
