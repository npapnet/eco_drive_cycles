"""
Step 1: Ingest raw OBD xlsx files into v2 archive Parquets + DuckDB catalog.
Run once per data collection batch. Re-run after algorithm changes to update the cache.

Usage:
    python examples/cli/ingest.py ./raw_data/ ./data/
"""

# %% [markdown]
"""
## Ingest pipeline

1. `TripCollection.from_folder_raw()` — loads all .xlsx as raw OBDFile objects (no processing yet)
2. Inspect quality via `quality_report()` and skip files with missing CURATED_COLS
3. `OBDFile.to_parquet()` — write v2 archive Parquets (all raw columns, no derived cols)
4. `TripCollection.from_archive_parquets()` — process archives -> Trips via ProcessingConfig
5. `TripCollection.to_duckdb_catalog()` — upsert trip metadata + config_hash into DuckDB
"""

# %%
import sys
from pathlib import Path

from drive_cycle_calculator.metrics.trip_collection import TripCollection

raw_dir = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
archive_dir = out_dir / "trips"
db_path = out_dir / "metadata.duckdb"

archive_dir.mkdir(parents=True, exist_ok=True)

# %%
print(f"Loading raw xlsx files from {raw_dir}...")
raw_files = TripCollection.from_folder_raw(raw_dir)
print(f"  Found {len(raw_files)} raw files.")

if not raw_files:
    print("No xlsx files found — nothing to ingest.")
    sys.exit(0)

# %%
print("Writing v2 archive Parquets...")
archived = []
for obd in raw_files:
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
