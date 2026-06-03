from pathlib import Path

import typer

from drive_cycle_calculator.schema import UserMetadata, generate_yaml_template

app = typer.Typer(help="Write a metadata-<project_dir>.yaml template into the raw/ subfolder.")

_INGEST_SETTINGS_BLOCK = """\
# --- Ingest settings ---
# CSV field delimiter. Leave as null for auto-detection.
sep: ","

# CSV decimal separator. Leave as null for auto-detection.
decimal: "."
"""


@app.callback(invoke_without_command=True)
def config_init(
    project_dir: Path = typer.Argument(
        ...,
        help="Project directory containing a raw/ subfolder with OBD export files.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite an existing metadata yaml.",
    ),
) -> None:
    project_dir = Path(project_dir).resolve()
    raw_dir = project_dir / "raw"

    if not raw_dir.is_dir():
        typer.secho(
            f"No raw/ subfolder found under {project_dir}. "
            "Create raw/ and place your OBD export files there first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    out_path = raw_dir / f"metadata-{project_dir.name}.yaml"

    if out_path.exists() and not force:
        typer.secho(
            f"  {out_path.name} already exists. Use --force to overwrite.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    content = generate_yaml_template(UserMetadata) + "\n" + _INGEST_SETTINGS_BLOCK
    out_path.write_text(content, encoding="utf-8")
    typer.secho(f"  Written: {out_path}", fg=typer.colors.GREEN)
