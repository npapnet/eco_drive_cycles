"""
Inspect a raw OBD xlsx file before any processing.

Shows the unmodified DataFrame exactly as Torque exported it — raw column
names, dtypes, sensor-off markers ("-"), and a sample of values. Useful
for diagnosing data-quality issues or understanding what the ingest pipeline
receives as input.

Usage:
    python examples/cli/inspect_raw.py <path/to/file.xlsx>

Example:
    python examples/cli/inspect_raw.py raw_data/trackLog-2019-Sep-20_10-49-22.xlsx
"""
import sys
from pathlib import Path

from drive_cycle_calculator.metrics import load_raw_df

if len(sys.argv) < 2:
    print("Usage: python examples/cli/inspect_raw.py <path/to/file.xlsx>")
    sys.exit(1)

path = Path(sys.argv[1])
print(f"Loading raw file: {path}\n")

df = load_raw_df(path)

print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")

print("── Columns, dtypes, and non-null counts ─────────────────────────────────")
for col in df.columns:
    n_non_null = df[col].notna().sum()
    # Count how many are the Torque "-" placeholder
    n_dash = (df[col] == "-").sum() if df[col].dtype == object else 0
    dash_note = f"  ({n_dash} sensor-off '-')" if n_dash else ""
    print(f"  {col!r:50s}  dtype={str(df[col].dtype):8s}  non-null={n_non_null}/{len(df)}{dash_note}")

print("\n── First 5 rows (key OBD columns) ──────────────────────────────────────")
key_cols = [c for c in df.columns if any(k in c for k in [
    "GPS Time", "Speed (OBD)", "CO", "Engine Load", "Fuel flow",
])]
print(df[key_cols].head(5).to_string())

print("\n── Sample unique values per key column ─────────────────────────────────")
for col in key_cols:
    sample = df[col].dropna().unique()[:5].tolist()
    print(f"  {col!r}: {sample}")
