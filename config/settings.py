"""Central configuration for the sales pipeline."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default dataset folder — can be overridden via env var or CLI argument
_env_dataset = os.environ.get("CASE7_DATASET_PATH", "Data for sales")
DATASET_PATH: Path = PROJECT_ROOT / _env_dataset

WAREHOUSE_PATH: Path = PROJECT_ROOT / "data" / "warehouse" / "sales.duckdb"
DQ_REPORTS_DIR: Path = PROJECT_ROOT / "data" / "dq_reports"
RAW_DATA_DIR: Path = PROJECT_ROOT / "data" / "raw"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS: list[str] = [
    "order_id",
    "order_timestamp",
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "qty",
    "unit_price",
    "discount_pct",
    "region",
]

# Columns that must not be null for a row to be kept
CRITICAL_COLUMNS: list[str] = [
    "order_id",
    "order_timestamp",
    "customer_id",
    "product_id",
    "qty",
    "unit_price",
    "region",
]

# ---------------------------------------------------------------------------
# Expected business dates — March 2025 (all 31 days)
# ---------------------------------------------------------------------------
def _march_2025_dates() -> list[date]:
    start = date(2025, 3, 1)
    return [start + timedelta(days=i) for i in range(31)]


EXPECTED_DATES: list[date] = _march_2025_dates()

# ---------------------------------------------------------------------------
# DQ thresholds
# ---------------------------------------------------------------------------
# Flag a column as a null-spike if its per-file null% exceeds this multiplier
# relative to the global median null% for that column
NULL_SPIKE_MULTIPLIER: float = 3.0
# Absolute threshold — always flag if null% exceeds this, regardless of median
NULL_SPIKE_ABSOLUTE_THRESHOLD: float = 0.20  # 20 %

# ---------------------------------------------------------------------------
# File pattern
# ---------------------------------------------------------------------------
SALES_FILE_PATTERN: str = "sales_????-??-??.csv"
