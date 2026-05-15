"""Ingest discovered CSV files into a raw pandas DataFrame and DuckDB table.

Each row is augmented with pipeline metadata before storage.
If a single file fails to read, the error is logged and ingestion continues.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import duckdb
import pandas as pd

from pipeline.discover_files import FileRecord

logger = logging.getLogger(__name__)


def _read_csv_safe(record: FileRecord) -> pd.DataFrame | None:
    """Read a sales CSV file; return None (and log) on failure."""
    try:
        df = pd.read_csv(
            record["file_path"],
            dtype=str,           # keep everything as text — typing happens in transform
            keep_default_na=False,
            na_values=["", "NULL", "null", "N/A", "n/a", "NA", "NaN"],
        )
        df["source_file"] = record["file_name"]
        df["business_date"] = record["business_date"]
        df["ingested_at"] = datetime.now(timezone.utc).isoformat()
        df["is_late_arrival"] = record["is_late_arrival"]
        df["row_number_in_file"] = range(1, len(df) + 1)
        return df
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read %s: %s", record["file_path"], exc)
        return None


def ingest_files(file_records: list[FileRecord]) -> tuple[pd.DataFrame, list[str]]:
    """Read all discovered files and concatenate into one raw DataFrame.

    Args:
        file_records: Output from discover_sales_files().

    Returns:
        Tuple of (raw_df, failed_files).
        raw_df contains all successfully read rows with metadata columns.
        failed_files lists filenames that could not be read.
    """
    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for record in file_records:
        df = _read_csv_safe(record)
        if df is not None:
            frames.append(df)
        else:
            failed.append(record["file_name"])

    if not frames:
        return pd.DataFrame(), failed

    raw_df = pd.concat(frames, ignore_index=True)
    logger.info("Ingested %d rows from %d files.", len(raw_df), len(frames))
    return raw_df, failed


def write_raw_to_duckdb(raw_df: pd.DataFrame, conn: duckdb.DuckDBPyConnection) -> None:
    """Persist *raw_df* to DuckDB table *raw_sales_orders* (replace each run)."""
    conn.execute("DROP TABLE IF EXISTS raw_sales_orders")
    conn.execute(
        """
        CREATE TABLE raw_sales_orders AS
        SELECT * FROM raw_df
        """
    )
    logger.info("Wrote %d raw rows to raw_sales_orders.", len(raw_df))
