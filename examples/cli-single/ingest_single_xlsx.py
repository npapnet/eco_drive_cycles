# %%[markdown]
"""
Load and ingest a raw OBD xlsx file before any processing.

Shows the unmodified DataFrame exactly as Torque exported it — raw column
names, dtypes, sensor-off markers ("-"), and a sample of values. Useful
for diagnosing data-quality issues or understanding what the ingest pipeline
receives as input.

Usage:
    python examples/cli-single/inspect_raw.py <path/to/file.xlsx>

Example:
    python examples/cli-single/inspect_raw.py raw_data/trackLog-2019-Sep-20_10-49-22.xlsx
"""

# %%
import sys
from pathlib import Path

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.misc import parse_gps_time_torque

# %%

# if len(sys.argv) < 2:
#     # Requires at least one argument
#     print("Usage: python examples/cli/inspect_raw.py <path/to/file.xlsx>")
#     sys.exit(1)
# else:
#     path = Path(sys.argv[1])

# %% For use with interactive system
ROOTDIR = Path(__file__).parents[2]
DATADIR = ROOTDIR / "raw_data"
assert DATADIR.exists()

# find all xlsx files in DATADIR
xlsx_files = list(DATADIR.glob("*.xlsx"))
assert len(xlsx_files) > 0

# pick one file
path = xlsx_files[0]
print(path)
# %%

print(f"Loading raw file: {path}\n")

obd = OBDFile.from_xlsx(path)

df = obd.full_df
# %%
obd.quality_report()

# %%

obd.to_parquet("gps_time.parquet")
print(obd._df["GPS Time"].dtype)
print(obd._df["GPS Time"].memory_usage(index=True, deep=False))
obd._df.iloc[0, 0]
# %%
import pyarrow as pa
import pyarrow.parquet as pq

df_withdt = obd._df.copy()
df_withdt["GPS Time"] = parse_gps_time_torque(df_withdt["GPS Time"])
# df_withdt[" Device Time"] = parse_gps_time_torque(df_withdt[" Device Time"])

table = pa.Table.from_pandas(df_withdt)
# %%

columns_for_dict = [col for col in table.column_names if col not in ["GPS Time", " Device Time"]]
columns_for_dict = False
pq.write_table(
    table,
    "gps_time_parsed_opt.parquet",
    compression="zstd",
    use_dictionary=columns_for_dict,
    write_statistics=True,
    version="2.6",
)
print(obd._df["GPS Time"].dtype)
print(obd._df["GPS Time"].memory_usage(index=True, deep=False))


# %%
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
