# CLI Examples

## ingest.py

Reads raw OBD `.xlsx` files from a folder, processes them in-memory, writes:
- One `.parquet` file per trip to `<out_dir>/trips/`
- One metadata row per trip to `<out_dir>/metadata.duckdb`

```bash
python examples/cli/ingest.py <raw_xlsx_dir> <output_dir>
```

Re-running overwrites existing Parquet files (safe to re-run after algorithm updates).

## analyze.py

Loads trips from the DuckDB catalog (no raw file reprocessing), computes similarity
scores, and prints the representative trip.

```bash
python examples/cli/analyze.py <output_dir>
```
