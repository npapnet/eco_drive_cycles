# obd_file.py
# -----------
# OBDFile — wraps a single raw OBD xlsx/CSV/Parquet file.
# Responsible for: archive ingestion, type coercion, quality reporting, and
# producing a Trip via ProcessingConfig.

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import TYPE_CHECKING, Union

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from drive_cycle_calculator._schema import CURATED_COLS
from drive_cycle_calculator.gps_time_parser import GpsTimeParser
import logging

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from drive_cycle_calculator.processing_config import ProcessingConfig
    from drive_cycle_calculator.trip import Trip

# Parquet format version written to PyArrow schema metadata.
# v1 = old processed format (smooth_speed_kmh column present).
# v2 = new archive format (all raw columns, no derived columns).
_FORMAT_VERSION = "2"
_FORMAT_VERSION_KEY = b"format_version"


class OBDFile:
    """A raw OBD recording file, as exported by the Torque app.

    Holds the complete unprocessed DataFrame (all columns, dash→NaN coercion).
    Processing is done lazily via ``to_trip(config)``.

    Construction
    ------------
    Use the class-method constructors:
    - ``OBDFile.from_xlsx(path)``
    - ``OBDFile.from_csv(path, sep=None, decimal=None)``
    - ``OBDFile.from_parquet(path)``

    Attributes
    ----------
    name : str
        Inferred from the filename stem (e.g. "2019-09-22_Morning").
    """

    def __init__(self, df: pd.DataFrame, name: str) -> None:
        self._df = _parse_timestamps(_strip_column_names(df))
        self.name = name

        # preprocessing quality checks
        if "Fuel flow rate/hour(l/hr)" not in self._df.columns:
            logger.warning(
                "'Fuel flow rate/hour(l/hr)' column is missing from %s",
                name,
            )
            if "Fuel Rate (direct from ECU)(L/m)" in self._df.columns:
                self._df["Fuel flow rate/hour(l/hr)"] = (
                    self._df["Fuel Rate (direct from ECU)(L/m)"] * 60
                )
                logger.info(
                    "'Fuel flow rate/hour(l/hr)' column created from 'Fuel Rate (direct from ECU)(L/m)' in %s.",
                    name,
                )
            if "Fuel flow rate/hour(gal/hr)" in self._df.columns:
                self._df["Fuel flow rate/hour(l/hr)"] = (
                    self._df["Fuel flow rate/hour(gal/hr)"] * 3.78541
                )
                logger.info(
                    "'Fuel flow rate/hour(l/hr)' column created from 'Fuel flow rate/hour(gal/hr)' in %s.",
                    name,
                )

        self._validate_columns(strict=True)

        # call function to create metadata
        self._spatial_metadata = self._trip_metadata()

    def _validate_columns(self, strict: bool = True):

        # # Returns True if all columns exist, False otherwise
        # assert set(CURATED_COLS).issubset(self._df.columns)

        missing_cols = set(CURATED_COLS) - set(self._df.columns)

        if missing_cols:
            error_msg = f"DataFrame is missing required columns: {missing_cols}"

            if strict:
                # Halts execution immediately
                raise ValueError(error_msg)
            else:
                # Alerts the user but allows the object to be created
                logger.warning("%s. Some features may be degraded.", error_msg)

    def _trip_metadata(self) -> dict:
        """Extract metadata from the raw DataFrame for use in Trip construction."""
        longmean, longstd = self._df["Longitude"].mean(), self._df["Longitude"].std()
        latmean, latstd = self._df["Latitude"].mean(), self._df["Latitude"].std()
        alt_mean, alt_std = self._df["Altitude"].mean(), self._df["Altitude"].std()
        return {
            "lon_mean": longmean,
            "lon_std": longstd,
            "lat_mean": latmean,
            "lat_std": latstd,
            "alt_mean": alt_mean,
            "alt_std": alt_std,
        }

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_xlsx(cls, path: str | Path) -> "OBDFile":
        """Load a raw OBD xlsx file produced by the Torque app.

        All columns are preserved. Dash placeholders (Torque sensor-off marker)
        are coerced to NaN for numeric columns.

        Parameters
        ----------
        path : str | Path
            Path to the xlsx file.

        Raises
        ------
        FileNotFoundError
            If the path does not exist or is not a file.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_excel(path)
        df = _coerce_numeric_columns(df)
        name = path.stem
        return cls(df, name)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        sep: str | None = None,
        decimal: str | None = None,
    ) -> "OBDFile":
        """Load a raw OBD CSV file produced by the Torque app.

        Separator is auto-detected via ``csv.Sniffer`` on the first 20 lines.
        Decimal separator is inferred by scanning the first non-null numeric cell
        for a comma (e.g. European locale exports).

        Parameters
        ----------
        path : str | Path
            Path to the CSV file.
        sep : str, optional
            Override the auto-detected field separator.
        decimal : str, optional
            Override the inferred decimal separator ('.' or ',').

        Raises
        ------
        FileNotFoundError
            If the path does not exist or is not a file.
        ValueError
            If the separator cannot be resolved unambiguously. The message lists
            detected candidates and suggests passing ``sep=`` explicitly.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        if sep is None:
            sep = _sniff_separator(path)

        if decimal is None:
            decimal = _infer_decimal(path, sep)

        df = pd.read_csv(path, sep=sep, decimal=decimal)
        df = _coerce_numeric_columns(df)
        return cls(df, path.stem)

    @classmethod
    def from_parquet(cls, path: str | Path) -> "OBDFile":
        """Load an archive Parquet file (v2 format).

        Raises
        ------
        FileNotFoundError
            If the path does not exist or is not a file.
        ValueError
            If the file appears to be in the old v1 processed format
            (i.e. it contains a ``smooth_speed_kmh`` column, which is only
            present in processed DataFrames, not raw archives).
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_parquet(path)
        if "smooth_speed_kmh" in df.columns:
            raise ValueError(
                f"{path.name} appears to be in the old processed format (v1). "
                "Re-ingest from raw xlsx with OBDFile.from_xlsx() and archive "
                "with OBDFile.to_parquet() to create a v2 archive."
            )
        return cls(df, path.stem)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        **kwargs,
    ) -> "OBDFile":
        """Load a raw OBD file (.xlsx or .csv) by inspecting its extension.

        For .csv files, the `sep` and `decimal` kwargs are passed through to
        allow explicit parsing configuration. Otherwise, automatic sniffing
        is used.

        Raises
        ------
        ValueError
            If the file extension is unsupported.
        """
        path = Path(path)
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            return cls.from_xlsx(path)
        elif ext == ".csv":
            return cls.from_csv(path, **kwargs)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_parquet(
        self,
        path: str | Path,
        use_dictionary: Union[bool, list[str]] = False,
    ) -> None:
        """Write the full archive to a Parquet file (v2 format).

        Timestamp columns (``GPS Time``, ``Device Time``) are stored as
        ``datetime64[ns, UTC]`` — they are converted once at construction time,
        so no additional transformation is needed here.

        Parameters
        ----------
        path : str | Path
            Destination path. Parent directory must exist.
        use_dictionary : bool or list[str], optional
            Controls PyArrow dictionary (RLE) encoding:

            - ``False`` (default) — no dictionary encoding for any column.
              Use this when column cardinality is high (most numeric columns).
            - ``True`` — dictionary-encode every column *except* the timestamp
              columns (``GPS Time``, ``Device Time``), which are already stored
              efficiently as ``datetime64``.
            - ``list[str]`` — explicit list of column names to dictionary-encode.
        """
        path = Path(path)
        table = pa.Table.from_pandas(self._df)
        existing_meta = table.schema.metadata or {}
        new_meta = {**existing_meta, _FORMAT_VERSION_KEY: _FORMAT_VERSION.encode()}
        table = table.replace_schema_metadata(new_meta)

        if use_dictionary is True:
            # Dict-encode everything except the already-typed timestamp columns
            resolved_dict: bool | list[str] = [
                col for col in table.column_names if col not in _TIMESTAMP_COLS
            ]
        else:
            resolved_dict = use_dictionary  # False or explicit list pass-through

        pq.write_table(
            table,
            path,
            compression="zstd",
            use_dictionary=resolved_dict,
            write_statistics=True,
            version="2.6",
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def parquet_name(self) -> str:
        """Return a canonical Parquet stem derived from the trip's GPS start time and duration.

        Format: ``t<YYYYMMDD-hhmmss>-<duration_s>``

        - ``YYYYMMDD-hhmmss`` is the UTC timestamp of the first valid GPS row.
        - ``duration_s`` is the total elapsed seconds (integer) from first to last
          valid GPS timestamp.

        Falls back to ``self.name`` (the raw filename stem) if the GPS Time column
        is absent or fully unparseable.
        """
        if "GPS Time" not in self._df.columns:
            return self.name

        # Avoid parsing the full column — only the first and last non-null raw
        # values are needed.  dropna() on a string Series is a cheap null-mask
        # scan; the expensive dateutil parse only runs twice.
        raw_valid = self._df["GPS Time"].dropna()
        if raw_valid.empty:
            return self.name

        parser = GpsTimeParser()
        start_dt = parser.to_datetime(raw_valid.iloc[[0]]).dropna()
        if start_dt.empty:
            return self.name

        start_ts: pd.Timestamp = start_dt.iloc[0]
        end_dt = parser.to_datetime(raw_valid.iloc[[-1]]).dropna()
        duration_s = int((end_dt.iloc[0] - start_ts).total_seconds()) if not end_dt.empty else 0
        stamp = start_ts.strftime("%Y%m%d-%H%M%S")
        return f"t{stamp}-{duration_s}"

    @property
    def curated_df(self) -> pd.DataFrame:
        """Return the CURATED_COLS subset of the raw DataFrame.

        Columns absent from the raw file are silently omitted — no error.
        Call ``quality_report()`` to check for missing columns before processing.
        """
        present = [c for c in CURATED_COLS if c in self._df.columns]
        return self._df[present].copy()

    @property
    def full_df(self) -> pd.DataFrame:
        """Return the full raw DataFrame."""
        return self._df.copy()

    # ── Quality reporting ─────────────────────────────────────────────────────

    def quality_report(self) -> dict:
        """Return a data-quality summary for this file.

        Returns
        -------
        dict with keys:
        - ``row_count`` : int — number of rows
        - ``missing_pct`` : dict[str, float] — fraction of NaN per column
        - ``dash_count`` : dict[str, int] — count of literal "-" per column
        - ``gps_gap_count`` : int — GPS Time gaps > 5 s
        - ``speed_outlier_count`` : int — rows with Speed (OBD)(km/h) > 250
        - ``speed_min_kmh`` : float — minimum speed (NaN if column absent)
        - ``speed_max_kmh`` : float — maximum speed (NaN if column absent)
        - ``missing_curated_cols`` : list[str] — CURATED_COLS absent from file
        """
        df = self._df
        row_count = len(df)

        missing_pct = {
            col: float(df[col].isna().mean()) if col in df.columns else float("nan")
            for col in df.columns
        }

        dash_count: dict[str, int] = {}
        for col in df.columns:
            if df[col].dtype == object:
                dash_count[col] = int((df[col] == "-").sum())
            else:
                dash_count[col] = 0

        # GPS gap count: gaps > 5 s between consecutive valid timestamps
        gps_gap_count = 0
        if "GPS Time" in df.columns:
            parser = GpsTimeParser()
            elapsed = parser.to_duration_seconds(df["GPS Time"])
            valid = elapsed.dropna()
            if len(valid) > 1:
                gaps = valid.diff().dropna()
                gps_gap_count = int((gaps > 5).sum())

        # Speed outliers
        speed_col = "Speed (OBD)(km/h)"
        if speed_col in df.columns:
            speed = pd.to_numeric(df[speed_col], errors="coerce")
            speed_outlier_count = int((speed > 250).sum())
            speed_min_kmh = float(speed.min()) if speed.notna().any() else float("nan")
            speed_max_kmh = float(speed.max()) if speed.notna().any() else float("nan")
        else:
            speed_outlier_count = 0
            speed_min_kmh = float("nan")
            speed_max_kmh = float("nan")

        missing_curated_cols = [c for c in CURATED_COLS if c not in df.columns]

        return dict(
            row_count=row_count,
            missing_pct=missing_pct,
            dash_count=dash_count,
            gps_gap_count=gps_gap_count,
            speed_outlier_count=speed_outlier_count,
            speed_min_kmh=speed_min_kmh,
            speed_max_kmh=speed_max_kmh,
            missing_curated_cols=missing_curated_cols,
        )

    # ── Trip construction ─────────────────────────────────────────────────────

    def to_trip(self, config: "ProcessingConfig | None" = None) -> "Trip":
        """Process the curated data and return a Trip.

        Parameters
        ----------
        config : ProcessingConfig, optional
            Processing parameters. Defaults to ``DEFAULT_CONFIG`` (window=4).

        Raises
        ------
        ValueError
            If any CURATED_COL is missing from the raw DataFrame.
        """
        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG
        from drive_cycle_calculator.trip import Trip

        if config is None:
            config = DEFAULT_CONFIG

        missing = [c for c in CURATED_COLS if c not in self._df.columns]
        if missing:
            raise ValueError(
                f"Missing required column(s) for analysis: {missing}. "
                "Check quality_report()['missing_curated_cols'] for details."
            )

        processed_df = config.apply(self.curated_df)
        return Trip(df=processed_df, name=self.name, stop_threshold_kmh=config.stop_threshold_kmh)


# ── Module-level helpers ──────────────────────────────────────────────────────

# Columns excluded from numeric coercion (they hold timestamp strings on load,
# then converted to datetime64 at construction time via _parse_timestamps).
_TIMESTAMP_COLS = frozenset({"GPS Time", "Device Time"})


def _strip_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return *df* with all column names stripped of leading/trailing whitespace.

    Torque exports sometimes emit column headers with surrounding spaces or tabs
    (e.g. ``" Device Time\t"``). Normalising them on construction means the rest
    of the code can use clean names (``"Device Time"``) unconditionally.

    The operation is performed on the DataFrame index in-place (no data copy).
    """
    df.columns = df.columns.str.strip()
    return df


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with timestamp columns converted to ``datetime64[ns, UTC]``.

    Only columns listed in ``_TIMESTAMP_COLS`` that are actually present *and*
    not already typed as datetime are converted — already-typed columns (e.g.
    loaded from a v2 Parquet) are left untouched. Missing columns are silently
    skipped.

    Called once at construction time (``__init__``) so that ``_df`` is always in
    a consistent state: clean column names, numeric coercion applied, and
    timestamps as timezone-aware datetime objects.
    """
    parser = GpsTimeParser()
    df = df.copy()
    for col in _TIMESTAMP_COLS:
        if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = parser.to_datetime(df[col])
    return df


def _coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce object-dtype columns that contain Torque dash-placeholders to float64.

    Torque exports sensor-off cells as literal "-". Without this coercion,
    mixed str/float columns produce dtype=object and PyArrow raises ArrowTypeError
    on to_parquet().

    Timestamp columns are skipped — they contain date strings and must remain
    as-is for GpsTimeParser to parse them correctly.
    """
    for col in df.columns:
        if col in _TIMESTAMP_COLS:
            continue
        if df[col].dtype == object:
            coerced = pd.to_numeric(df[col], errors="coerce")
            # Only replace if at least one value parsed successfully — otherwise
            # keep as-is (could be a genuine non-numeric string column).
            if coerced.notna().any():
                df[col] = coerced
    return df


