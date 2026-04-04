import os
import pandas as pd
import pytest
from drive_cycle_calculator.calculations import run_calculations


def _make_session_xlsx(path, n_rows: int = 10) -> None:
    """Write a minimal valid OBD-II session xlsx.

    Uses numeric GPS times (0, 1, 2, ...) so gps_to_duration_seconds takes
    the fast numeric path.  The date-parsing in run_calculations falls back
    to the file's mtime when strptime fails on a plain integer, which is
    acceptable for these tests.
    """
    pd.DataFrame({
        "GPS Time": list(range(n_rows)),
        "Speed (OBD)(km/h)": [30.0] * n_rows,
        "CO₂ in g/km (Average)(g/km)": [120.0] * n_rows,
        "Engine Load(%)": [50.0] * n_rows,
        "Fuel flow rate/hour(l/hr)": [5.0] * n_rows,
    }).to_excel(str(path), index=False)


class TestRunCalculations:
    def test_happy_path_writes_both_logs(self, tmp_path):
        """A folder with one valid xlsx produces both a text log and an Excel log."""
        _make_session_xlsx(tmp_path / "session.xlsx")
        log_dir = str(tmp_path / "log")

        txt, xlsx = run_calculations(str(tmp_path), log_folder=log_dir)

        assert os.path.isfile(txt), "Text log not written"
        assert os.path.isfile(xlsx), "Excel log not written"
        sheets = pd.read_excel(xlsx, sheet_name=None)
        data_sheets = {k: v for k, v in sheets.items() if k != "Log"}
        assert len(data_sheets) >= 1, "Expected at least one data sheet in Excel log"

    def test_missing_required_column_skips_file(self, tmp_path):
        """An xlsx missing a required column is skipped; text log records the skip."""
        pd.DataFrame({
            "GPS Time": list(range(5)),
            "Speed (OBD)(km/h)": [10.0] * 5,
            # deliberately omitting CO2, Engine Load, Fuel flow
        }).to_excel(str(tmp_path / "bad.xlsx"), index=False)

        log_dir = str(tmp_path / "log")
        txt, xlsx = run_calculations(str(tmp_path), log_folder=log_dir)

        text = open(txt, encoding="utf-8").read()
        assert "missing" in text.lower(), "Expected 'missing' in text log for skipped file"
        sheets = pd.read_excel(xlsx, sheet_name=None)
        assert "Log" in sheets, "Expected fallback 'Log' sheet when no data was written"

    def test_empty_folder_writes_log_sheet(self, tmp_path):
        """A folder with no xlsx files still produces a valid workbook with a 'Log' sheet."""
        log_dir = str(tmp_path / "log")
        txt, xlsx = run_calculations(str(tmp_path), log_folder=log_dir)

        assert os.path.isfile(xlsx)
        sheets = pd.read_excel(xlsx, sheet_name=None)
        assert "Log" in sheets
