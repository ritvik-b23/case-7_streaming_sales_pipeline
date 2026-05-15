"""Discover daily sales CSV files from the dataset folder.

Recursively scans the dataset directory for files matching:
    sales_YYYY-MM-DD.csv

Handles:
- Nested folders (including late_arrivals/)
- Paths with spaces
- Missing dates detection (March 2025 expected)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import TypedDict

from config.settings import EXPECTED_DATES, SALES_FILE_PATTERN


class FileRecord(TypedDict):
    file_path: Path
    file_name: str
    business_date: date
    is_late_arrival: bool


_DATE_RE = re.compile(r"sales_(\d{4}-\d{2}-\d{2})\.csv$", re.IGNORECASE)
_LATE_ARRIVAL_KEYWORDS = ("late_arrivals", "late-arrival", "late arrivals")


def _is_late_arrival_path(path: Path) -> bool:
    """Return True if any folder component name exactly matches a late-arrival keyword."""
    for part in path.parts:
        lower = part.lower()
        if any(lower == kw for kw in _LATE_ARRIVAL_KEYWORDS):
            return True
    return False


def _extract_business_date(file_path: Path) -> date | None:
    """Parse YYYY-MM-DD from a sales_YYYY-MM-DD.csv filename."""
    match = _DATE_RE.search(file_path.name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def discover_sales_files(dataset_path: Path) -> list[FileRecord]:
    """Recursively discover all matching sales CSV files under *dataset_path*.

    Args:
        dataset_path: Root folder to scan (may contain spaces in path).

    Returns:
        Sorted list of FileRecord dicts, one per matching file.
    """
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset folder not found: {dataset_path}\n"
            "Set CASE7_DATASET_PATH or pass --dataset-path to override."
        )

    records: list[FileRecord] = []

    for csv_file in sorted(dataset_path.rglob(SALES_FILE_PATTERN)):
        business_date = _extract_business_date(csv_file)
        if business_date is None:
            continue  # filename doesn't match pattern — skip

        records.append(
            FileRecord(
                file_path=csv_file,
                file_name=csv_file.name,
                business_date=business_date,
                is_late_arrival=_is_late_arrival_path(csv_file),
            )
        )

    return records


def find_missing_dates(file_records: list[FileRecord]) -> list[date]:
    """Return expected March 2025 dates that have no corresponding file."""
    found_dates = {r["business_date"] for r in file_records}
    return [d for d in EXPECTED_DATES if d not in found_dates]


def find_late_arrivals(file_records: list[FileRecord]) -> list[FileRecord]:
    """Return only the late-arrival records."""
    return [r for r in file_records if r["is_late_arrival"]]
