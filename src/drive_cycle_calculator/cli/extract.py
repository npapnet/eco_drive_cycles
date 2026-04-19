# %%
# %%
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq
import typer

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.schema import ParquetMetadata, ProcessingConfig

app = typer.Typer(help="Extract trip metrics from archive Parquets into DuckDB / CSV / XLSX.")


@app.callback(invoke_without_command=True)
def extract(
    data_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory containing a trips/ sub-folder of archive Parquets.",
    ),
    output: str = typer.Option(
        "duckdb",
        "--output",
        "-o",
        help="Output format: duckdb, csv, or xlsx.",
    ),
    out_file: Optional[Path] = typer.Option(
        None,
        "--out-file",
        help="Output file path. Defaults to <data_dir>/metrics.{duckdb,csv,xlsx}.",
    ),
    window: int = typer.Option(
        4,
        "--window",
        help="ProcessingConfig rolling-window size (samples).",
    ),
    stop_threshold: float = typer.Option(
        2.0,
        "--stop-threshold",
        help="ProcessingConfig stop threshold in km/h.",
    ),
    from_date: Optional[str] = typer.Option(
        None,
        "--from",
        help="Filter trips whose start_time >= this ISO 8601 date.",
    ),
    to_date: Optional[str] = typer.Option(
        None,
        "--to",
        help="Filter trips whose end_time <= this ISO 8601 date.",
    ),
    lat_min: Optional[float] = typer.Option(
        None, "--lat-min", help="Filter: min GPS latitude centroid."
    ),
    lat_max: Optional[float] = typer.Option(
        None, "--lat-max", help="Filter: max GPS latitude centroid."
    ),
    lon_min: Optional[float] = typer.Option(
        None, "--lon-min", help="Filter: min GPS longitude centroid."
    ),
    lon_max: Optional[float] = typer.Option(
        None, "--lon-max", help="Filter: max GPS longitude centroid."
    ),
) -> None:
    trips_dir = data_dir / "trips"
    if not trips_dir.is_dir():
        typer.secho(f"No trips/ directory found under {data_dir}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if output not in ("duckdb", "csv", "xlsx"):
        typer.secho(
            f"Unknown output format: {output!r}. Use duckdb, csv, or xlsx.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    ext_map = {"duckdb": ".duckdb", "csv": ".csv", "xlsx": ".xlsx"}
    if out_file is None:
        out_file = data_dir / f"metrics{ext_map[output]}"

    config = ProcessingConfig(window=window, stop_threshold_kmh=stop_threshold)
    dt_from = _parse_iso_date("--from", from_date)
    dt_to = _parse_iso_date("--to", to_date)

    parquets = sorted(trips_dir.glob("*.parquet"))
    typer.echo(f"Found {len(parquets)} parquet file(s) in {trips_dir}.")

    rows: list[dict] = []
    for p in parquets:
        # Read only PyArrow schema metadata — no column data loaded
        raw_meta = pq.ParquetFile(p).schema_arrow.metadata or {}
        meta_bytes = raw_meta.get(b"dcc_metadata")
        if meta_bytes is None:
            typer.secho(
                f"  SKIP   {p.name}: no dcc_metadata (legacy parquet)",
                fg=typer.colors.YELLOW,
            )
            continue

        try:
            pq_meta = ParquetMetadata.model_validate_json(meta_bytes)
        except Exception as exc:
            typer.secho(
                f"  SKIP   {p.name}: invalid dcc_metadata — {exc}",
                fg=typer.colors.YELLOW,
            )
            continue

        cts = pq_meta.computed_trip_stats

        # Apply date filters (timezone-naive comparison)
        if dt_from is not None and cts.start_time is not None:
            if cts.start_time.replace(tzinfo=None) < dt_from:
                continue
        if dt_to is not None and cts.end_time is not None:
            if cts.end_time.replace(tzinfo=None) > dt_to:
                continue

        # Apply GPS centroid filters
        if lat_min is not None and cts.gps_lat_mean < lat_min:
            continue
        if lat_max is not None and cts.gps_lat_mean > lat_max:
            continue
        if lon_min is not None and cts.gps_lon_mean < lon_min:
            continue
        if lon_max is not None and cts.gps_lon_mean > lon_max:
            continue

        try:
            obd = OBDFile.from_parquet(p)
            trip = obd.to_trip(config)
        except Exception as exc:
            typer.secho(f"  ERROR  {p.name}: {exc}", fg=typer.colors.RED)
            continue

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
                "config_hash": config.config_hash,
                "config_snapshot": config.config_snapshot,
            }
        )
        typer.secho(f"  OK     {p.name}", fg=typer.colors.GREEN)

    typer.echo(f"\n  Processed {len(rows)} trip(s).")

    if not rows:
        typer.echo("No trips matched filters — nothing written.")
        raise typer.Exit()

    df = pd.DataFrame(rows)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if output == "duckdb":
        _write_duckdb(df, out_file)
    elif output == "csv":
        df.to_csv(out_file, index=False)
        typer.secho(f"  Written: {out_file}", fg=typer.colors.GREEN)
    elif output == "xlsx":
        df.to_excel(out_file, index=False)
        typer.secho(f"  Written: {out_file}", fg=typer.colors.GREEN)

    typer.secho(f"Done. Output: {out_file}", fg=typer.colors.GREEN)


def _parse_iso_date(flag: str, value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        typer.secho(
            f"Invalid {flag} date: {value!r}. Use ISO 8601 (e.g. 2024-01-01).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def _write_duckdb(df: pd.DataFrame, db_path: Path) -> None:
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
        conn.execute("INSERT OR REPLACE INTO trip_metrics SELECT * FROM df")
    typer.secho(f"  Written: {db_path}", fg=typer.colors.GREEN)