def _sniff_separator(path: Path) -> str:
    """Auto-detect the field separator using csv.Sniffer on the first 20 lines."""
    sample_lines: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for _ in range(20):
            line = f.readline()
            if not line:
                break
            sample_lines.append(line)
    sample = "".join(sample_lines)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        # Sniffer failed — common with comma-decimal files where "," appears as
        # both separator and decimal.  Fall back to ";" which is typical for
        # European locale Torque exports.
        candidates = []
        for delim in [",", ";", "\t"]:
            count = sample.count(delim)
            if count > 0:
                candidates.append((count, delim))
        candidates.sort(reverse=True)
        if candidates:
            return candidates[0][1]
        raise ValueError(
            f"Cannot detect separator in {path.name}. Pass sep= explicitly (e.g. sep=',', sep=';')."
        )


def _infer_decimal(path: Path, sep: str) -> str:
    """Infer the decimal separator by scanning the first non-null numeric-looking cell.

    If a cell contains a comma where a float decimal point is expected (e.g. "3,14"),
    returns ','. Otherwise returns '.'.
    """
    try:
        # Read a small preview without decimal conversion
        preview = pd.read_csv(path, sep=sep, nrows=20, dtype=str)
    except Exception:
        return "."

    _decimal_comma = re.compile(r"^\s*-?\d+,\d+\s*$")

    for col in preview.columns:
        for val in preview[col].dropna():
            val_str = str(val).strip()
            if _decimal_comma.match(val_str):
                return ","
    return "."
