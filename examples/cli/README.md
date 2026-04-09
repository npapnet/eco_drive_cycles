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


## Expected output

Using the 2019 September dataset  when running the `uv run python examples/cli/analyze.py data/` command, the results should be:

```
Similarity scores:
  trackLog-2019-Sep-18_11-05-05: 97.8
  trackLog-2019-Sep-16_10-58-16: 95.7
  trackLog-2019-Sep-21_11-02-29: 95.4
  trackLog-2019-Sep-19_10-52-57: 94.1
  trackLog-2019-Sep-20_10-49-22: 91.4
  trackLog-2019-Sep-16_18-45-06: 89.1
  trackLog-2019-Sep-22_18-47-12: 88.0
  trackLog-2019-Sep-19_18-39-31: 86.3
  trackLog-2019-Sep-22_10-32-18: 85.4
  trackLog-2019-Sep-17_11-02-01: 83.2
  trackLog-2019-Sep-18_18-47-50: 80.7
  trackLog-2019-Sep-17_18-38-19: 72.9
  trackLog-2019-Sep-21_18-37-01: 68.8
  trackLog-2019-Sep-20_18-37-12: 64.7

Representative trip: trackLog-2019-Sep-18_11-05-05
  Mean speed:      23.8 km/h
  Max speed:       60.2 km/h
  Stop percentage: 11.0%
  Duration:        2674 s
```