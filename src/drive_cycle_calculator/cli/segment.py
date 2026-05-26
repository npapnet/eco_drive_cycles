from pathlib import Path

import typer

app = typer.Typer(help="Segment archive Parquets into microtrips.")


@app.callback(invoke_without_command=True)
def segment(
    project_dir: Path = typer.Argument(
        ...,
        help="Project directory containing a trips/ subfolder of archive Parquets.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    stop_threshold: float = typer.Option(
        2.0,
        "--stop-threshold",
        help="Speed below which a sample is considered stopped (km/h).",
    ),
    stop_min_duration: float = typer.Option(
        1.0,
        "--stop-min-duration",
        help="Minimum confirmed stop duration in seconds.",
    ),
    microtrip_min_duration: float = typer.Option(
        15.0,
        "--microtrip-min-duration",
        help="Minimum microtrip duration (motion + stop) in seconds.",
    ),
    microtrip_min_distance: float = typer.Option(
        50.0,
        "--microtrip-min-distance",
        help="Minimum motion-phase distance in metres.",
    ),
) -> None:
    from drive_cycle_calculator.cli._layout import _project_layout
    from drive_cycle_calculator.schema import SegmentationConfig
    from drive_cycle_calculator.segmentation import MicrotripSegmenter
    from drive_cycle_calculator.trip_collection import TripCollection

    layout = _project_layout(project_dir)

    if not any(layout.trips.glob("*.parquet")):
        typer.secho(
            f"No parquets found in {layout.trips}. Run 'dcc ingest' first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    config = SegmentationConfig(
        stop_threshold_kmh=stop_threshold,
        stop_min_duration_s=stop_min_duration,
        microtrip_min_duration_s=microtrip_min_duration,
        microtrip_min_distance_m=microtrip_min_distance,
    )

    typer.echo(f"Loading trips from {layout.trips}...")
    tc = TripCollection.from_archive_parquets(layout.trips)
    typer.echo(f"  {len(tc)} trip(s) loaded.")

    if len(tc) == 0:
        typer.secho("No trips found — nothing to segment.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    segmenter = MicrotripSegmenter(config)
    result = segmenter.segment_collection(tc)
    total = sum(len(v) for v in result.values())
    typer.echo(f"Segmentation complete: {total} microtrip(s) across {len(tc)} trip(s).")

    typer.echo(f"Saving microtrips to {layout.microtrips}...")
    summary = segmenter.export_collection(result, layout.microtrips)

    summary_path = layout.reports / "microtrip_summary.csv"
    summary.to_csv(summary_path, index=False)

    typer.secho(f"  {len(summary)} microtrip(s) saved.", fg=typer.colors.GREEN)
    typer.secho(f"  Summary written to {summary_path}", fg=typer.colors.GREEN)
    typer.secho(
        "Done. Use MicrotripCollection.from_parquets() for synthesis.",
        fg=typer.colors.GREEN,
    )
