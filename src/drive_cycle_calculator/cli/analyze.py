from datetime import datetime
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

    run_dt = datetime.now()

    scores = tc.similarity_scores()
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])

    typer.echo("\nSimilarity scores:")
    for name, score in sorted_scores:
        typer.echo(f"  {name}: {score:.1f}")

    rep = tc.find_representative()
    typer.echo(f"\nRepresentative trip: {rep.name}")
    typer.echo(f"  Mean speed:      {rep.mean_speed:.1f} km/h")
    typer.echo(f"  Max speed:       {rep.max_speed:.1f} km/h")
    typer.echo(f"  Stop percentage: {rep.stop_pct:.1f}%")
    typer.echo(f"  Duration:        {rep.duration:.0f} s")

    # ── Output folder ─────────────────────────────────────────────────────────
    out_dir = data_dir / "analyses" / f"dcca-{run_dt.strftime('%Y%m%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── similarity_scores.csv ─────────────────────────────────────────────────
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

    # ── report.md ─────────────────────────────────────────────────────────────
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

    typer.secho(f"\nOutput written to {out_dir}", fg=typer.colors.CYAN)
