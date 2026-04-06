"""
Step 1: Ingest raw OBD xlsx files into Parquet + DuckDB catalog.
Run once per data collection batch. Re-run after algorithm changes to update the cache.

Usage:
    python examples/cli/ingest.py ./raw_data/ ./data/
"""
import sys
from pathlib import Path

from drive_cycle_calculator.metrics.trip import TripCollection

raw_dir = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
trips_dir = out_dir / "trips"
db_path = out_dir / "metadata.duckdb"

trips_dir.mkdir(parents=True, exist_ok=True)

print(f"Reading raw files from {raw_dir}...")
tc = TripCollection.from_folder(raw_dir)
print(f"  Found {len(tc)} valid trips.")

if len(tc) == 0:
    print("No trips found — nothing to ingest.")
    sys.exit(0)

print(f"Writing Parquet files to {trips_dir}...")
tc.to_parquet(trips_dir)

print(f"Updating DuckDB catalog at {db_path}...")
tc.to_duckdb_catalog(db_path)

print("Done. Run analyze.py to query the stored data.")
