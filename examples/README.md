# Examples

Two-step workflow replacing the old all-in-one DriveGUI approach:

```
Step 1 (once):   ingest raw .xlsx → Parquet + DuckDB catalog
Step 2 (fast):   load from catalog → query → analyze
```

## CLI examples

```bash
# Step 1: ingest raw OBD xlsx files
python examples/cli/ingest.py ./raw_data/ ./data/

# Step 2: analyze stored trips
python examples/cli/analyze.py ./data/
```

See [cli/README.md](cli/README.md) for details.

## GUI example

```bash
python examples/gui/main.py
```

Tkinter app with folder picker and embedded Matplotlib chart. See [gui/README.md](gui/README.md).

## Storage layout

```
data/
  trips/
    2025-05-14_Morning.parquet   # one file per trip (processed DataFrame)
    2025-05-14_Evening.parquet
  metadata.duckdb                # catalog: one row per trip, metrics + parquet_path
```

## Note on DriveGUI

`students/DriveGUI/` is **frozen** — a self-contained historical reference with no package
dependencies. This `examples/` directory is its active successor.
