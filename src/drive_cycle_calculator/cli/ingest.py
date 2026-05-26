from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.schema import UserMetadata

app = typer.Typer(help="Ingest raw OBD files into v2 archive Parquets (no DuckDB).")


@app.callback(invoke_without_command=True)
def ingest(
    first_arg: Path = typer.Argument(
        ...,
        help=(
            "Project directory (single-arg mode: reads raw/, writes trips/) "
            "or raw OBD directory (two-arg mode)."
        ),
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    out_dir: Optional[Path] = typer.Argument(
        None,
        help="Output directory (two-arg backward-compat mode only).",
        file_okay=False,
    ),
    format: str = typer.Option(
        "auto",
        "--format",
        "-f",
        help="File format to scan for: auto, xlsx, or csv.",
    ),
    sep: Optional[str] = typer.Option(
        None,
        help="CSV field delimiter (e.g. ',' or ';'). Overrides metadata yaml value.",
    ),
    decimal: Optional[str] = typer.Option(
        None,
        help="CSV decimal separator (e.g. '.' or ','). Overrides metadata yaml value.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing archive Parquets. Default: skip files that already exist.",
    ),
    max_gap_s: float = typer.Option(
        5.0,
        "--max-gap-s",
        help="Maximum allowable time gap in seconds. Gaps above this threshold trigger a warning.",
    ),
    strict_gaps: bool = typer.Option(
        False,
        "--strict-gaps",
        help="Skip files with any time gap exceeding --max-gap-s (instead of just warning).",
    ),
    no_resample: bool = typer.Option(
        False,
        "--no-resample",
        help="Disable 1 Hz resampling. Archive will contain raw timestamps.",
    ),
) -> None:
    if out_dir is None:
        # Single-arg project-dir mode
        from drive_cycle_calculator.cli._layout import _project_layout

        project_dir = first_arg
        raw_subdir = project_dir / "raw"
        if not raw_subdir.is_dir():
            typer.secho(
                f"No raw/ subfolder found under {project_dir}. "
                "Create raw/ and place your OBD export files there first.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)
        layout = _project_layout(project_dir)
        raw_dir = layout.raw
        archive_dir = layout.trips
    else:
        # Two-arg backward-compat mode
        raw_dir = first_arg
        archive_dir = out_dir / "trips"
        archive_dir.mkdir(parents=True, exist_ok=True)

    # ── Discover metadata-<folder>.yaml ──────────────────────────────────────
    yaml_files = sorted(raw_dir.glob("metadata-*.yaml"))
    user_metadata = UserMetadata()
    yaml_sep: Optional[str] = None
    yaml_decimal: Optional[str] = None

    if len(yaml_files) == 1:
        raw_yaml = yaml.safe_load(yaml_files[0].read_text(encoding="utf-8")) or {}
        yaml_sep = raw_yaml.pop("sep", None)
        yaml_decimal = raw_yaml.pop("decimal", None)
        user_fields = {k: v for k, v in raw_yaml.items() if v is not None}
        try:
            user_metadata = UserMetadata.model_validate(user_fields)
        except ValidationError as exc:
            typer.secho(
                f"Invalid metadata in {yaml_files[0].name}:\n{exc}",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)
        typer.secho(f"  Loaded metadata from {yaml_files[0].name}", fg=typer.colors.CYAN)
    elif len(yaml_files) > 1:
        names = ", ".join(f.name for f in yaml_files)
        typer.secho(
            f"Multiple metadata files found — remove all but one:\n  {names}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    # CLI flag > yaml value > None (OBDFile auto-detects when None)
    resolved_sep = sep if sep is not None else yaml_sep
    resolved_decimal = decimal if decimal is not None else yaml_decimal

    # ── File discovery ────────────────────────────────────────────────────────
    typer.echo(f"Scanning for {format!r} files in {raw_dir}...")
    if format == "auto":
        files = (
            list(raw_dir.glob("*.xlsx"))
            + list(raw_dir.glob("*.xls"))
            + list(raw_dir.glob("*.csv"))
        )
    elif format in ("xlsx", "xls"):
        files = list(raw_dir.glob("*.xlsx")) + list(raw_dir.glob("*.xls"))
    elif format == "csv":
        files = list(raw_dir.glob("*.csv"))
    else:
        typer.secho(
            f"Unknown format: {format!r}. Use auto, xlsx, or csv.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if not files:
        typer.echo(f"No {format!r} files found in {raw_dir} — nothing to ingest.")
        raise typer.Exit()

    resample = not no_resample
    resample_label = "1 Hz resampling" if resample else "raw timestamps (no resample)"
    typer.echo(f"  Found {len(files)} raw file(s). Mode: {resample_label}, max_gap_s={max_gap_s}")

    ok = skipped = collisions = 0
    for f in sorted(files):
        try:
            obd = OBDFile.from_file(f, sep=resolved_sep, decimal=resolved_decimal)
        except Exception as exc:
            typer.secho(f"  ERROR  {f.name}: {exc}", fg=typer.colors.RED)
            skipped += 1
            continue

        dest = archive_dir / f"{obd.parquet_name}.parquet"
        if dest.exists():
            if not force:
                typer.secho(
                    f"  EXISTS {f.name} → {dest.name}  (skipped — use --force to overwrite)",
                    fg=typer.colors.YELLOW,
                )
                collisions += 1
                continue
            typer.secho(f"  OVERWRITE {dest.name}", fg=typer.colors.YELLOW)

        try:
            obd.to_parquet(
                dest,
                user_metadata=user_metadata,
                resample=resample,
                max_gap_s=max_gap_s,
                strict_gaps=strict_gaps,
            )
        except ValueError as exc:
            typer.secho(f"  SKIPPED {f.name}: {exc}", fg=typer.colors.RED)
            skipped += 1
            continue

        ok += 1
        typer.secho(f"  OK     {f.name} → {dest.name}", fg=typer.colors.GREEN)

    typer.echo(f"\n  Archived {ok} trip(s), {collisions} skipped (already exist), {skipped} failed.")
    if collisions:
        typer.secho("  Tip: re-run with --force to overwrite existing files.", fg=typer.colors.YELLOW)
    if ok:
        typer.secho("Done. Run 'dcc extract' to compute metrics.", fg=typer.colors.GREEN)
