# %%
"""
Step 3 — Segment trips into microtrips and save to disk.

Loads archive Parquets from OUTPUT_DIR/trips/, segments each trip into
motion segments (microtrips), and writes:
  - OUTPUT_DIR/microtrips/<trip_stem>_mt<N>.parquet  — samples for each microtrip
  - OUTPUT_DIR/microtrips/summary.csv                — one row per microtrip

A microtrip is one stop-to-stop motion segment.  The trailing stop is
included in each segment's parquet (stop_phase column = True).

See: src/drive_cycle_calculator/segmentation.py
     docs/designs/archive/microtrip_design_spec.md
"""

from pathlib import Path

import pandas as pd

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter

# ── Configuration ─────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]

OUTPUT_DIR = ROOTDIR / "data"  # must contain a trips/ sub-folder of Parquets
# %%
PROCESSING_CONFIG = ProcessingConfig(window=4, stop_threshold_kmh=2.0)

SEGMENTATION_CONFIG = SegmentationConfig(
    stop_threshold_kmh=2.0,
    stop_min_duration_s=1.0,
    microtrip_min_duration_s=15.0,
    microtrip_min_distance_m=50.0,
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

        duration = (
            float(mt.samples["elapsed_s"].iloc[-1] - mt.samples["elapsed_s"].iloc[0])
            if "elapsed_s" in mt.samples.columns and len(mt.samples) >= 2
            else float(len(mt.samples))
        )
        speed = mt.samples.get("smooth_speed_kmh", mt.samples.get("speed_kmh"))
        mean_speed = float(speed.mean()) if speed is not None else float("nan")

        summary_rows.append(
            {
                "trip_id": p.stem,
                "parquet_id": mt.parquet_id,
                "microtrip_index": i,
                "filename": dest.name,
                "motion_samples": len(mt.samples),
                "stop_samples": len(mt.stop_samples),
                "duration_s": round(duration, 1),
                "stop_duration_s": round(mt.stop_duration_after, 1),
                "mean_speed_kmh": round(mean_speed, 2),
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
