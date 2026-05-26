from pathlib import Path
from typing import NamedTuple


class ProjectLayout(NamedTuple):
    project_dir: Path
    raw: Path
    trips: Path
    microtrips: Path
    reports: Path
    analyses: Path


def _project_layout(project_dir: Path) -> ProjectLayout:
    """Return canonical subdirectory paths for a project directory, creating them if absent.

    raw/ is not created — it is user-supplied.
    """
    raw = project_dir / "raw"
    trips = project_dir / "trips"
    microtrips = project_dir / "microtrips"
    reports = project_dir / "reports"
    analyses = project_dir / "analyses"
    for d in (trips, microtrips, reports, analyses):
        d.mkdir(parents=True, exist_ok=True)
    return ProjectLayout(project_dir, raw, trips, microtrips, reports, analyses)
