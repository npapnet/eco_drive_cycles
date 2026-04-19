# Obtain the version of the package using importlib.metadata
from importlib.metadata import version, PackageNotFoundError

try:
    # Note: Use the distribution name exactly as it appears in pyproject.toml
    __version__ = version("drive-cycle-calculator")
except PackageNotFoundError:
    # Fallback for when the package is run without being installed
    __version__ = "unknown"


# Import the main classes from the submodules
from .obd_file import OBDFile
from .trip import Trip
from .trip_collection import TripCollection

__all__ = ["Trip", "TripCollection", "OBDFile"]
