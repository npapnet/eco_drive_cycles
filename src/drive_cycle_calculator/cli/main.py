import typer

from .ingest import app as ingest_app
from .analyze import app as analyze_app
from .gui import app as gui_app

app = typer.Typer(
    help="Drive Cycle Calculator (DCC) CLI.",
    no_args_is_help=True,
)

app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")
app.add_typer(gui_app, name="gui")

if __name__ == "__main__":
    app()
