# %%
"""
Step 2 — Extract trip metrics and run similarity analysis.

Reads archive Parquets from OUTPUT_DIR/trips/, computes per-trip metrics,
writes them to OUTPUT_DIR/metrics.duckdb (for the workflow; the CLI uses CSV
instead), then runs similarity scoring and produces a Markdown report + CSV
in OUTPUT_DIR/analyses/dcca-<timestamp>/.

Equivalent CLI commands:
    uv run dcc extract <OUTPUT_DIR>
    uv run dcc analyze <OUTPUT_DIR>

Configuration is read from config.json in the same directory as this script.
"""

from datetime import datetime
from pathlib import Path
import json

import pandas as pd
import pyarrow.parquet as pq

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.schema import ParquetMetadata
from drive_cycle_calculator.trip_collection import TripCollection

# ── Configuration (loaded from config.json) ───────────────────────────────────
# set the root dir to repo root.
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]  # must contain a trips/ sub-folder of Parquets

_proc = _cfg["processing"]
PROCESSING_CONFIG = ProcessingConfig(
    window=_proc["window"],
    stop_threshold_kmh=_proc["stop_threshold_kmh"],
)

# ── Setup ──────────────────────────────────────────────────────────────────────

trips_dir = OUTPUT_DIR / "trips"
db_path = OUTPUT_DIR / "metrics.duckdb"

if not trips_dir.is_dir():
    print(f"No trips/ directory found under {OUTPUT_DIR}.")
    print("Run 010_ingest.py first.")
    raise SystemExit(1)

parquets = sorted(trips_dir.glob("*.parquet"))
print(f"Found {len(parquets)} parquet file(s) in {trips_dir}.")
# %%
# ── Extract: compute metrics → DuckDB ────────────────────────────────────────

rows: list[dict] = []

for p in parquets:
    raw_meta = pq.ParquetFile(p).schema_arrow.metadata or {}
    meta_bytes = raw_meta.get(b"dcc_metadata")
    if meta_bytes is None:
        print(f"  SKIP   {p.name}: no dcc_metadata (not a v2 archive Parquet)")
        continue

    try:
        pq_meta = ParquetMetadata.model_validate_json(meta_bytes)
    except Exception as exc:
        print(f"  SKIP   {p.name}: invalid dcc_metadata — {exc}")
        continue

    try:
        obd = OBDFile.from_parquet(p)
        trip = obd.to_trip(PROCESSING_CONFIG)
    except Exception as exc:
        print(f"  ERROR  {p.name}: {exc}")
        continue

    cts = pq_meta.computed_trip_stats
    um = pq_meta.user_metadata
    m = trip.metrics

    rows.append(
        {
            "trip_id": p.stem,
            "parquet_path": str(p.resolve()),
            "parquet_id": pq_meta.parquet_id,
            "start_time": cts.start_time,
            "end_time": cts.end_time,
            "user": um.user,
            "fuel_type": um.fuel_type,
            "vehicle_category": um.vehicle_category,
            "vehicle_make": um.vehicle_make,
            "vehicle_model": um.vehicle_model,
            "engine_size_cc": um.engine_size_cc,
            "year": um.year,
            "gps_lat_mean": cts.gps_lat_mean,
            "gps_lon_mean": cts.gps_lon_mean,
            "duration_s": m["duration"],
            "avg_velocity_kmh": m["mean_speed"],
            "max_velocity_kmh": trip.max_speed,
            "avg_acceleration_ms2": m["mean_acc"],
            "avg_deceleration_ms2": m["mean_dec"],
            "idle_time_pct": m["stop_pct"],
            "stop_count": m["stops"],
            "config_hash": PROCESSING_CONFIG.config_hash,
            "config_snapshot": PROCESSING_CONFIG.config_snapshot,
        }
    )
    print(f"  OK     {p.name}")

print(f"\nProcessed {len(rows)} trip(s).")

if not rows:
    print("No trips extracted — nothing to analyze.")
    raise SystemExit(1)

df_metrics = pd.DataFrame(rows)

import duckdb

