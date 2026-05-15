# Data Contract — Daily Sales CSV Feed

**Version:** 1.0  
**Owner:** Data Engineering Team  
**Effective Date:** 2025-03-01  
**Status:** Active

---

## Source

| Field | Value |
|---|---|
| Source name | E-commerce Sales Platform |
| Source system | Internal order management system |
| Delivery mechanism | CSV file drop to shared folder |
| Destination folder | `Data for sales/` |

---

## Delivery Expectations

| Field | Value |
|---|---|
| Delivery frequency | Daily (once per calendar day) |
| Expected delivery time | By 02:00 UTC the following day |
| File naming convention | `sales_YYYY-MM-DD.csv` (e.g., `sales_2025-03-15.csv`) |
| Expected date range | All calendar days within the reporting month |
| Late arrivals | Files may arrive in a `late_arrivals/` subfolder with original filename date |

---

## Expected Schema

| Column | Type | Nullable | Description |
|---|---|---|---|
| `order_id` | string | NO | Unique order identifier (e.g., `ORD2025030100000`) |
| `order_timestamp` | ISO 8601 datetime | NO | Timestamp when the order was placed |
| `customer_id` | string | NO | Unique customer identifier |
| `product_id` | string | NO | Product identifier (e.g., `P001`) |
| `product_name` | string | YES | Human-readable product name |
| `category` | string | YES | Product category (e.g., Electronics, Apparel) |
| `qty` | integer | NO | Quantity ordered — must be > 0 |
| `unit_price` | float | NO | Unit price in USD — must be ≥ 0 |
| `discount_pct` | float | NO | Discount percentage as decimal [0.0, 1.0] |
| `region` | string | NO | Sales region (North, South, East, West) |

---

## Business Rules

| Rule | Enforcement |
|---|---|
| `order_id` must be globally unique across all files | Duplicates removed; kept row is first occurrence |
| `qty` must be > 0 | Rows with `qty ≤ 0` are dropped |
| `unit_price` must be ≥ 0 | Rows with `unit_price < 0` are dropped |
| `discount_pct` must be in [0.0, 1.0] | Rows outside range are dropped |
| `order_timestamp` must be parseable as ISO 8601 | Unparseable rows are dropped |
| Revenue formula is locked | `net_revenue = qty × unit_price × (1 − discount_pct)` |

---

## Duplicate Handling

If the same `order_id` appears in multiple files:
1. The pipeline detects and counts duplicates via the **duplicate check**
2. The DQ report records the affected files and row counts
3. The transformation step keeps the **first occurrence** of each `order_id`
4. Duplicate count is visible in the terminal summary and the dashboard

---

## Late-Arrival Handling

Files placed in any subfolder whose name contains `late_arrivals`, `late-arrival`, or `late arrivals` are:
1. Discovered and ingested normally
2. Flagged with `is_late_arrival = True` in all pipeline tables
3. Recorded as `info`-severity DQ events in the report
4. Included in all mart calculations unless explicitly filtered

---

## Schema Drift Handling

If a file contains unexpected columns or is missing required columns:

| Scenario | Severity | Action |
|---|---|---|
| Required column missing | Critical | File still ingested; affected rows excluded from fact table |
| Extra column present | Warning | Extra column ignored; not written to fact table |
| All columns match | Info / Pass | No action |

---

## Contract Breach Policy

| Breach type | Automated action | Manual escalation |
|---|---|---|
| Missing file for a date | Warning in DQ report | Notify source team within 4 hours |
| Critical DQ issues detected | Pipeline continues; DQ report written | Data team reviews before sharing revenue number |
| Schema drift (missing cols) | Affected rows excluded from fact table | Source team notified to fix schema |
| Delivery after SLA | File ingested; flagged as late arrival | No escalation unless > 48 hours late |
