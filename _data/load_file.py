#%% [markdown]
"""
This script defines a funciton that loads a csv file into a pandas dataframe

Then using the pathlib library recursively finds all the *.csv files in the subdirectories for each file name loads the file
extracts the first line and appends it to a file named "all headers.csv" prepending it the relative path of the file.  

"""

#%%
from datetime import datetime
import pandas as pd
from pathlib import Path

def load_csv_to_df(file_path:Path|str):
    """
    Loads a csv file into a pandas dataframe.
    """
    df = pd.read_csv(file_path, sep = ";", decimal=",")

    # Convert GPS Time column with entries like "Mon Jul 08 17:28:55 GMT+03:00 2019" to datetime
    if "GPS Time" in df.columns:
        df["GPSTime"] = pd.to_datetime(
            df["GPS Time"], 
            format='%a %b %d %H:%M:%S GMT%z %Y', 
            errors='coerce'
        )
    return df

def extract_headers(base_dir=Path(".")):
    """
    Recursively finds all *.csv files, extracts their first line, 
    and saves them to "all headers.csv" with the relative path prepended.
    """
    output_file = base_dir / "all headers.csv"
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        for file_path in base_dir.rglob("*.csv"):
            # Avoid processing the output file itself
            if file_path.resolve() == output_file.resolve():
                continue
                
            try:
                # Loading entire file to extract headers is inefficient, 
                # so we just read the first line directly.
                with open(file_path, 'r', encoding='utf-8') as in_f:
                    first_line = in_f.readline().rstrip('\n')
                
                # Get the relative path
                rel_path = file_path.relative_to(base_dir)
                
                # Append to the output file (prepending the relative path)
                out_f.write(f'"{rel_path}",{first_line}\n')
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

#%%
if __name__ == "__main__":
    # extract_headers()
    pass

# %%
ROOTDIR = Path(".")
DATADIR = ROOTDIR / "complete_extract" / "ladikas/" 
assert DATADIR.exists(), "Data directory does not exist"
CSV_FILES = list(DATADIR.glob("*.csv"))
print(list(CSV_FILES))
#%%
FNAME = CSV_FILES[0]
df = load_csv_to_df(FNAME)
# %%
df.head()
# %%
cols  = df.columns
# %%
df.loc[3, ["GPSTime", "GPS Time"]]
# %%
df.plot(x="GPSTime", y="GPS Speed (Meters/second)")
# %%
# 0: 'GPS Time',
#  1: 'Device Time',
#  2: 'Longitude',
#  3: 'Latitude',
#  4: 'GPS Speed (Meters/second)',
#  5: 'Horizontal Dilution of Precision',
#  6: 'Altitude',
#  7: 'Bearing',
#  8: 'G(x)',
#  9: 'G(y)',
#  10: 'G(z)',
#  11: 'G(calibrated)',
#  12: '0-100kph Time(s)',
#  13: '100-0kph Time(s)',
#  14: '100-200kph Time(s)',
#  15: 'Acceleration Sensor(Total)(g)',
#  16: 'Average trip speed(whilst stopped or moving)(km/h)',
#  17: 'CO₂ in g/km (Average)(g/km)',
#  18: 'Engine Coolant Temperature(°C)',
#  19: 'Engine Load(%)',
#  20: 'Engine RPM(rpm)',
#  21: 'Fuel flow rate/hour(gal/hr)',
#  22: 'GPS Accuracy(m)',
#  23: 'GPS Bearing(°)',
#  24: 'GPS Satellites',
#  25: 'GPS vs OBD Speed difference(km/h)',
#  26: 'Percentage of City driving(%)',
#  27: 'Percentage of Highway driving(%)',
#  28: 'Percentage of Idle driving(%)',
#  29: 'Speed (GPS)(km/h)',
#  30: 'Speed (OBD)(km/h)',
#  31: 'Trip Distance(km)',
#  32: 'Trip Time(Since journey start)(s)',
#  33: 'Trip time(whilst moving)(s)',
#  34: 'Trip time(whilst stationary)(s)',
#  35: 'GPSTime'}
df[df.columns[19]]
# %%
dict(enumerate(df.columns))
# %%
import matplotlib.pyplot as plt
plt.plot(df["GPSTime"].diff() [1:])
# %%
df["GPSTime"].diff()[1:].dt.total_seconds().value_counts()
# %%
