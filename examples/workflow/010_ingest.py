# %%
"""
Step 1 — Ingest raw OBD files into v2 archive Parquets.

Reads every .xlsx / .xls / .csv from DATA_DIR and writes one archive
Parquet per trip into OUTPUT_DIR/trips/.  Skips files that already
exist (delete the destination or set force_reingest = true in config.json
to overwrite).

Equivalent CLI command:
    uv run dcc ingest <DATA_DIR> <OUTPUT_DIR>

Configuration is read from config.json in the same directory as this script.
"""

import json
from pathlib import Path

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.schema import UserMetadata

# ── Configuration (loaded from config.json) ───────────────────────────────────

ROOTDIR = Path(__file__).parents[2]  # repo root
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

DATA_DIR = ROOTDIR / _cfg["data_dir"]       # folder with raw OBD exports (.xlsx / .csv)
OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]   # archive Parquets go to OUTPUT_DIR/trips/
FORCE = _cfg.get("force_reingest", False)   # overwrite existing Parquets?

# Optional: fill in known vehicle details (leave None for unknown).
USER_METADATA = UserMetadata(
    user=None,
    vehicle_make=None,
    vehicle_model=None,
    engine_size_cc=None,
    year=None,
    fuel_type=None,
    vehicle_category=None,
)
# %%
# ── Setup ──────────────────────────────────────────────────────────────────────

archive_dir = OUTPUT_DIR / "trips"
archive_dir.mkdir(parents=True, exist_ok=True)

raw_files = (
    sorted(DATA_DIR.glob("*.xlsx"))
    + sorted(DATA_DIR.glob("*.xls"))
    + sorted(DATA_DIR.glob("*.csv"))
)

if not raw_files:
    print(f"No raw files found in {DATA_DIR} — nothing to ingest.")
    raise SystemExit(0)

print(f"Found {len(raw_files)} raw file(s) in {DATA_DIR}.")

# ── Ingest ────────────────────────────────────────────────────────────────────

ok = skipped = failed = 0

for f in raw_files:
    try:
        obd = OBDFile.from_file(f)
    except Exception as exc:
        print(f"  ERROR  {f.name}: {exc}")
        failed += 1
        continue

    dest = archive_dir / f"{obd.parquet_name}.parquet"

    if dest.exists() and not FORCE:
        print(f"  EXISTS {f.name} -> {dest.name}  (skipped)")
        skipped += 1
        continue

    obd.to_parquet(dest, user_metadata=USER_METADATA)
    print(f"  OK     {f.name} -> {dest.name}")
    ok += 1

print(f"\nDone: {ok} archived, {skipped} skipped (already exist), {failed} failed.")
if skipped:
    print("  Tip: set FORCE = True at the top of this script to overwrite.")
if ok:
    print("  Next: run 020_extract_analyze.py")
