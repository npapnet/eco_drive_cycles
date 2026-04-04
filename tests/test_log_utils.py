import os
import time
import pytest
from eco_drive_cycles.log_utils import find_latest_log


class TestFindLatestLog:
    def test_returns_newest_file(self, tmp_path):
        older = tmp_path / "calculations_log_20250101_100000.xlsx"
        newer = tmp_path / "calculations_log_20250101_110000.xlsx"
        older.write_text("x")
        time.sleep(0.02)
        newer.write_text("x")
        # newer has a later mtime
        assert find_latest_log(str(tmp_path)) == str(newer)

    def test_single_file_returns_it(self, tmp_path):
        only = tmp_path / "calculations_log_20250101_100000.xlsx"
        only.write_text("x")
        assert find_latest_log(str(tmp_path)) == str(only)

    def test_empty_dir_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_latest_log(str(tmp_path))

    def test_non_matching_files_ignored(self, tmp_path):
        (tmp_path / "other.xlsx").write_text("x")
        (tmp_path / "calculations_log_20250101_100000.xlsx").write_text("x")
        result = find_latest_log(str(tmp_path))
        assert "calculations_log" in os.path.basename(result)