with duckdb.connect(str(db_path)) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_metrics (
            trip_id              VARCHAR PRIMARY KEY,
            parquet_path         VARCHAR,
            parquet_id           VARCHAR,
            start_time           TIMESTAMPTZ,
            end_time             TIMESTAMPTZ,
            user                 VARCHAR,
            fuel_type            VARCHAR,
            vehicle_category     VARCHAR,
            vehicle_make         VARCHAR,
            vehicle_model        VARCHAR,
            engine_size_cc       INTEGER,
            year                 INTEGER,
            gps_lat_mean         DOUBLE,
            gps_lon_mean         DOUBLE,
            duration_s           DOUBLE,
            avg_velocity_kmh     DOUBLE,
            max_velocity_kmh     DOUBLE,
            avg_acceleration_ms2 DOUBLE,
            avg_deceleration_ms2 DOUBLE,
            idle_time_pct        DOUBLE,
            stop_count           INTEGER,
            config_hash          VARCHAR,
            config_snapshot      VARCHAR
        )
    """)
    conn.execute("INSERT OR REPLACE INTO trip_metrics SELECT * FROM df_metrics")

print(f"Metrics written to {db_path}.")

# ── Analyze: similarity scores + report ───────────────────────────────────────

tc = TripCollection.from_duckdb_catalog(db_path, config=PROCESSING_CONFIG)
print(f"\nLoaded {len(tc)} trips from catalog.")

run_dt = datetime.now()
scores = tc.similarity_scores()
sorted_scores = sorted(scores.items(), key=lambda x: -x[1])

print("\nSimilarity scores:")
for name, score in sorted_scores:
    print(f"  {name}: {score:.1f}")

rep = tc.find_representative()
print(f"\nRepresentative trip: {rep.name}")
print(f"  Mean speed:      {rep.mean_speed:.1f} km/h")
print(f"  Max speed:       {rep.max_speed:.1f} km/h")
print(f"  Stop percentage: {rep.stop_pct:.1f}%")
print(f"  Duration:        {rep.duration:.0f} s")

# ── Write analysis outputs ─────────────────────────────────────────────────────

out_dir = OUTPUT_DIR / "analyses" / f"dcca-{run_dt.strftime('%Y%m%d-%H%M')}"
out_dir.mkdir(parents=True, exist_ok=True)

trip_metrics = {t.name: t.metrics for t in tc.trips}

csv_path = out_dir / "similarity_scores.csv"
with csv_path.open("w", encoding="utf-8") as fh:
    fh.write("trip_id,score,duration,mean_speed,mean_ns,stops,stop_pct,mean_acc,mean_dec\n")
    for name, score in sorted_scores:
        m = trip_metrics[name]
        fh.write(
            f"{name},{score:.4f},{m['duration']:.0f},{m['mean_speed']:.3f},"
            f"{m['mean_ns']:.3f},{int(m['stops'])},{m['stop_pct']:.3f},"
            f"{m['mean_acc']:.4f},{m['mean_dec']:.4f}\n"
        )

m = rep.metrics
md_path = out_dir / "report.md"
with md_path.open("w", encoding="utf-8") as fh:
    fh.write("# Drive Cycle Analysis Report\n\n")
    fh.write("| | |\n|---|---|\n")
    fh.write(f"| Run | {run_dt.strftime('%Y-%m-%d %H:%M')} |\n")
    fh.write(f"| Database | `{db_path}` |\n")
    fh.write(f"| Trips | {len(tc)} |\n\n")

    fh.write("## Similarity Scores\n\n")
    fh.write("| Trip | Score |\n|---|---|\n")
    for name, score in sorted_scores:
        marker = " ★" if name == rep.name else ""
        fh.write(f"| `{name}`{marker} | {score:.1f} |\n")

    fh.write("\n## Representative Trip\n\n")
    fh.write(f"**`{rep.name}`**\n\n")
    fh.write("| Metric | Value |\n|---|---|\n")
    fh.write(f"| Duration | {m['duration']:.0f} s |\n")
    fh.write(f"| Mean speed | {m['mean_speed']:.1f} km/h |\n")
    fh.write(f"| Mean speed (no stops) | {m['mean_ns']:.1f} km/h |\n")
    fh.write(f"| Max speed | {rep.max_speed:.1f} km/h |\n")
    fh.write(f"| Stop percentage | {m['stop_pct']:.1f}% |\n")
    fh.write(f"| Stop count | {int(m['stops'])} |\n")
    fh.write(f"| Mean acceleration | {m['mean_acc']:.3f} m/s² |\n")
    fh.write(f"| Mean deceleration | {m['mean_dec']:.3f} m/s² |\n")

print(f"\nOutput written to {out_dir}")
print("  Next: run 030_build_microtrips.py")

# %%
