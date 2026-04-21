from pathlib import Path

import typer

from drive_cycle_calculator.schema import UserMetadata, generate_yaml_template

app = typer.Typer(help="Write a metadata-<folder>.yaml template for a raw OBD folder.")

_INGEST_SETTINGS_BLOCK = """\
# --- Ingest settings ---
# CSV field delimiter. Leave as null for auto-detection.
sep: ","

# CSV decimal separator. Leave as null for auto-detection.
decimal: "."
"""


@app.callback(invoke_without_command=True)
def config_init(
    folder: Path = typer.Argument(
        ...,
        help="Folder containing raw OBD files (.xlsx / .csv).",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite an existing metadata-<folder>.yaml.",
    ),
) -> None:
    folder = Path(folder)
    out_path = folder / f"metadata-{folder.absolute().name}.yaml"

    if out_path.exists() and not force:
        typer.secho(
            f"  {out_path.name} already exists. Use --force to overwrite.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    content = generate_yaml_template(UserMetadata) + "\n" + _INGEST_SETTINGS_BLOCK
    out_path.write_text(content, encoding="utf-8")
    typer.secho(f"  Written: {out_path}", fg=typer.colors.GREEN)
