from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import typer

from drive_cycle_calculator.similarity import pct_deviation

app = typer.Typer(help="Compute similarity scores from extracted trip metrics.")

# Ordered metric columns in metrics.csv → 7 metric keys used for fleet matrix
_METRIC_COLS = [
    "duration_s",
    "avg_velocity_kmh",
    "mean_speed_ns_kmh",
    "stop_count",
    "idle_time_pct",
    "avg_acceleration_ms2",
    "avg_deceleration_ms2",
]
_METRIC_KEYS = ["duration", "mean_speed", "mean_ns", "stops", "stop_pct", "mean_acc", "mean_dec"]


@app.callback(invoke_without_command=True)
def analyze(
    data_dir: Path = typer.Argument(
        ...,
        help="Project directory containing an analyses/ folder with a metrics CSV.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
):
    analyses_dir = data_dir / "analyses"

    # Find most recent metrics.csv (directories are named by timestamp, sorted lexicographically)
    csv_files = sorted(analyses_dir.glob("*/metrics.csv"), key=lambda p: p.parent.name)
    if not csv_files:
        typer.secho(
            f"No metrics.csv found under {analyses_dir}. Run 'dcc extract' first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    metrics_csv = csv_files[-1]
    typer.echo(f"Loading metrics from {metrics_csv}...")

    df = pd.read_csv(metrics_csv)

    missing = [c for c in _METRIC_COLS if c not in df.columns]
    if missing:
        typer.secho(
            f"Metrics CSV missing required columns: {missing}. "
            "Re-run 'dcc extract' with the current version.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    typer.echo(f"  {len(df)} trips in metrics CSV.")

    if len(df) == 0:
        typer.secho("No trips in metrics CSV.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    fleet = df[_METRIC_COLS].to_numpy(dtype=float)

    scores: dict[str, float] = {}
    for _, row in df.iterrows():
        trip_vec = np.array([row[c] for c in _METRIC_COLS], dtype=float)
        scores[row["trip_id"]] = pct_deviation(fleet, trip_vec)

    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])

    typer.echo("\nSimilarity scores:")
    for name, score in sorted_scores:
        typer.echo(f"  {name}: {score:.1f}")

    best_id = sorted_scores[0][0]
    rep = df[df["trip_id"] == best_id].iloc[0]

    typer.echo(f"\nRepresentative trip: {best_id}")
    typer.echo(f"  Mean speed:      {rep['avg_velocity_kmh']:.1f} km/h")
    typer.echo(f"  Max speed:       {rep['max_velocity_kmh']:.1f} km/h")
    typer.echo(f"  Stop percentage: {rep['idle_time_pct']:.1f}%")
    typer.echo(f"  Duration:        {rep['duration_s']:.0f} s")

    # ── Output folder ─────────────────────────────────────────────────────────
    run_dt = datetime.now()
    out_dir = data_dir / "analyses" / f"dcca-{run_dt.strftime('%Y%m%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── similarity_scores.csv ─────────────────────────────────────────────────
    csv_path = out_dir / "similarity_scores.csv"
    with csv_path.open("w", encoding="utf-8") as fh:
        fh.write("trip_id,score,duration,mean_speed,mean_ns,stops,stop_pct,mean_acc,mean_dec\n")
        for name, score in sorted_scores:
            r = df[df["trip_id"] == name].iloc[0]
            fh.write(
                f"{name},{score:.4f},{r['duration_s']:.0f},{r['avg_velocity_kmh']:.3f},"
                f"{r['mean_speed_ns_kmh']:.3f},{int(r['stop_count'])},"
                f"{r['idle_time_pct']:.3f},{r['avg_acceleration_ms2']:.4f},"
                f"{r['avg_deceleration_ms2']:.4f}\n"
            )

    # ── report.md ─────────────────────────────────────────────────────────────
    md_path = out_dir / "report.md"
    with md_path.open("w", encoding="utf-8") as fh:
        fh.write("# Drive Cycle Analysis Report\n\n")
        fh.write("| | |\n|---|---|\n")
        fh.write(f"| Run | {run_dt.strftime('%Y-%m-%d %H:%M')} |\n")
        fh.write(f"| Metrics CSV | `{metrics_csv}` |\n")
        fh.write(f"| Trips | {len(df)} |\n\n")

        fh.write("## Similarity Scores\n\n")
        fh.write("| Trip | Score |\n|---|---|\n")
        for name, score in sorted_scores:
            marker = " ★" if name == best_id else ""
            fh.write(f"| `{name}`{marker} | {score:.1f} |\n")

        fh.write("\n## Representative Trip\n\n")
        fh.write(f"**`{best_id}`**\n\n")
        fh.write("| Metric | Value |\n|---|---|\n")
        fh.write(f"| Duration | {rep['duration_s']:.0f} s |\n")
        fh.write(f"| Mean speed | {rep['avg_velocity_kmh']:.1f} km/h |\n")
        fh.write(f"| Mean speed (no stops) | {rep['mean_speed_ns_kmh']:.1f} km/h |\n")
        fh.write(f"| Max speed | {rep['max_velocity_kmh']:.1f} km/h |\n")
        fh.write(f"| Stop percentage | {rep['idle_time_pct']:.1f}% |\n")
        fh.write(f"| Stop count | {int(rep['stop_count'])} |\n")
        fh.write(f"| Mean acceleration | {rep['avg_acceleration_ms2']:.3f} m/s² |\n")
        fh.write(f"| Mean deceleration | {rep['avg_deceleration_ms2']:.3f} m/s² |\n")

    typer.secho(f"\nOutput written to {out_dir}", fg=typer.colors.CYAN)
