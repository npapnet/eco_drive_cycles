# segmentation.py
# ---------------
# Two-stage microtrip segmentation: boundary detection then object construction.
# See microtrip_design_spec.md §5.

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from drive_cycle_calculator.microtrip import Microtrip
from drive_cycle_calculator.schema import SegmentationConfig

if TYPE_CHECKING:
    from drive_cycle_calculator.trip import Trip
    from drive_cycle_calculator.trip_collection import TripCollection

_logger = logging.getLogger(__name__)


@dataclass
class SegmentBoundary:
    """Positional iloc index bounds for one candidate microtrip segment.

    Produced by detect_boundaries(); consumed by build_microtrips().
    Both motion and stop bounds are derived in a single pass over the
    speed signal.

    See microtrip_design_spec.md §5.2.
    """

    motion_start_idx: int
    motion_end_idx: int
    stop_start_idx: int
    stop_end_idx: int


def _get_runs(arr: list) -> list[tuple[bool, int, int]]:
    """Run-length encode a boolean sequence.

    Returns (value, start, end) tuples with half-open [start, end) intervals.
    Works on Python lists and any sequence supporting len() and bool() elements.
    """
    if not arr:
        return []
    runs: list[tuple[bool, int, int]] = []
    current = bool(arr[0])
    start = 0
    for i in range(1, len(arr)):
        v = bool(arr[i])
        if v != current:
            runs.append((current, start, i))
            current = v
            start = i
    runs.append((current, start, len(arr)))
    return runs


def detect_boundaries(
    speed: pd.Series,
    config: SegmentationConfig,
) -> list[SegmentBoundary]:
    """Detect motion/stop boundaries in a pre-smoothed speed signal.

    Stage 1 of the two-stage segmentation design. Operates on the raw
    speed array only — no Trip object required. This isolation allows the
    function to be tested against speed arrays independently.

    Sample count is used as a proxy for duration, which assumes ~1 Hz OBD
    sampling. This holds for Torque-app exports and is documented here as
    a known approximation.

    Parameters
    ----------
    speed : pd.Series
        Pre-smoothed speed in km/h (smooth_speed_kmh column from
        ProcessingConfig.apply()). Passing raw speed produces incorrect
        boundaries.
    config : SegmentationConfig
        Segmentation parameters (thresholds, minimum durations).

    Returns
    -------
    list[SegmentBoundary]
        Detected boundaries. Returns [] (not None) for degenerate input:
        all-stopped signal, signal shorter than microtrip_min_duration_s,
        or no valid (motion + trailing confirmed stop) pairs found.

    See microtrip_design_spec.md §5.3.
    """
    if len(speed) == 0:
        return []

    speed_vals = pd.to_numeric(speed, errors="coerce").fillna(0.0)

    # Degenerate: all samples below threshold — no motion possible.
    if (speed_vals < config.stop_threshold_kmh).all():
        _logger.warning(
            "detect_boundaries: speed series entirely below stop_threshold_kmh=%.1f — "
            "no microtrips possible.",
            config.stop_threshold_kmh,
        )
        return []

    # Degenerate: series too short to contain a valid microtrip.
    if len(speed_vals) < config.microtrip_min_duration_s:
        _logger.warning(
            "detect_boundaries: series length %d < microtrip_min_duration_s=%.1f — "
            "no boundaries possible.",
            len(speed_vals),
            config.microtrip_min_duration_s,
        )
        return []

    is_stopped: list[bool] = (speed_vals < config.stop_threshold_kmh).tolist()
    min_stop_samples = max(1, round(config.stop_min_duration_s))

    # Demote unconfirmed stops (below minimum stop duration) to "moving" so
    # the flanking motion blocks are treated as a single continuous segment.
    effective = is_stopped[:]
    for val, start, end in _get_runs(is_stopped):
        if val and (end - start) < min_stop_samples:
            effective[start:end] = [False] * (end - start)

    # Each motion run whose immediate successor is a confirmed stop = one boundary.
    runs = _get_runs(effective)
    boundaries: list[SegmentBoundary] = []
    for k, (val, start, end) in enumerate(runs):
        if not val and k + 1 < len(runs):
            nv, ns, ne = runs[k + 1]
            if nv:
                boundaries.append(
                    SegmentBoundary(
                        motion_start_idx=start,
                        motion_end_idx=end,
                        stop_start_idx=ns,
                        stop_end_idx=ne,
                    )
                )

    return boundaries


