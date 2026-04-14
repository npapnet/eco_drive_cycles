# %%[markdown]
"""
# Parquet Metadata

This script demonstrates how to read and display metadata from a Parquet file using the `pyarrow` library.

Parquet is a columnar storage file format that is optimized for use with big data processing frameworks.

"""

# %%
import pathlib
import pyarrow.parquet as pq
import pandas as pd


# %% [markdown]
"""
# Example saving metadata in Parquet file


"""
# %%
# # Sample DataFrame
# df = pd.DataFrame({"data_column": [10.5, 20.1, 30.7]})

# # Convert to Table
# table = pa.Table.from_pandas(df)

# # Define custom metadata (keys and values must be strings/bytes)
# custom_metadata = {
#     "User": "ME_Lecturer_01",
#     "creation_time": datetime.datetime.now().isoformat(),
#     "Project_ID": "Vibration_Analysis_2026",
# }

# # Merge with existing schema metadata
# existing_meta = table.schema.metadata
# combined_meta = {**existing_meta, **{k.encode(): v.encode() for k, v in custom_metadata.items()}}
# table = table.replace_schema_metadata(combined_meta)

# # Write to Parquet
# pq.write_table(table, "engineering_data.parquet")
# %% [markdown]
"""
# Retrieving Data
"""
# %%
ROOTDIR = pathlib.Path(__file__).parent.parent.parent
DATADIR = ROOTDIR / "data" / "trips"
print(ROOTDIR)
print(DATADIR)

pq_files = list(DATADIR.glob("*.parquet"))
FNAME = pq_files[0]
print(f"Reading metadata from: {FNAME}")

# %%
pqf = pq.ParquetFile(FNAME)
metadata = pqf.metadata
# %%
mtd = pqf.schema.to_arrow_schema().metadata
print(type(mtd))
# %%
mtd.get(b"format_version")
# %%
