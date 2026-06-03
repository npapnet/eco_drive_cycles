# %%
"""
Step 3 — Segment trips into microtrips and save to disk.

Loads archive Parquets from OUTPUT_DIR/trips/, segments each trip into
microtrips, and writes:
  - OUTPUT_DIR/microtrips/<trip>_mt<N>.parquet  — per-microtrip Parquets
  - OUTPUT_DIR/microtrips/summary.csv           — one row per microtrip

Configuration is read from config.json in the same directory.

See: src/drive_cycle_calculator/segmentation.py
     notes/designs/archive/microtrip_design_spec.md
"""

import json
from pathlib import Path

from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter
from drive_cycle_calculator.trip_collection import TripCollection

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

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
    print("Run 010_ingest.py first.")
    raise SystemExit(1)

# ── Load trips ────────────────────────────────────────────────────────────────
tc = TripCollection.from_archive_parquets(trips_dir, PROCESSING_CONFIG)
print(f"Loaded {len(tc)} trips from {trips_dir}.")

# ── Segment and export ────────────────────────────────────────────────────────
segmenter = MicrotripSegmenter(SEGMENTATION_CONFIG)
result = segmenter.segment_collection(tc)
summary = segmenter.export_collection(result, microtrips_dir)

total = len(summary)
if total == 0:
    print("No microtrips produced — check segmentation thresholds.")
    raise SystemExit(0)

summary_path = microtrips_dir / "summary.csv"
summary.to_csv(summary_path, index=False)

print(f"\nDone: {total} microtrip(s) saved to {microtrips_dir}/")
print(f"  Summary: {summary_path}")
print("  Next: run 040_microtrip_clustering.py")
# %%
