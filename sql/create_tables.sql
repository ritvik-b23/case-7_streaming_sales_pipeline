-- Creates base tables used by the pipeline.
-- Run order: this file first, then mart_*.sql views.

CREATE TABLE IF NOT EXISTS raw_sales_orders (
    order_id          TEXT,
    order_timestamp   TEXT,
    customer_id       TEXT,
    product_id        TEXT,
    product_name      TEXT,
    category          TEXT,
    qty               TEXT,
    unit_price        TEXT,
    discount_pct      TEXT,
    region            TEXT,
    source_file       TEXT,
    business_date     DATE,
    ingested_at       TIMESTAMP,
    is_late_arrival   BOOLEAN,
    row_number_in_file INTEGER
);

CREATE TABLE IF NOT EXISTS fact_sales_orders (
    order_id          TEXT PRIMARY KEY,
    order_timestamp   TIMESTAMP,
    customer_id       TEXT,
    product_id        TEXT,
    product_name      TEXT,
    category          TEXT,
    qty               INTEGER,
    unit_price        DOUBLE,
    discount_pct      DOUBLE,
    region            TEXT,
    gross_revenue     DOUBLE,
    discount_amount   DOUBLE,
    net_revenue       DOUBLE,
    source_file       TEXT,
    business_date     DATE,
    ingested_at       TIMESTAMP,
    is_late_arrival   BOOLEAN
);
