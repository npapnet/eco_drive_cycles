"""
> [!WARNING]
> OBSOLETE
> This script is obsolete. The logic has been integrated natively into `dcc analyze`.
> Use `uv run dcc analyze <data_dir>` instead. 
> This file remains for reference.

Step 2: Load stored trips from DuckDB catalog and analyze.
Runs instantly — no raw file reprocessing.

Usage:
    python examples/cli/analyze.py ./data/
"""

import sys
from pathlib import Path

from drive_cycle_calculator.trip_collection import TripCollection

out_dir = Path(sys.argv[1])
db_path = out_dir / "metadata.duckdb"

if not db_path.exists():
    print(f"No catalog found at {db_path}. Run ingest.py first.")
    sys.exit(1)

print(f"Loading catalog from {db_path}...")
tc = TripCollection.from_duckdb_catalog(db_path)
print(f"  {len(tc)} trips in catalog.")

if len(tc) == 0:
    print("Catalog is empty.")
    sys.exit(0)

print("\nSimilarity scores:")
for name, score in sorted(tc.similarity_scores().items(), key=lambda x: -x[1]):
    print(f"  {name}: {score:.1f}")

rep = tc.find_representative()
print(f"\nRepresentative trip: {rep.name}")
print(f"  Mean speed:      {rep.mean_speed:.1f} km/h")
print(f"  Max speed:       {rep.max_speed:.1f} km/h")
print(f"  Stop percentage: {rep.stop_pct:.1f}%")
print(f"  Duration:        {rep.duration:.0f} s")

# TODO: microtrip segmentation (see TODOS.md P1)
# for mt in rep.microtrips:
#     print(f"  microtrip: {mt.duration:.0f}s, {mt.mean_speed:.1f} km/h")