def build_microtrips(
    trip: Trip,
    boundaries: list[SegmentBoundary],
    config: SegmentationConfig,
) -> list[Microtrip]:
    """Construct, filter, and bind Microtrip objects from detected boundaries.

    Stage 2 of the two-stage segmentation design. Applies duration and
    distance filters, instantiates Microtrip objects, and binds each to
    the parent Trip via weakref.

    Filtering order per boundary (see spec):
      1. Total duration: (stop_end_idx - motion_start_idx) treated as seconds
         at ~1 Hz >= config.microtrip_min_duration_s
      2. Distance: integral of speed over motion phase
         >= config.microtrip_min_distance_m

    Parameters
    ----------
    trip : Trip
        Parent Trip owning the processed DataFrame. Passed to Microtrip.bind().
    boundaries : list[SegmentBoundary]
        Output of detect_boundaries().
    config : SegmentationConfig
        Segmentation parameters used for duration and distance filtering.

    Returns
    -------
    list[Microtrip]
        Filtered Microtrip objects with weakref bound to trip. Returns []
        (not None) if no boundaries pass the filters.

    See microtrip_design_spec.md §5.4.
    """
    if not boundaries:
        return []

    df = trip.data
    has_elapsed = "elapsed_s" in df.columns
    microtrips: list[Microtrip] = []

    for b in boundaries:
        # Duration filter: total sample count (motion + stop) as seconds at ~1 Hz.
        if b.stop_end_idx - b.motion_start_idx < config.microtrip_min_duration_s:
            continue

        # Distance filter: integrate speed_ms × dt over the motion phase.
        motion = df.iloc[b.motion_start_idx:b.motion_end_idx]
        speed_ms = (
            pd.to_numeric(motion["smooth_speed_kmh"], errors="coerce").fillna(0.0) / 3.6
        )
        if has_elapsed:
            elapsed = pd.to_numeric(motion["elapsed_s"], errors="coerce")
            # bfill fills the first-sample NaN from diff() using the next dt value.
            dt = elapsed.diff().bfill().fillna(1.0)
        else:
            dt = pd.Series(1.0, index=speed_ms.index)

        distance_m = float((speed_ms * dt).sum())
        if distance_m < config.microtrip_min_distance_m:
            continue

        mt = Microtrip(
            trip_file=trip.file or Path(""),
            parquet_id=trip.parquet_id,
            start_idx=b.motion_start_idx,
            end_idx=b.motion_end_idx,
            stop_start_idx=b.stop_start_idx,
            stop_end_idx=b.stop_end_idx,
        )
        mt.bind(trip)
        microtrips.append(mt)

    return microtrips


