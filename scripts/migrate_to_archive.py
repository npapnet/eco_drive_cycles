#!/usr/bin/env python
"""migrate_to_archive.py — Convert raw OBD xlsx files to v2 archive Parquets.

Usage:
    python scripts/migrate_to_archive.py <raw_xlsx_dir> <archive_dir>

For each .xlsx in raw_xlsx_dir:
  - Load via OBDFile.from_xlsx()
  - Run quality_report() to check for missing CURATED_COLS
  - If all required columns are present, write to <archive_dir>/<name>.parquet
  - If columns are missing, print a warning and skip the file

At the end, print a summary: N archived, M skipped.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path


def main(raw_dir: Path, archive_dir: Path) -> None:
    from drive_cycle_calculator.obd_file import OBDFile

    if not raw_dir.exists():
        print(f"ERROR: raw directory not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    archive_dir.mkdir(parents=True, exist_ok=True)

    xlsx_files = sorted(raw_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No .xlsx files found in {raw_dir}")
        return

    archived = 0
    skipped = 0
    skipped_names: list[str] = []

    for xlsx_path in xlsx_files:
        try:
            obd = OBDFile.from_xlsx(xlsx_path)
        except Exception as exc:
            print(f"  SKIP (load error) {xlsx_path.name}: {exc}")
            skipped += 1
            skipped_names.append(xlsx_path.name)
            continue

        report = obd.quality_report()
        missing = report["missing_curated_cols"]

        if missing:
            print(f"  SKIP (missing cols) {xlsx_path.name}: {missing}")
            skipped += 1
            skipped_names.append(xlsx_path.name)
            continue

        dest = archive_dir / f"{obd.name}.parquet"
        obd.to_parquet(dest)
        print(f"  OK  {xlsx_path.name} -> {dest.name}")
        archived += 1

    print()
    print(f"Done. Archived: {archived}, Skipped: {skipped}")
    if skipped_names:
        print(f"Skipped files: {skipped_names}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    raw_dir = Path(sys.argv[1])
    archive_dir = Path(sys.argv[2])
    main(raw_dir, archive_dir)
