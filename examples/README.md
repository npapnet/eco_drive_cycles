# Examples

Three-step workflow from raw OBD data to microtrip segments.

```
Step 1:  ingest raw .xlsx / .csv → archive Parquets
Step 2:  extract metrics → DuckDB + similarity report
Step 3:  segment trips → microtrip Parquets + summary
```

## Workflow

```bash
# Step 1: ingest raw OBD files
uv run python examples/workflow/01_ingest.py

# Step 2: compute metrics and run similarity analysis
uv run python examples/workflow/02_extract_analyze.py

# Step 3: segment trips into microtrips
uv run python examples/workflow/03_microtrips.py
```

Edit the constants at the top of each script (`DATA_DIR`, `OUTPUT_DIR`, etc.)
to point at your data. See [workflow/README.md](workflow/README.md) for details.

## GUI example

```bash
python examples/gui/main.py
```

Tkinter app with folder picker and embedded Matplotlib chart. See [gui/README.md](gui/README.md).

## Storage layout

```
data/
  trips/
    t20250514-083012-2674-ab3f7c.parquet   # one archive Parquet per trip
    t20250514-183012-1820-cd9e12.parquet
  metrics.duckdb                            # trip_metrics table (extract output)
  microtrips/
    t20250514-083012-2674-ab3f7c_mt00.parquet
    t20250514-083012-2674-ab3f7c_mt01.parquet
    summary.csv
  analyses/
    dcca-20250514-1430/
      report.md
      similarity_scores.csv
```

## Note on DriveGUI

`students/DriveGUI/` is **frozen** — a self-contained historical reference with no package
dependencies. This `examples/` directory is its active successor.
