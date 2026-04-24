# obd_file.py
# -----------
# OBDFile — wraps a single raw OBD xlsx/CSV/Parquet file.
# Responsible for: archive ingestion, type coercion, quality reporting, and
# producing a Trip via ProcessingConfig.

from __future__ import annotations

import csv
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Union

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from drive_cycle_calculator.gps_time_parser import GpsTimeParser
from drive_cycle_calculator.schema import CURATED_COLS

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from drive_cycle_calculator.processing_config import ProcessingConfig
    from drive_cycle_calculator.schema import UserMetadata
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
    - ``OBDFile.from_xlsx(path, strict=True)``
    - ``OBDFile.from_csv(path, sep=None, decimal=None, strict=True)``
    - ``OBDFile.from_parquet(path, strict=True)``
    - ``OBDFile.from_file(path, strict=True, **kwargs)``

    Parameters
    ----------
    strict : bool
        If True (default), missing curated columns raise ``ValueError``.
        If False, missing columns are injected as NaN so ``curated_df``
        always has the expected shape.  Permissive mode is for library/debug
        use only — the CLI always uses strict mode.

    Attributes
    ----------
    name : str
        Inferred from the filename stem (e.g. "2019-09-22_Morning").
    """

    def __init__(self, df: pd.DataFrame, name: str, strict: bool = True) -> None:
        # Torque exports sometimes emit column headers with surrounding spaces or tabs.
        # Normalising on construction means the rest of the code can use clean names.
        df.columns = df.columns.str.strip()

        self._df = _parse_timestamps(df)
        self.name = name
        self._strict = strict

        # Fuel unit fallbacks
        if "Fuel flow rate/hour(l/hr)" not in self._df.columns:
            logger.warning("'Fuel flow rate/hour(l/hr)' column is missing from %s", name)
            if "Fuel Rate (direct from ECU)(L/m)" in self._df.columns:
                self._df["Fuel flow rate/hour(l/hr)"] = (
                    self._df["Fuel Rate (direct from ECU)(L/m)"] * 60
                )
                logger.info(
                    "'Fuel flow rate/hour(l/hr)' created from 'Fuel Rate (direct from ECU)(L/m)' in %s.",
                    name,
                )
            elif "Fuel flow rate/hour(gal/hr)" in self._df.columns:
                self._df["Fuel flow rate/hour(l/hr)"] = (
                    self._df["Fuel flow rate/hour(gal/hr)"] * 3.78541
                )
                logger.info(
                    "'Fuel flow rate/hour(l/hr)' created from 'Fuel flow rate/hour(gal/hr)' in %s.",
                    name,
                )

        self._validate_columns()

    def _validate_columns(self) -> None:
        missing_cols = set(CURATED_COLS) - set(self._df.columns)
        if not missing_cols:
            return
        if self._strict:
            raise ValueError(f"DataFrame is missing required columns: {missing_cols}")
        # Permissive: inject NaN columns so curated_df always has the expected shape.
        for col in missing_cols:
            self._df[col] = float("nan")
        logger.warning("Missing curated columns %s in %s — NaN columns injected.", missing_cols, self.name)

    def _compute_parquet_id(self) -> str:
        """6-char hex hash of GPS lat+lon bytes, or name-hash fallback."""
        if "Latitude" in self._df.columns and "Longitude" in self._df.columns:
            lat_bytes = self._df["Latitude"].values.tobytes()
            lon_bytes = self._df["Longitude"].values.tobytes()
            return hashlib.sha256(lat_bytes + lon_bytes).hexdigest()[:6]
        return hashlib.sha256(self.name.encode()).hexdigest()[:6]

    def _compute_gps_stats(self) -> "ComputedTripStats":
        """Compute ComputedTripStats from raw GPS columns."""
        from drive_cycle_calculator.schema import ComputedTripStats

        gps_col = (
            self._df["GPS Time"]
            if "GPS Time" in self._df.columns
            else pd.Series(dtype="datetime64[ns, UTC]")
        )
        valid = gps_col.dropna()
        start_time = valid.iloc[0].to_pydatetime() if not valid.empty else None
        end_time = valid.iloc[-1].to_pydatetime() if not valid.empty else None

        lat_col = self._df["Latitude"] if "Latitude" in self._df.columns else pd.Series(dtype=float)
        lon_col = self._df["Longitude"] if "Longitude" in self._df.columns else pd.Series(dtype=float)

        n_lat = lat_col.dropna().__len__()

        return ComputedTripStats(
            start_time=start_time,
            end_time=end_time,
            gps_lat_mean=float(lat_col.mean()) if n_lat > 0 else 0.0,
            gps_lat_std=float(lat_col.std()) if n_lat > 1 else 0.0,
            gps_lon_mean=float(lon_col.mean()) if n_lat > 0 else 0.0,
            gps_lon_std=float(lon_col.std()) if n_lat > 1 else 0.0,
        )

    def _trip_spatial_metadata(self) -> dict:
        """Extract spatial metadata from the raw DataFrame."""
        longmean, longstd = self._df["Longitude"].mean(), self._df["Longitude"].std()
        latmean, latstd = self._df["Latitude"].mean(), self._df["Latitude"].std()
        alt_mean, alt_std = self._df["Altitude"].mean(), self._df["Altitude"].std()
        return {
            "lon_mean": float(longmean),
            "lon_std": float(longstd),
            "lat_mean": float(latmean),
            "lat_std": float(latstd),
            "alt_mean": float(alt_mean),
            "alt_std": float(alt_std),
        }

    # region ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_xlsx(cls, path: str | Path, strict: bool = True) -> "OBDFile":
        """Load a raw OBD xlsx file produced by the Torque app."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_excel(path)
        df = _coerce_numeric_columns(df)
        return cls(df, path.stem, strict=strict)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        sep: str | None = None,
        decimal: str | None = None,
        strict: bool = True,
    ) -> "OBDFile":
        """Load a raw OBD CSV file produced by the Torque app."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        if sep is None:
            sep = _sniff_separator(path)
        if decimal is None:
            decimal = _infer_decimal(path, sep)

        df = pd.read_csv(path, sep=sep, decimal=decimal)
        df = _coerce_numeric_columns(df)
        return cls(df, path.stem, strict=strict)

    @classmethod
    def from_parquet(cls, path: str | Path, strict: bool = True) -> "OBDFile":
        """Load an archive Parquet file (v2 format)."""
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
        return cls(df, path.stem, strict=strict)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        strict: bool = True,
        **kwargs,
    ) -> "OBDFile":
        """Load a raw OBD file (.xlsx or .csv) by inspecting its extension."""
        path = Path(path)
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            return cls.from_xlsx(path, strict=strict)
        elif ext == ".csv":
            return cls.from_csv(path, strict=strict, **kwargs)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    # end region

    # region Persistence ───────────────────────────────────────────────────────────

    def to_parquet(
        self,
        path: str | Path,
        user_metadata: "UserMetadata | None" = None,
        use_dictionary: Union[bool, list[str]] = False,
    ) -> None:
        """Write the full archive to a Parquet file (v2 format) with embedded metadata.

        Parameters
        ----------
        path : str | Path
            Destination path. Parent directory must exist.
        user_metadata : UserMetadata, optional
            User-supplied metadata to embed. Defaults to empty UserMetadata (all None).
        use_dictionary : bool or list[str], optional
            Controls PyArrow dictionary encoding.
        """
        from drive_cycle_calculator.schema import (
            IngestProvenance,
            ParquetMetadata,
            UserMetadata as _UserMetadata,
        )

        # Lazy import to avoid circular dependency at module level
        try:
            from drive_cycle_calculator import __version__ as _sw_ver
        except ImportError:
            _sw_ver = "unknown"

        path = Path(path)
        table = pa.Table.from_pandas(self._df)
        existing_meta = table.schema.metadata or {}

        # Assemble ParquetMetadata
        pq_meta = ParquetMetadata(
            schema_version="1.0",
            software_version=_sw_ver,
            parquet_id=self._compute_parquet_id(),
            ingest_provenance=IngestProvenance(
                ingest_timestamp=datetime.now(timezone.utc),
                source_filename=self.name,
            ),
            computed_trip_stats=self._compute_gps_stats(),
            user_metadata=user_metadata if user_metadata is not None else _UserMetadata(),
        )

        new_meta = {
            **existing_meta,
            _FORMAT_VERSION_KEY: _FORMAT_VERSION.encode(),
            b"dcc_metadata": pq_meta.model_dump_json().encode(),
        }
        table = table.replace_schema_metadata(new_meta)

        if use_dictionary is True:
            resolved_dict: bool | list[str] = [
                col for col in table.column_names if col not in _TIMESTAMP_COLS
            ]
        else:
            resolved_dict = use_dictionary

        pq.write_table(
            table,
            path,
            compression="zstd",
            use_dictionary=resolved_dict,
            write_statistics=True,
            version="2.6",
        )

    # end region

    # region  ── Properties ────────────────────────────────────────────────────────────

    @property
    def parquet_name(self) -> str:
        """Return a canonical Parquet stem derived from GPS start time, duration, and hash.

        Format: ``t<YYYYMMDD-hhmmss>-<duration_s>-<hash6>``

        - ``YYYYMMDD-hhmmss``: UTC timestamp of the first valid GPS row.
        - ``duration_s``: total elapsed seconds (integer).
        - ``hash6``: first 6 hex chars of sha256(lat_bytes + lon_bytes).

        Falls back to ``self.name`` if GPS Time is absent or fully unparseable.
        """
        if "GPS Time" not in self._df.columns:
            return self.name

        raw_valid = self._df["GPS Time"].dropna()
        if raw_valid.empty:
            return self.name

        parser = GpsTimeParser()
        start_dt = parser.to_datetime(raw_valid.iloc[[0]]).dropna()
        if start_dt.empty:
            return self.name

        start_ts: pd.Timestamp = start_dt.iloc[0]
        end_dt = parser.to_datetime(raw_valid.iloc[[-1]]).dropna()
        duration_s = (
            int((end_dt.iloc[0] - start_ts).total_seconds()) if not end_dt.empty else 0
        )
        stamp = start_ts.strftime("%Y%m%d-%H%M%S")
        hash6 = self._compute_parquet_id()
        return f"t{stamp}-{duration_s}-{hash6}"

    @property
    def curated_df(self) -> pd.DataFrame:
        """Return the CURATED_COLS subset of the raw DataFrame.

        In permissive mode, absent columns were injected as NaN at construction
        so this always returns a DataFrame with all expected columns.
        """
        present = [c for c in CURATED_COLS if c in self._df.columns]
        return self._df[present].copy()

    @property
    def full_df(self) -> pd.DataFrame:
        """Return the full raw DataFrame."""
        return self._df.copy()

    # end region

    # region  ── Auxilliary functions ─────────────────────────────────────────────────────

    def get_metrics(self, config: "ProcessingConfig | None" = None) -> dict:
        """Get the full metrics dict for this file."""
        from drive_cycle_calculator.processing_config import DEFAULT_CONFIG

        if config is None:
            config = DEFAULT_CONFIG

        tr = self.to_trip(config=config)
        metrics = tr.metrics
        spatial_metadata = self._trip_spatial_metadata()
        metrics.update(spatial_metadata)
        return metrics

    # end region

    # region  ── Quality reporting ─────────────────────────────────────────────────────

    def quality_report(self) -> dict:
        """Return a data-quality summary for this file."""
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

        gps_gap_count = 0
        if "GPS Time" in df.columns:
            parser = GpsTimeParser()
            elapsed = parser.to_duration_seconds(df["GPS Time"])
            valid = elapsed.dropna()
            if len(valid) > 1:
                gaps = valid.diff().dropna()
                gps_gap_count = int((gaps > 5).sum())

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

    # end region

    # region  ── Trip construction ─────────────────────────────────────────────────────

    def to_trip(self, config: "ProcessingConfig | None" = None) -> "Trip":
        """Process the curated data and return a Trip.

        The resulting Trip's ``name`` is set to ``self.parquet_name`` so that
        DuckDB ``trip_id`` values align with archive Parquet filenames.
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
        return Trip(
            df=processed_df,
            name=self.parquet_name,
            stop_threshold_kmh=config.stop_threshold_kmh,
            parquet_id=self._compute_parquet_id(),
        )

    # end region


# region  ── Module-level helpers ──────────────────────────────────────────────────────

_TIMESTAMP_COLS = frozenset({"GPS Time", "Device Time"})


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with timestamp columns converted to ``datetime64[ns, UTC]``."""
    parser = GpsTimeParser()
    df = df.copy()
    for col in _TIMESTAMP_COLS:
        if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = parser.to_datetime(df[col])
    return df


def _coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce object-dtype columns that contain Torque dash-placeholders to float64."""
    for col in df.columns:
        if col in _TIMESTAMP_COLS:
            continue
        if df[col].dtype == object:
            coerced = pd.to_numeric(df[col], errors="coerce")
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
    """Infer the decimal separator by scanning the first non-null numeric-looking cell."""
    try:
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
