# %%
"""
Step 3 — Segment trips into microtrips and save to disk.

Loads archive Parquets from OUTPUT_DIR/trips/, segments each trip into
motion segments (microtrips), and writes:
  - OUTPUT_DIR/microtrips/<trip_stem>_mt<N>.parquet  — samples for each microtrip
  - OUTPUT_DIR/microtrips/summary.csv                — one row per microtrip

A microtrip is one stop-to-stop motion segment.  The trailing stop is
included in each segment's parquet (stop_phase column = True).

META_COLS lists identifier columns that are excluded from clustering features
in 04_microtrip_clustering.py.  Every other column in summary.csv is treated
as a numeric feature.

Configuration is read from config.json in the same directory as this script.

See: src/drive_cycle_calculator/segmentation.py
     docs/designs/archive/microtrip_design_spec.md
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter

# ── Configuration (loaded from config.json) ───────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]  # must contain a trips/ sub-folder of Parquets

# Columns that identify a microtrip but are not clustering features.
# Keep in sync with the same constant in 04_microtrip_clustering.py.
META_COLS = frozenset(
    {"trip_id", "parquet_id", "microtrip_index", "filename", "motion_samples", "stop_samples"}
)
# %%
_proc = _cfg["processing"]
PROCESSING_CONFIG = ProcessingConfig(
    window=_proc["window"],
    stop_threshold_kmh=_proc["stop_threshold_kmh"],
)

_seg = _cfg["segmentation"]
SEGMENTATION_CONFIG = SegmentationConfig(
    stop_threshold_kmh=_seg["stop_threshold_kmh"],
    stop_min_duration_s=_seg["stop_min_duration_s"],
    microtrip_min_duration_s=_seg["microtrip_min_duration_s"],
    microtrip_min_distance_m=_seg["microtrip_min_distance_m"],
)

# ── Setup ──────────────────────────────────────────────────────────────────────

trips_dir = OUTPUT_DIR / "trips"
microtrips_dir = OUTPUT_DIR / "microtrips"

if not trips_dir.is_dir():
    print(f"No trips/ directory found under {OUTPUT_DIR}.")
    print("Run 01_ingest.py first.")
    raise SystemExit(1)

microtrips_dir.mkdir(parents=True, exist_ok=True)

parquets = sorted(trips_dir.glob("*.parquet"))
print(f"Found {len(parquets)} parquet file(s) in {trips_dir}.")

# ── Segment and save ──────────────────────────────────────────────────────────

segmenter = MicrotripSegmenter(SEGMENTATION_CONFIG)
summary_rows: list[dict] = []

for p in parquets:
    try:
        obd = OBDFile.from_parquet(p)
        trip = obd.to_trip(PROCESSING_CONFIG)
    except Exception as exc:
        print(f"  ERROR  {p.name}: {exc}")
        continue

    microtrips = segmenter.segment(trip)
    print(f"  {p.stem}: {len(microtrips)} microtrip(s)")

    for i, mt in enumerate(microtrips):
        motion = mt.samples.copy()
        motion["stop_phase"] = False
        stop = mt.stop_samples.copy()
        stop["stop_phase"] = True
        combined = pd.concat([motion, stop], ignore_index=True)

        dest = microtrips_dir / f"{p.stem}_mt{i:02d}.parquet"
        combined.to_parquet(dest, index=False)

        df = mt.samples

        # ── Duration ──────────────────────────────────────────────────────────
        if "elapsed_s" in df.columns and len(df) >= 2:
            elapsed = pd.to_numeric(df["elapsed_s"], errors="coerce").dropna()
            duration = float(elapsed.iloc[-1] - elapsed.iloc[0])
        else:
            duration = float(len(df))

        # ── Speed ─────────────────────────────────────────────────────────────
        speed = (
            df.get("smooth_speed_kmh") if "smooth_speed_kmh" in df.columns else df.get("speed_kmh")
        )
        mean_speed = float(speed.mean()) if speed is not None and not speed.empty else float("nan")
        max_speed = float(speed.max()) if speed is not None and not speed.empty else float("nan")

        # ── Distance (trapezoidal integration of speed) ────────────────────────
        if speed is not None and "elapsed_s" in df.columns:
            elapsed = pd.to_numeric(df["elapsed_s"], errors="coerce")
            dt = elapsed.diff().fillna(0.0)
            distance_m = float((pd.to_numeric(speed, errors="coerce").fillna(0.0) / 3.6 * dt).sum())
        else:
            distance_m = float("nan")

        # ── Acceleration / deceleration ────────────────────────────────────────
        if "acc_ms2" in df.columns:
            acc = pd.to_numeric(df["acc_ms2"], errors="coerce")
            mean_acc = float(acc.where(acc > 0).mean())  # NaN when no positive values
            mean_dec = float(acc.where(acc < 0).abs().mean())  # NaN when no negative values
        else:
            mean_acc = mean_dec = float("nan")

        # ── Stop percentage ────────────────────────────────────────────────────
        total_samples = len(df) + len(mt.stop_samples)
        stop_pct = (
            round(len(mt.stop_samples) / total_samples * 100, 1) if total_samples else float("nan")
        )

        summary_rows.append(
            {
                # ── identifiers (META_COLS) ────────────────────────────────────
                "trip_id": p.stem,
                "parquet_id": mt.parquet_id,
                "microtrip_index": i,
                "filename": dest.name,
                "motion_samples": len(df),
                "stop_samples": len(mt.stop_samples),
                # ── features ──────────────────────────────────────────────────
                "duration_s": round(duration, 1),
                "stop_duration_s": round(mt.stop_duration_after, 1),
                "distance_m": round(distance_m, 1),
                "mean_speed_kmh": round(mean_speed, 2),
                "max_speed_kmh": round(max_speed, 2),
                "mean_acc_ms2": round(mean_acc, 4),
                "mean_dec_ms2": round(mean_dec, 4),
                "stop_pct": stop_pct,
            }
        )

total = len(summary_rows)

if total == 0:
    print("\nNo microtrips produced — check segmentation thresholds.")
    raise SystemExit(0)

summary_path = microtrips_dir / "summary.csv"
pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

print(f"\nDone: {total} microtrip(s) saved to {microtrips_dir}/")
print(f"  Summary: {summary_path}")

# %%
