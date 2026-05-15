"""Transform raw sales data into a clean, typed fact table.

Steps:
1. Select only expected business columns (ignore extra schema-drift columns)
2. Parse timestamps, cast numeric types
3. Normalise string columns
4. Remove rows with critical missing fields or invalid business-rule values
5. Deduplicate by order_id (keep first occurrence)
6. Calculate gross_revenue, discount_amount, net_revenue
"""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import EXPECTED_COLUMNS

logger = logging.getLogger(__name__)

# Metadata columns added during ingestion that we want to carry through
_META_COLUMNS = ["source_file", "business_date", "ingested_at", "is_late_arrival"]

# Columns that must be non-null to keep a row
_REQUIRED_COLS = ["order_id", "order_timestamp", "customer_id", "product_id", "qty", "unit_price"]


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Cast columns to their intended types, coercing errors to NaN."""
    df = df.copy()
    df["order_timestamp"] = pd.to_datetime(df["order_timestamp"], errors="coerce")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce").fillna(0.0)
    return df


def _normalise_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and title-case categorical text columns."""
    df = df.copy()
    for col in ("region", "category", "product_name"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
    return df


def _remove_invalid_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop rows that violate critical rules. Returns (clean_df, dropped_count)."""
    original_len = len(df)

    # Drop rows missing critical columns
    df = df.dropna(subset=[c for c in _REQUIRED_COLS if c in df.columns])

    # Drop rows with invalid business rules
    qty_valid = df["qty"] > 0
    price_valid = df["unit_price"] >= 0
    disc_valid = df["discount_pct"].between(0, 1, inclusive="both")
    ts_valid = df["order_timestamp"].notna()

    df = df[qty_valid & price_valid & disc_valid & ts_valid]

    dropped = original_len - len(df)
    return df.reset_index(drop=True), dropped


def _deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove duplicate order_id rows, keeping the first occurrence."""
    original_len = len(df)
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    removed = original_len - len(df)
    return df.reset_index(drop=True), removed


def _calculate_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Add gross_revenue, discount_amount, net_revenue columns."""
    df = df.copy()
    df["gross_revenue"] = df["qty"] * df["unit_price"]
    df["discount_amount"] = df["gross_revenue"] * df["discount_pct"]
    df["net_revenue"] = df["gross_revenue"] - df["discount_amount"]
    return df


def transform(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Run all transformation steps on the raw DataFrame.

    Args:
        raw_df: Combined raw ingestion output.

    Returns:
        Tuple of (fact_df, stats) where stats summarises transformation results.
    """
    if raw_df.empty:
        logger.warning("transform() called with empty DataFrame.")
        return pd.DataFrame(), {}

    # Keep expected business columns + metadata
    keep_cols = [c for c in EXPECTED_COLUMNS if c in raw_df.columns]
    keep_cols += [c for c in _META_COLUMNS if c in raw_df.columns]
    df = raw_df[keep_cols].copy()

    df = _coerce_types(df)
    df = _normalise_strings(df)
    df, invalid_dropped = _remove_invalid_rows(df)
    df, dup_removed = _deduplicate(df)
    df = _calculate_revenue(df)

    # Ensure integer qty after dedup (to_numeric returns float when NaNs were present)
    df["qty"] = df["qty"].astype(int)

    stats = {
        "raw_rows": len(raw_df),
        "after_invalid_removal": len(raw_df) - invalid_dropped,
        "invalid_rows_dropped": invalid_dropped,
        "duplicate_rows_removed": dup_removed,
        "clean_rows": len(df),
        "total_net_revenue": round(float(df["net_revenue"].sum()), 2),
    }

    logger.info(
        "Transform complete: %d raw → %d clean rows "
        "(%d invalid dropped, %d duplicates removed).",
        stats["raw_rows"],
        stats["clean_rows"],
        stats["invalid_rows_dropped"],
        stats["duplicate_rows_removed"],
    )
    return df, stats
