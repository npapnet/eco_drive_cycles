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
