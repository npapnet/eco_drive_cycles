# Workflow Examples

Complete three-step pipeline from raw OBD data to microtrip segments.
Run from the repository root with `uv run python examples/workflow/<script>`.

## Scripts

### `01_ingest.py` — Raw → Archive Parquets

Reads `.xlsx` / `.xls` / `.csv` files from `DATA_DIR` and writes one v2
archive Parquet per trip to `OUTPUT_DIR/trips/`.  Existing files are skipped
by default; set `FORCE = True` in the script to overwrite.

```bash
uv run python examples/workflow/01_ingest.py
```

Equivalent CLI: `uv run dcc ingest <DATA_DIR> <OUTPUT_DIR>`

---

### `02_extract_analyze.py` — Metrics + Similarity Report

Reads archive Parquets from `OUTPUT_DIR/trips/`, computes per-trip metrics
into `OUTPUT_DIR/metrics.duckdb`, then runs 7-metric similarity scoring and
writes:

- `OUTPUT_DIR/analyses/dcca-<timestamp>/similarity_scores.csv`
- `OUTPUT_DIR/analyses/dcca-<timestamp>/report.md`

```bash
uv run python examples/workflow/02_extract_analyze.py
```

Equivalent CLI: `uv run dcc extract <OUTPUT_DIR>` then `uv run dcc analyze <OUTPUT_DIR>`

---

### `03_microtrips.py` — Microtrip Segmentation

Segments every trip into stop-to-stop motion segments and writes:

- `OUTPUT_DIR/microtrips/<trip>_mt<N>.parquet` — samples for each microtrip
  (motion phase + trailing stop, distinguished by `stop_phase` column)
- `OUTPUT_DIR/microtrips/summary.csv` — one row per microtrip with key stats

```bash
uv run python examples/workflow/03_microtrips.py
```

## Configuration

Edit the constants at the top of each script:

| Constant | Default | Description |
|---|---|---|
| `DATA_DIR` | `raw_data` | Source folder for raw OBD exports |
| `OUTPUT_DIR` | `data` | Root output folder |
| `FORCE` | `False` | Overwrite existing Parquets (script 01 only) |
| `PROCESSING_CONFIG` | `window=4, stop=2.0 km/h` | Smoothing and stop detection |
| `SEGMENTATION_CONFIG` | see script | Microtrip boundary thresholds |
