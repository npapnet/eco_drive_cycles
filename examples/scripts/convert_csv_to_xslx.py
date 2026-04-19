# %% [markdown]
"""
This is a script that is used to convert a folder of  csv file to xlsx


"""

# %%
import numpy as np
import pandas as pd
import pathlib
from tkinter import filedialog
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# %%


# %%
def get_skip_rows(file_path: pathlib.Path, sep=",", dec="."):
    """Reads the CSV file and identifies rows to skip based on the 3rd column's ability to parse as numeric.
    Args:
        file_path (pathlib.Path): The path to the CSV file.
        sep (str, optional): The separator used in the CSV file. Defaults to ",".
        dec (str, optional): The decimal point character used in the CSV file. Defaults to ".".
    Returns:
        np.ndarray: An array of row indices to skip (1-based).
    """
    df = pd.read_csv(file_path, sep=sep, decimal=dec)

    # 2. Isolate the 3rd column (index 2) to use as the truth guide.
    # errors='coerce' forces any text (like repeated headers) into NaN.
    reference_series = pd.to_numeric(df.iloc[:, 2], errors="coerce")

    # 3. Create a mask keeping only rows where the 3rd column successfully parsed as a number.
    # (If your valid data actually contains legitimate NaNs in this column that you want to keep,
    # use: valid_mask = reference_series.notna() | df.iloc[:, 2].isna())
    valid_mask = reference_series.notna()

    # The commented code if returnng the cleaned DataFrame instead of skiprows,
    # but this is not needed for the current use case
    # # 4. Filter the DataFrame.
    # df_clean = df[valid_mask].copy()
    #
    # # 5. Clean up data types safely across the entire DataFrame
    # # Iterating through columns and catching exceptions replaces the deprecated 'ignore'
    # for col in df_clean.columns:
    #     try:
    #         df_clean[col] = pd.to_numeric(df_clean[col])
    #     except (ValueError, TypeError):
    #         # If conversion fails (e.g., the column contains actual text data), leave it as is
    #         pass
    # df_clean.reset_index(drop=True, inplace=True)

    # create skiprows array (1-based index for pandas)
    skiprows = df.index[~valid_mask].to_numpy() + 1

    return skiprows


def convert_csv_to_xlsx(file_path: pathlib.Path, sep=",", dec=".", skiprows=None):
    assert file_path.suffix == ".csv", "The selected file must be a CSV file."
    assert isinstance(file_path, pathlib.Path), "The file path must be a pathlib.Path object."
    assert file_path.exists(), "The file path does not exist"

    # Read the CSV file into a DataFrame
    df = pd.read_csv(file_path, sep=sep, decimal=dec, skiprows=skiprows)

    # Create the output file path by changing the extension to .xlsx
    output_file_path = file_path.parents[1] / file_path.with_suffix(".xlsx").name

    # Write the DataFrame to an Excel file
    df.to_excel(output_file_path, index=False)

    logging.info("Converted %s to %s", file_path, output_file_path)


## %% Do a single file
## Open a file dialog to select a file  containing the CSV files
#
# sep = ","
# dec = "."
# file_path = filedialog.askopenfilename(title="Select a CSV file")
#
#
# file_path = pathlib.Path(file_path)
#
# skiprows = get_skip_rows(file_path, sep=sep, dec=dec)
# print(f"Skipping rows: {skiprows}")
#
# convert_csv_to_xlsx(file_path=file_path, sep=sep, dec=dec, skiprows=skiprows)

# %%[markdown]

# %%
sep = ";"
dec = ","


folder_path = filedialog.askdirectory(title="Select Folder Containing CSV Files")
# %%
print(folder_path)
# collect csv files
csv_files = list(pathlib.Path(folder_path).glob("*.csv"))
print(f"Found {len(csv_files)} CSV files in the folder.")
for csv_file in csv_files:
    print(f"Converting {csv_file.name}...", end="")
    _skip_rows = get_skip_rows(csv_file, sep=sep, dec=dec)
    print(f"Skipping rows: {_skip_rows}")
    try:
        convert_csv_to_xlsx(file_path=csv_file, sep=sep, dec=dec, skiprows=_skip_rows)
    except Exception as e:
        print(f"Error converting {csv_file.name}: {e}")

    print("Done.")
# %%
