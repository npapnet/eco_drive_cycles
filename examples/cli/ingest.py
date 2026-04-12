"""
Step 1: Ingest raw OBD xlsx files into v2 archive Parquets + DuckDB catalog.
Run once per data collection batch. Re-run after algorithm changes to update the cache.

Usage:
    python examples/cli/ingest.py ./raw_data/ ./data/
"""

# %% [markdown]
"""
> [!WARNING]
> OBSOLETE
> This script is obsolete. The logic has been integrated natively into `dcc ingest`.
> Use `uv run dcc ingest <raw_dir> <out_dir>` instead. 
> This file remains for reference.

## Legacy Ingest pipeline (Decoupled from TripCollection)

1. `OBDFile.from_file(path)` — loads file (Excel or CSV) as raw OBDFile.
2. Inspect quality via `quality_report()` and skip files with missing CURATED_COLS
3. `OBDFile.to_parquet()` — write v2 archive Parquets
4. `TripCollection.from_archive_parquets()` — process archives
5. `TripCollection.to_duckdb_catalog()` — upsert trip metadata into DuckDB
"""

# %%
import sys
from pathlib import Path

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.trip_collection import TripCollection

raw_dir = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
archive_dir = out_dir / "trips"
db_path = out_dir / "metadata.duckdb"

archive_dir.mkdir(parents=True, exist_ok=True)

# %%
print(f"Loading raw files from {raw_dir}...")
raw_files = list(raw_dir.glob("*.xlsx")) + list(raw_dir.glob("*.xls")) + list(raw_dir.glob("*.csv"))
print(f"  Found {len(raw_files)} raw files.")

if not raw_files:
    print("No files found — nothing to ingest.")
    sys.exit(0)

# %%
print("Writing v2 archive Parquets...")
archived = []
for f in raw_files:
    try:
        obd = OBDFile.from_file(f)
    except Exception as exc:
        print(f"  ERROR {f.name}: {exc}")
        continue

    report = obd.quality_report()
    missing = report["missing_curated_cols"]
    if missing:
        print(f"  SKIP {obd.name}: missing columns {missing}")
        continue

    dest = archive_dir / f"{obd.name}.parquet"
    obd.to_parquet(dest)
    archived.append(obd.name)
    print(f"  OK   {obd.name} -> {dest.name}")

print(f"  Archived {len(archived)} trips, skipped {len(raw_files) - len(archived)}.")

if not archived:
    print("No valid trips to catalog.")
    sys.exit(0)

# %%
print(f"Building TripCollection from archives in {archive_dir}...")
tc = TripCollection.from_archive_parquets(archive_dir)
print(f"  Loaded {len(tc)} trips.")

print(f"Updating DuckDB catalog at {db_path}...")
tc.to_duckdb_catalog(db_path)

print("Done. Run analyze.py to query the stored data.")
