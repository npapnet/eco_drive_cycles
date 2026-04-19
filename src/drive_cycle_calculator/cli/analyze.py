from pathlib import Path

import typer

from drive_cycle_calculator.trip_collection import TripCollection

app = typer.Typer(help="Load stored trips from DuckDB catalog and analyze.")

@app.callback(invoke_without_command=True)
def analyze(
    data_dir: Path = typer.Argument(
        ...,
        help="Directory containing the DuckDB catalog.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
):
    db_path = data_dir / "metrics.duckdb"

    if not db_path.exists():
        typer.secho(f"No metrics DB found at {db_path}. Run 'dcc extract' first.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"Loading catalog from {db_path}...")
    tc = TripCollection.from_duckdb_catalog(db_path)
    typer.echo(f"  {len(tc)} trips in catalog.")

    if len(tc) == 0:
        typer.secho("Catalog is empty.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    typer.echo("\nSimilarity scores:")
    for name, score in sorted(tc.similarity_scores().items(), key=lambda x: -x[1]):
        typer.echo(f"  {name}: {score:.1f}")

    rep = tc.find_representative()
    typer.echo(f"\nRepresentative trip: {rep.name}")
    typer.echo(f"  Mean speed:      {rep.mean_speed:.1f} km/h")
    typer.echo(f"  Max speed:       {rep.max_speed:.1f} km/h")
    typer.echo(f"  Stop percentage: {rep.stop_pct:.1f}%")
    typer.echo(f"  Duration:        {rep.duration:.0f} s")
