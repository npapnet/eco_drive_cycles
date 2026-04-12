import sys
from pathlib import Path
from typing import Optional, Literal

import typer

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.trip_collection import TripCollection

app = typer.Typer(help="Ingest raw OBD files into DuckDB catalog.")

@app.callback(invoke_without_command=True)
def ingest(
    raw_dir: Path = typer.Argument(
        ...,
        help="Directory containing raw OBD exports (.xlsx or .csv)",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    out_dir: Path = typer.Argument(
        ...,
        help="Directory to save the DuckDB catalog and archive parquets",
        file_okay=False,
    ),
    format: str = typer.Option(
        "auto",
        "--format",
        "-f",
        help="File format to search for. 'auto' relies on file extension.",
    ),
    sep: Optional[str] = typer.Option(
        None,
        help="CSV delimiter (e.g., ',' or ';'). If missing, auto-sniffed.",
    ),
    decimal: Optional[str] = typer.Option(
        None,
        help="CSV decimal separator (e.g., '.' or ','). If missing, auto-inferred.",
    ),
):
    archive_dir = out_dir / "trips"
    db_path = out_dir / "metadata.duckdb"

    archive_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Scanning for {format} files in {raw_dir}...")
    
    # Resolve the glob pattern
    if format == "auto":
        files = list(raw_dir.glob("*.xlsx")) + list(raw_dir.glob("*.xls")) + list(raw_dir.glob("*.csv"))
    elif format in ("xlsx", "xls"):
        files = list(raw_dir.glob("*.xlsx")) + list(raw_dir.glob("*.xls"))
    elif format == "csv":
        files = list(raw_dir.glob("*.csv"))
    else:
        typer.secho(f"Unknown format: {format}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not files:
        typer.echo(f"No {format} files found — nothing to ingest.")
        raise typer.Exit()

    typer.echo(f"  Found {len(files)} raw files.")
    typer.echo("Writing v2 archive Parquets...")

    archived = []
    
    # Iterate and use our new from_file factory!
    for f in sorted(files):
        try:
            obd = OBDFile.from_file(f, sep=sep, decimal=decimal)
        except Exception as exc:
            typer.secho(f"  ERROR {f.name}: {exc}", fg=typer.colors.RED)
            continue
            
        report = obd.quality_report()
        missing = report["missing_curated_cols"]
        if missing:
            typer.secho(f"  SKIP  {obd.name}: missing columns {missing}", fg=typer.colors.YELLOW)
            continue
            
        dest = archive_dir / f"{obd.parquet_name}.parquet"
        obd.to_parquet(dest)
        archived.append(obd.parquet_name)
        typer.secho(f"  OK    {obd.name} -> {dest.name}", fg=typer.colors.GREEN)

    typer.echo(f"  Archived {len(archived)} trips, skipped {len(files) - len(archived)}.")

    if not archived:
        typer.echo("No valid trips to catalog.")
        raise typer.Exit()

    typer.echo(f"Building TripCollection from archives in {archive_dir}...")
    tc = TripCollection.from_archive_parquets(archive_dir)
    typer.echo(f"  Loaded {len(tc)} trips.")

    typer.echo(f"Updating DuckDB catalog at {db_path}...")
    tc.to_duckdb_catalog(db_path)

    typer.secho("Done. Run 'dcc analyze' to query the stored data.", fg=typer.colors.GREEN)
