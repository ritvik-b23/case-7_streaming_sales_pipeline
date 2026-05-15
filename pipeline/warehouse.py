"""Write modelled tables and views to the DuckDB warehouse.

Tables created:
  raw_sales_orders   — raw ingestion output (written by ingest.py)
  fact_sales_orders  — cleaned, typed, deduplicated sales rows
  dq_issues          — all DQ issue records for the latest run

Views created:
  mart_daily_revenue
  mart_top_products
  mart_region_revenue
  mart_dq_summary

The warehouse is idempotent: tables are replaced on each run.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def open_warehouse(warehouse_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB warehouse file."""
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(warehouse_path))
    logger.info("Opened warehouse: %s", warehouse_path)
    return conn


def write_fact_table(fact_df: pd.DataFrame, conn: duckdb.DuckDBPyConnection) -> None:
    """Write fact_sales_orders, replacing any existing data."""
    conn.execute("DROP TABLE IF EXISTS fact_sales_orders")
    conn.execute(
        """
        CREATE TABLE fact_sales_orders AS
        SELECT
            CAST(order_id        AS VARCHAR)   AS order_id,
            CAST(order_timestamp AS TIMESTAMP) AS order_timestamp,
            CAST(customer_id     AS VARCHAR)   AS customer_id,
            CAST(product_id      AS VARCHAR)   AS product_id,
            CAST(product_name    AS VARCHAR)   AS product_name,
            CAST(category        AS VARCHAR)   AS category,
            CAST(qty             AS INTEGER)   AS qty,
            CAST(unit_price      AS DOUBLE)    AS unit_price,
            CAST(discount_pct    AS DOUBLE)    AS discount_pct,
            CAST(region          AS VARCHAR)   AS region,
            CAST(gross_revenue   AS DOUBLE)    AS gross_revenue,
            CAST(discount_amount AS DOUBLE)    AS discount_amount,
            CAST(net_revenue     AS DOUBLE)    AS net_revenue,
            CAST(source_file     AS VARCHAR)   AS source_file,
            CAST(business_date   AS DATE)      AS business_date,
            CAST(ingested_at     AS VARCHAR)   AS ingested_at,
            CAST(is_late_arrival AS BOOLEAN)   AS is_late_arrival
        FROM fact_df
        """
    )
    logger.info("Wrote %d rows to fact_sales_orders.", len(fact_df))


def write_dq_issues(issues_df: pd.DataFrame, conn: duckdb.DuckDBPyConnection) -> None:
    """Write DQ issues table, replacing any existing data."""
    conn.execute("DROP TABLE IF EXISTS dq_issues")
    conn.execute("CREATE TABLE dq_issues AS SELECT * FROM issues_df")
    logger.info("Wrote %d DQ issue rows to dq_issues.", len(issues_df))


def build_marts(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or replace all mart views."""
    conn.execute("""
        CREATE OR REPLACE VIEW mart_daily_revenue AS
        SELECT
            business_date,
            COUNT(*)                        AS orders_count,
            COUNT(DISTINCT customer_id)     AS unique_customers,
            ROUND(SUM(gross_revenue), 2)    AS gross_revenue,
            ROUND(SUM(discount_amount), 2)  AS discount_amount,
            ROUND(SUM(net_revenue), 2)      AS net_revenue,
            ROUND(AVG(net_revenue), 2)      AS avg_order_value
        FROM fact_sales_orders
        GROUP BY business_date
        ORDER BY business_date
    """)

    conn.execute("""
        CREATE OR REPLACE VIEW mart_top_products AS
        SELECT
            product_id,
            product_name,
            category,
            COUNT(*)                     AS orders_count,
            SUM(qty)                     AS units_sold,
            ROUND(SUM(net_revenue), 2)   AS net_revenue
        FROM fact_sales_orders
        GROUP BY product_id, product_name, category
        ORDER BY net_revenue DESC
    """)

    conn.execute("""
        CREATE OR REPLACE VIEW mart_region_revenue AS
        SELECT
            region,
            COUNT(*)                     AS orders_count,
            ROUND(SUM(net_revenue), 2)   AS net_revenue
        FROM fact_sales_orders
        GROUP BY region
        ORDER BY net_revenue DESC
    """)

    conn.execute("""
        CREATE OR REPLACE VIEW mart_dq_summary AS
        SELECT
            run_id,
            run_timestamp,
            check_name,
            severity,
            status,
            affected_rows,
            message,
            source_file,
            business_date,
            affected_column
        FROM dq_issues
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'warning'  THEN 2
                ELSE 3
            END,
            run_timestamp DESC
    """)

    logger.info("Built mart views: mart_daily_revenue, mart_top_products, mart_region_revenue, mart_dq_summary.")


def build_warehouse(
    fact_df: pd.DataFrame,
    issues_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    warehouse_path: Path,
) -> duckdb.DuckDBPyConnection:
    """Full warehouse build: open connection, write tables, build views."""
    conn = open_warehouse(warehouse_path)

    # Write raw table
    conn.execute("DROP TABLE IF EXISTS raw_sales_orders")
    conn.execute("CREATE TABLE raw_sales_orders AS SELECT * FROM raw_df")

    write_fact_table(fact_df, conn)
    write_dq_issues(issues_df, conn)
    build_marts(conn)

    conn.commit()
    return conn
