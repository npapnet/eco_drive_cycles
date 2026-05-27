# Pipeline Architecture

The full data pipeline from raw OBD export to synthesized drive cycle.

---

## End-to-End Data Flow

```{mermaid}
flowchart TD
    raw["Raw .xlsx / .csv\n(OBD-II via Torque)"]

    subgraph ingest["Ingestion"]
        ci["dcc config-init\nGenerate metadata YAML"]
        yaml["[User fills metadata YAML]"]
        ing["dcc ingest\nRaw → 1 Hz Archive Parquet\nEmbeds ParquetMetadata"]
        ci --> yaml --> ing
    end

    subgraph metrics["Metrics Branch"]
        ext["dcc extract\nParquets → trip_metrics\nDuckDB / CSV / XLSX"]
        ana["dcc analyze\nSimilarity scores\nRepresentative trip"]
        ext --> ana
    end

    subgraph synthesis["Synthesis Branch"]
        seg["MicrotripSegmenter\nDetect stop boundaries\nBuild microtrip list"]
        cls["KMeans Clustering\nworkflow 040"]
        syn["Cycle Synthesis\nWLTP or Cluster-based"]
        seg --> cls --> syn
    end

    raw --> ingest
    ing --> metrics
    ing --> synthesis
```

---

## Ingestion

Raw OBD exports from the Torque app (`.xlsx`, `.csv`) are cleaned, resampled to a
uniform 1 Hz time grid, and written as v2 archive Parquets. Each Parquet embeds a
`ParquetMetadata` block containing user-supplied metadata (vehicle, driver), ingest
provenance (timestamp, source filename), and GPS-derived statistics.

```
dcc config-init <raw_dir>          # writes metadata-<raw_dir>.yaml
# [edit the YAML: vehicle make/model, driver, fuel type, …]
dcc ingest <raw_dir> <out_dir>     # raw → out_dir/trips/*.parquet
```

Existing Parquets are skipped by default; use `--force` to overwrite.

**Parquet filename convention:** `t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>.parquet`
where `hash6 = sha256(lat_bytes + lon_bytes)[:6]`.

---

## Metrics Branch

`dcc extract` reads every archive Parquet in `out_dir/trips/`, applies
`ProcessingConfig` (smoothing, stop detection), and writes all per-trip scalar metrics
into a DuckDB file (`metrics.duckdb`) as well as a CSV and XLSX copy.

`dcc analyze` reads the DuckDB metrics and computes pairwise similarity scores across
seven kinematic metrics, then identifies the most representative trip.

```
dcc extract <out_dir>    # → out_dir/metrics.duckdb + CSV/XLSX
dcc analyze <out_dir>    # → similarity_scores.csv + report.md
```

---

## Synthesis Branch

After ingestion, `MicrotripSegmenter` slices each trip into stop-to-stop motion
segments (microtrips). Each microtrip carries its speed profile, duration, distance,
and a trailing-stop period.

The segments are then clustered (KMeans) to group similar driving behaviours, and a
stochastic Markov-guided selection algorithm assembles a synthetic representative drive
cycle that statistically matches fleet-level kinematic targets.

Two synthesis strategies are available:

| Strategy | Groups | Config |
|---|---|---|
| [WLTP (GTR 15)](quickstart/synthesis-wltp.md) | Fixed speed phases: Low / Med / High / xHigh | `config_wltp.json` |
| [Cluster-based](quickstart/synthesis-cluster.md) | Data-driven KMeans clusters | `config_syn_cluster.json` |

---

## Processed DataFrame Columns

After `ProcessingConfig.apply()` every trip DataFrame contains:

| Column | Description |
|---|---|
| `elapsed_s` | Elapsed time from trip start (seconds) |
| `speed_kmh` | Raw OBD speed |
| `smooth_speed_kmh` | Rolling-window smoothed speed |
| `acc_ms2` | Acceleration derived from smoothed speed |
| `co2_g_per_km` | CO₂ average (g/km) |
| `engine_load_pct` | Engine load (%) |
| `fuel_flow_lph` | Fuel flow rate (l/hr) |

> `speed_ms`, `acceleration_ms2`, `deceleration_ms2` do not exist in processed output.

---

## DuckDB Schema (`trip_metrics`)

One row per trip. Columns: `trip_id`, `parquet_path`, `parquet_id`, `start_time`,
`end_time`, all `UserMetadata` fields (flattened), GPS stats, trip scalar metrics,
`config_hash`, `config_snapshot`.
