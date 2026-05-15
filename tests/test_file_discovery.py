"""Tests for pipeline.discover_files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.discover_files import (
    _extract_business_date,
    _is_late_arrival_path,
    discover_sales_files,
    find_missing_dates,
)


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------

class TestExtractBusinessDate:
    def test_valid_filename(self):
        p = Path("sales_2025-03-15.csv")
        assert _extract_business_date(p) == date(2025, 3, 15)

    def test_filename_with_parent_dirs(self):
        p = Path("some/folder/sales_2025-03-01.csv")
        assert _extract_business_date(p) == date(2025, 3, 1)

    def test_invalid_filename_returns_none(self):
        p = Path("random_file.csv")
        assert _extract_business_date(p) is None

    def test_wrong_extension_returns_none(self):
        p = Path("sales_2025-03-01.txt")
        assert _extract_business_date(p) is None


class TestIsLateArrivalPath:
    def test_late_arrivals_folder(self):
        p = Path("Data for sales/late_arrivals/sales_2025-03-01.csv")
        assert _is_late_arrival_path(p) is True

    def test_late_arrival_hyphen(self):
        p = Path("Data for sales/late-arrival/sales_2025-03-01.csv")
        assert _is_late_arrival_path(p) is True

    def test_normal_file(self):
        p = Path("Data for sales/sales_2025-03-01.csv")
        assert _is_late_arrival_path(p) is False

    def test_nested_normal_folder(self):
        p = Path("Data for sales/subfolder/sales_2025-03-01.csv")
        assert _is_late_arrival_path(p) is False


# ---------------------------------------------------------------------------
# Integration tests — file system scanning
# ---------------------------------------------------------------------------

class TestDiscoverSalesFiles:
    def test_discovers_matching_files(self, tmp_path: Path):
        (tmp_path / "sales_2025-03-01.csv").write_text("order_id\n1\n")
        (tmp_path / "sales_2025-03-02.csv").write_text("order_id\n2\n")
        records = discover_sales_files(tmp_path)
        assert len(records) == 2

    def test_ignores_unrelated_files(self, tmp_path: Path):
        (tmp_path / "sales_2025-03-01.csv").write_text("order_id\n1\n")
        (tmp_path / "README.txt").write_text("ignore me")
        (tmp_path / "summary.xlsx").write_text("ignore me")
        records = discover_sales_files(tmp_path)
        assert len(records) == 1

    def test_handles_path_with_spaces(self, tmp_path: Path):
        folder = tmp_path / "Data for sales"
        folder.mkdir()
        (folder / "sales_2025-03-05.csv").write_text("order_id\n5\n")
        records = discover_sales_files(folder)
        assert len(records) == 1
        assert records[0]["file_name"] == "sales_2025-03-05.csv"

    def test_detects_late_arrival_in_nested_folder(self, tmp_path: Path):
        late_dir = tmp_path / "late_arrivals"
        late_dir.mkdir()
        (late_dir / "sales_2025-03-03.csv").write_text("order_id\n3\n")
        (tmp_path / "sales_2025-03-01.csv").write_text("order_id\n1\n")
        records = discover_sales_files(tmp_path)
        assert len(records) == 2
        late = [r for r in records if r["is_late_arrival"]]
        normal = [r for r in records if not r["is_late_arrival"]]
        assert len(late) == 1
        assert len(normal) == 1
        assert late[0]["file_name"] == "sales_2025-03-03.csv"

    def test_no_late_arrivals_folder_does_not_fail(self, tmp_path: Path):
        (tmp_path / "sales_2025-03-01.csv").write_text("order_id\n1\n")
        records = discover_sales_files(tmp_path)
        assert records[0]["is_late_arrival"] is False

    def test_raises_for_missing_dataset_folder(self, tmp_path: Path):
        missing = tmp_path / "nonexistent_folder"
        with pytest.raises(FileNotFoundError):
            discover_sales_files(missing)

    def test_business_date_extracted_from_filename(self, tmp_path: Path):
        (tmp_path / "sales_2025-03-17.csv").write_text("order_id\n17\n")
        records = discover_sales_files(tmp_path)
        assert records[0]["business_date"] == date(2025, 3, 17)


class TestFindMissingDates:
    def test_no_missing_dates_when_all_present(self, tmp_path: Path):
        from config.settings import EXPECTED_DATES
        for d in EXPECTED_DATES:
            (tmp_path / f"sales_{d}.csv").write_text("h\n")
        records = discover_sales_files(tmp_path)
        missing = find_missing_dates(records)
        assert missing == []

    def test_detects_missing_dates(self, tmp_path: Path):
        (tmp_path / "sales_2025-03-01.csv").write_text("h\n")
        records = discover_sales_files(tmp_path)
        missing = find_missing_dates(records)
        # 31 days in March minus the 1 file we created
        assert len(missing) == 30
        assert date(2025, 3, 2) in missing
