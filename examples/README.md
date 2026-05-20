# Examples

Complete workflow from raw OBD data to microtrip segments and synthesized drive cycles.

```
Step 1:  ingest raw .xlsx / .csv → archive Parquets
Step 2:  extract metrics → DuckDB + similarity report
Step 3:  segment trips → microtrip Parquets + summary
Step 4:  cluster microtrips → data-driven KMeans clustering
Step 5:  synthesize drive cycles → via WLTP (GTR 15) or Cluster-based synthesis
```

## Workflow

```bash
# Step 1: Ingest raw OBD files
uv run python examples/workflow/010_ingest.py

# Step 2: Compute metrics and run similarity analysis
uv run python examples/workflow/020_extract_analyze.py

# Step 3: Segment trips into microtrips
uv run python examples/workflow/030_build_microtrips.py

# Step 4: Cluster microtrips
uv run python examples/workflow/040_microtrip_clustering.py
```

Parameters, input directories, and output folders are managed in `examples/workflow/config.json`. See [workflow/README.md](workflow/README.md) for details.

## GUI Example

```bash
python examples/gui/main.py
```

Tkinter app with folder picker and embedded Matplotlib chart. See [gui/README.md](gui/README.md).

## Storage Layout

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

`students/DriveGUI/` is **frozen** — a self-contained historical reference with no package dependencies. This `examples/` directory is its active successor.