class MicrotripSegmenter:
    """Configuration-owning segmenter that drives both pipeline stages.

    Parameters
    ----------
    config : SegmentationConfig, optional
        Explicit config object. If omitted, kwargs are forwarded to
        SegmentationConfig().
    **kwargs
        Forwarded to SegmentationConfig when config is None. Allows
        ``MicrotripSegmenter(stop_threshold_kmh=3.0)`` without importing
        SegmentationConfig directly.
    """

    def __init__(
        self,
        config: SegmentationConfig | None = None,
        **kwargs,
    ) -> None:
        self.config = config if config is not None else SegmentationConfig(**kwargs)

    def segment(self, trip: Trip) -> list[Microtrip]:
        """Segment trip into microtrips and store results on trip._microtrips."""
        data = trip.data
        if "smooth_speed_kmh" not in data.columns:
            trip._microtrips = []
            trip._segmentation_config = self.config
            return []
        speed = (
            pd.to_numeric(data["smooth_speed_kmh"], errors="coerce")
            .fillna(0.0)
            .reset_index(drop=True)
        )
        boundaries = detect_boundaries(speed, self.config)
        microtrips = build_microtrips(trip, boundaries, self.config)
        trip._microtrips = microtrips
        trip._segmentation_config = self.config
        return microtrips

    def segment_collection(
        self, tc: TripCollection
    ) -> dict[str, list[Microtrip]]:
        """Segment all trips in a TripCollection.

        Returns {trip.name: [Microtrip, ...]}. Each trip in tc is also
        populated in place — tc.trips[i].microtrips works after this call.
        """
        return {trip.name: self.segment(trip) for trip in tc.trips}

    def export_collection(
        self,
        result: dict[str, list[Microtrip]],
        dest: Path,
    ) -> "pd.DataFrame":
        """Save all microtrips to dest/ and return a summary DataFrame.

        Each microtrip is written as ``<trip_id>_mt<idx>.parquet``. Metrics
        are computed from the in-memory samples before saving.

        Parameters
        ----------
        result : dict[str, list[Microtrip]]
            Output of ``segment_collection()``.
        dest : Path
            Directory to write microtrip Parquet files into.

        Returns
        -------
        pd.DataFrame
            One row per microtrip. Columns: ``trip_id``, ``microtrip_idx``,
            ``path``, ``duration_s``, ``distance_m``, ``mean_speed_kmh``.
        """
        dest.mkdir(parents=True, exist_ok=True)
        rows: list[dict] = []
        for trip_id, microtrips in result.items():
            safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in trip_id)
            for idx, mt in enumerate(microtrips):
                fpath = dest / f"{safe_id}_mt{idx:03d}.parquet"
                mt.to_parquet(fpath)

                motion = mt.samples
                stop = mt.stop_samples

                if "elapsed_s" in motion.columns:
                    elapsed = pd.to_numeric(
                        pd.concat([motion, stop])["elapsed_s"], errors="coerce"
                    ).dropna()
                    duration_s = (
                        float(elapsed.iloc[-1] - elapsed.iloc[0])
                        if len(elapsed) >= 2
                        else float(len(motion) + len(stop))
                    )
                    dt = pd.to_numeric(motion["elapsed_s"], errors="coerce").diff().bfill().fillna(1.0)
                else:
                    duration_s = float(len(motion) + len(stop))
                    dt = pd.Series(1.0, index=motion.index)

                speed_col = (
                    "smooth_speed_kmh" if "smooth_speed_kmh" in motion.columns else "speed_kmh"
                )
                speed_kmh = pd.to_numeric(
                    motion.get(speed_col, pd.Series(dtype=float)), errors="coerce"
                ).fillna(0.0)
                distance_m = float((speed_kmh / 3.6 * dt).sum())
                mean_speed_kmh = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0
                max_speed_kmh = float(speed_kmh.max()) if not speed_kmh.empty else 0.0
                speed_95th_kmh = float(speed_kmh.quantile(0.95)) if not speed_kmh.empty else 0.0
                stop_duration_s = float(mt.stop_duration_after)

                if "acc_ms2" in motion.columns and distance_m > 0:
                    acc = pd.to_numeric(motion["acc_ms2"], errors="coerce").fillna(0.0)
                    acc_pos = acc.clip(lower=0.0)
                    rpa = float((speed_kmh / 3.6 * acc_pos * dt).sum() / distance_m)
                else:
                    rpa = float("nan")

                rows.append({
                    "trip_id": trip_id,
                    "microtrip_idx": idx,
                    "path": str(fpath),
                    "duration_s": duration_s,
                    "stop_duration_s": stop_duration_s,
                    "distance_m": distance_m,
                    "mean_speed_kmh": mean_speed_kmh,
                    "max_speed_kmh": max_speed_kmh,
                    "speed_95th_kmh": speed_95th_kmh,
                    "rpa": rpa,
                })

        return pd.DataFrame(rows)
