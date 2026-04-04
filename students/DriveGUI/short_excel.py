# short_excel.py
# --------------
# 1️⃣  Ask the user to pick a folder full of *.xlsx* logger files.
# 2️⃣  Read cell A2 of each workbook to get the recording timestamp.
# 3️⃣  Sort the files chronologically.
# 4️⃣  Group them by calendar day and label "Morning" or "Evening".
# 5️⃣  Build Day objects so other scripts can use the result.
#
# Note:  Every class / function name is identical to the old file, so
#        nothing else in your project needs to change.

import glob
import os
import re
from collections import OrderedDict
from datetime import datetime
from tkinter import filedialog

import pandas as pd


# ────────────────────────────────────────────────────────────────
# 1. Small helper class – one day’s worth of filenames
# ────────────────────────────────────────────────────────────────
class Day:
    """Hold the morning / evening filenames for a specific date."""

    def __init__(self, date):
        self.date = date          # datetime.date (e.g. 2025-06-25)
        self.morning = None       # (filename, datetime) or None
        self.evening = None       # (filename, datetime) or None

    def set_entry(self, file_name: str, dt: datetime) -> None:
        """Before 12:00 → morning, otherwise evening."""
        if dt.hour < 12:
            self.morning = (file_name, dt)
        else:
            self.evening = (file_name, dt)

    def __str__(self) -> str:      # nice for debugging / print()
        m = (
            f"{self.morning[0]} ({self.morning[1].strftime('%Y-%m-%d %H:%M:%S')})"
            if self.morning else "N/A"
        )
        e = (
            f"{self.evening[0]} ({self.evening[1].strftime('%Y-%m-%d %H:%M:%S')})"
            if self.evening else "N/A"
        )
        return f"Date: {self.date} | Morning: {m} | Evening: {e}"


# ────────────────────────────────────────────────────────────────
# 2. Main routine – unchanged signature
# ────────────────────────────────────────────────────────────────
def process_files() -> tuple[str, list[Day]]:
    """
    Open a folder-picker, scan every *.xlsx* file, and return
    ``(folder_path, days)`` where *days* is a list of **Day** objects
    sorted by date.

    The folder path is returned explicitly so callers can pass it to
    ``run_calculations()`` without relying on ``os.getcwd()``.
    """
    # 2️⃣.1  Pick folder
    folder = filedialog.askdirectory(title="Select Folder Containing Excel Files")
    if not folder:                       # user cancelled
        return "", []

    # 2️⃣.2  Build (filename, datetime) pairs
    file_times: list[tuple[str, datetime]] = []

    for fname in glob.glob(os.path.join(folder, "*.xlsx")):
        # Read only cell A2 (row-1, col-0) – contains timestamp string
        try:
            date_cell = str(pd.read_excel(fname, header=None).iloc[1, 0])
        except Exception as err:
            print(f"{fname}: ERROR reading date ({err})")
            continue

        # Clean "Mon Sep 16 18:45:50 GMT+03:00 2019" → "Mon Sep 16 18:45:50 +0300 2019"
        date_cell = date_cell.replace("GMT", "")
        date_cell = re.sub(r"(\+\d\d):(\d\d)", r"\1\2", date_cell)

        try:
            dt = datetime.strptime(date_cell.strip(), "%a %b %d %H:%M:%S %z %Y")
        except Exception as err:
            print(f"{fname}: cannot parse date ({err})")
            continue

        file_times.append((fname, dt))

    # 2️⃣.3  Sort chronologically and group by calendar day
    file_times.sort(key=lambda t: t[1])

    grouped: "OrderedDict[datetime.date, list[tuple[str, datetime]]]" = OrderedDict()
    for fname, dt in file_times:
        grouped.setdefault(dt.date(), []).append((fname, dt))

    # 2️⃣.4  Build Day objects
    days: list[Day] = []
    for day_idx, (date_key, entries) in enumerate(grouped.items(), 1):
        day_obj = Day(date_key)
        for fname, dt in entries:
            day_obj.set_entry(fname, dt)
            # Optional console output
            session = "Morning" if dt.hour < 12 else "Evening"
            print(f"Day {day_idx} – {session}: {fname} ({dt.strftime('%Y-%m-%d %H:%M:%S')})")
        days.append(day_obj)

    return folder, days


# ────────────────────────────────────────────────────────────────
# 3. Quick manual test
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _folder, result = process_files()
    print("\nSummary:")
    for d in result:
        print(d)
