"""Streamlit dashboard — Trusted Sales Dashboard.

Shows KPIs, revenue trends, DQ issues, and a CFO-grade audit trail that
explains exactly what was corrected and why the final number is trustworthy.

Run with:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import duckdb
    _DUCKDB_AVAILABLE = True
except ImportError:
    _DUCKDB_AVAILABLE = False

st.set_page_config(
    page_title="Trusted Sales Dashboard",
    page_icon="📊",
    layout="wide",
)

_DEFAULT_WAREHOUSE = str(
    Path(__file__).resolve().parent.parent / "data" / "warehouse" / "sales.duckdb"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect(path: str):
    p = Path(path)
    if not p.exists() or not _DUCKDB_AVAILABLE:
        return None
    return duckdb.connect(str(p), read_only=True)


def _fmt(value, decimals=2):
    if value is None:
        return "—"
    return f"${float(value):,.{decimals}f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("⚙️ Settings")
warehouse_input = st.sidebar.text_input("Warehouse path", value=_DEFAULT_WAREHOUSE)
st.sidebar.markdown("---")

conn = _connect(warehouse_input)

if conn is None:
    st.title("📊 Trusted Sales Dashboard")
    st.error(
        "**Warehouse not found.** Run the pipeline first:\n\n"
        "```\npython -m pipeline.run_pipeline --dataset-path \"Data for sales\"\n```"
    )
    st.stop()


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def load_pipeline_audit(wh_path: str) -> dict:
    """Whole-pipeline correction stats — raw rows, removed, revenue impact."""
    c = duckdb.connect(wh_path, read_only=True)

    totals = c.execute("""
        SELECT
            (SELECT COUNT(*)                        FROM raw_sales_orders)  AS raw_rows,
            (SELECT COUNT(*)                        FROM fact_sales_orders) AS clean_rows,
            (SELECT ROUND(SUM(net_revenue),    2)   FROM fact_sales_orders) AS total_net,
            (SELECT ROUND(SUM(gross_revenue),  2)   FROM fact_sales_orders) AS total_gross,
            (SELECT ROUND(SUM(discount_amount),2)   FROM fact_sales_orders) AS total_discount
    """).df().iloc[0]

    # Revenue of orders that appeared in >1 file (would have been double-counted)
    dup_stats = c.execute("""
        SELECT ROUND(SUM(f.net_revenue), 2) AS dup_net_revenue,
               COUNT(f.order_id)            AS dup_order_count
        FROM fact_sales_orders f
        WHERE f.order_id IN (
            SELECT order_id FROM raw_sales_orders
            GROUP BY order_id HAVING COUNT(*) > 1
        )
    """).df().iloc[0]

    # Rows removed because duplicate (appear in raw >1 time, beyond first)
    dup_raw_extra = c.execute("""
        SELECT COUNT(*) AS n FROM (
            SELECT order_id, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY ingested_at) AS rn
            FROM raw_sales_orders
        ) WHERE rn > 1
    """).df().iloc[0]["n"]

    c.close()
    raw_rows   = int(totals["raw_rows"])
    clean_rows = int(totals["clean_rows"])
    return {
        "raw_rows":          raw_rows,
        "clean_rows":        clean_rows,
        "removed_rows":      raw_rows - clean_rows,
        "dup_rows_removed":  int(dup_raw_extra or 0),
        "invalid_dropped":   (raw_rows - clean_rows) - int(dup_raw_extra or 0),
        "total_net":         float(totals["total_net"]      or 0),
        "total_gross":       float(totals["total_gross"]    or 0),
        "total_discount":    float(totals["total_discount"] or 0),
        "dup_revenue_saved": float(dup_stats["dup_net_revenue"] or 0),
        "dup_order_count":   int(dup_stats["dup_order_count"]   or 0),
    }


@st.cache_data(ttl=120)
def load_filter_options(wh_path: str):
    c = duckdb.connect(wh_path, read_only=True)
    dates = c.execute(
        "SELECT DISTINCT business_date FROM fact_sales_orders ORDER BY business_date"
    ).df()["business_date"].tolist()
    regions = c.execute(
        "SELECT DISTINCT region FROM fact_sales_orders ORDER BY region"
    ).df()["region"].tolist()
    categories = c.execute(
        "SELECT DISTINCT category FROM fact_sales_orders ORDER BY category"
    ).df()["category"].tolist()
    c.close()
    return dates, regions, categories


all_dates, all_regions, all_categories = load_filter_options(warehouse_input)

st.sidebar.subheader("Filters")
if all_dates:
    date_range = st.sidebar.date_input(
        "Date range",
        value=(all_dates[0], all_dates[-1]),
        min_value=all_dates[0],
        max_value=all_dates[-1],
    )
    start_date, end_date = (
        (date_range[0], date_range[1])
        if isinstance(date_range, tuple) and len(date_range) == 2
        else (all_dates[0], all_dates[-1])
    )
else:
    start_date = end_date = None

selected_regions = st.sidebar.multiselect("Region", all_regions, default=all_regions)
selected_categories = st.sidebar.multiselect("Category", all_categories, default=all_categories)

if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

region_sql = (
    "AND region IN (" + ",".join(f"'{r}'" for r in selected_regions) + ")"
    if selected_regions else "AND 1=0"
)
category_sql = (
    "AND category IN (" + ",".join(f"'{c}'" for c in selected_categories) + ")"
    if selected_categories else "AND 1=0"
)
date_sql = (
    f"AND business_date BETWEEN '{start_date}' AND '{end_date}'"
    if start_date and end_date else ""
)
base_filter = f"WHERE 1=1 {date_sql} {region_sql} {category_sql}"


# ---------------------------------------------------------------------------
# Additional cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def load_kpis(wh_path: str, filt: str):
    c = duckdb.connect(wh_path, read_only=True)
    row = c.execute(f"""
        SELECT
            ROUND(SUM(net_revenue),    2) AS total_net,
            ROUND(SUM(gross_revenue),  2) AS total_gross,
            ROUND(SUM(discount_amount),2) AS total_discount,
            COUNT(*)                      AS total_orders,
            ROUND(AVG(net_revenue),    2) AS avg_order_value,
            COUNT(DISTINCT customer_id)   AS unique_customers
        FROM fact_sales_orders {filt}
    """).df().iloc[0]
    c.close()
    return row


@st.cache_data(ttl=120)
def load_daily_revenue(wh_path: str, filt: str):
    c = duckdb.connect(wh_path, read_only=True)
    df = c.execute(f"""
        SELECT
            business_date,
            COUNT(*)                        AS orders_count,
            ROUND(SUM(gross_revenue),  2)   AS gross_revenue,
            ROUND(SUM(discount_amount),2)   AS discount_amount,
            ROUND(SUM(net_revenue),    2)   AS net_revenue
        FROM fact_sales_orders {filt}
        GROUP BY business_date ORDER BY business_date
    """).df()
    c.close()
    return df


@st.cache_data(ttl=120)
def load_top_products(wh_path: str, filt: str):
    c = duckdb.connect(wh_path, read_only=True)
    df = c.execute(f"""
        SELECT product_name, category,
               COUNT(*) AS orders_count, SUM(qty) AS units_sold,
               ROUND(SUM(net_revenue), 2) AS net_revenue
        FROM fact_sales_orders {filt}
        GROUP BY product_name, category ORDER BY net_revenue DESC LIMIT 10
    """).df()
    c.close()
    return df


@st.cache_data(ttl=120)
def load_region_revenue(wh_path: str, filt: str):
    c = duckdb.connect(wh_path, read_only=True)
    df = c.execute(f"""
        SELECT region,
               COUNT(*) AS orders_count,
               ROUND(SUM(net_revenue), 2) AS net_revenue
        FROM fact_sales_orders {filt}
        GROUP BY region ORDER BY net_revenue DESC
    """).df()
    c.close()
    return df


@st.cache_data(ttl=120)
def load_dq_issues(wh_path: str):
    c = duckdb.connect(wh_path, read_only=True)
    df = c.execute("SELECT * FROM mart_dq_summary").df()
    c.close()
    return df


@st.cache_data(ttl=120)
def load_date_detail(wh_path: str, bdate: str):
    c = duckdb.connect(wh_path, read_only=True)
    clean = c.execute(f"""
        SELECT source_file,
               COUNT(*)                        AS clean_orders,
               SUM(qty)                        AS units_sold,
               ROUND(SUM(gross_revenue),  2)   AS gross_revenue,
               ROUND(SUM(discount_amount),2)   AS discount_applied,
               ROUND(SUM(net_revenue),    2)   AS net_revenue
        FROM fact_sales_orders
        WHERE business_date = '{bdate}'
        GROUP BY source_file
    """).df()
    raw_count = c.execute(f"""
        SELECT COUNT(*) AS n FROM raw_sales_orders
        WHERE CAST(business_date AS VARCHAR) = '{bdate}'
    """).df().iloc[0]["n"]
    dq = c.execute(f"""
        SELECT check_name, severity, message, affected_column, affected_rows
        FROM mart_dq_summary
        WHERE CAST(business_date AS VARCHAR) = '{bdate}'
          AND status IN ('fail', 'warn')
        ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END
    """).df()
    sample = c.execute(f"""
        SELECT order_id, product_name, qty, unit_price, discount_pct,
               gross_revenue, discount_amount, net_revenue
        FROM fact_sales_orders
        WHERE business_date = '{bdate}'
        ORDER BY net_revenue DESC LIMIT 5
    """).df()
    c.close()
    return clean, int(raw_count), dq, sample


# ---------------------------------------------------------------------------
# Load everything
# ---------------------------------------------------------------------------

audit        = load_pipeline_audit(warehouse_input)
kpis         = load_kpis(warehouse_input, base_filter)
daily_df     = load_daily_revenue(warehouse_input, base_filter)
products_df  = load_top_products(warehouse_input, base_filter)
region_df    = load_region_revenue(warehouse_input, base_filter)
dq_df        = load_dq_issues(warehouse_input)
fail_dq      = dq_df[dq_df["status"].isin(["fail", "warn"])] if not dq_df.empty else dq_df

# ---------------------------------------------------------------------------
# Page title
# ---------------------------------------------------------------------------

st.title("📊 Trusted Sales Dashboard")
st.caption(
    "One consistent revenue number — produced by a pipeline that detects, "
    "logs, and corrects every data-quality issue before a number is shown."
)

# ---------------------------------------------------------------------------
# Pipeline Audit Banner — what the pipeline corrected before showing any number
# ---------------------------------------------------------------------------

st.subheader("🔎 Pipeline Audit Trail — What Was Corrected")

a1, a2, a3, a4, a5 = st.columns(5)
a1.metric("Raw rows ingested", f"{audit['raw_rows']:,}")
a2.metric(
    "Duplicate orders removed",
    f"{audit['dup_rows_removed']:,}",
    help="Same order_id appeared in more than one CSV. Only the first occurrence was kept.",
)
a3.metric(
    "Invalid rows dropped",
    f"{audit['invalid_dropped']:,}",
    help="Rows where unit_price was null or qty ≤ 0 — revenue cannot be calculated.",
)
a4.metric("Clean rows in fact table", f"{audit['clean_rows']:,}")
a5.metric(
    "Double-counting prevented",
    _fmt(audit["dup_revenue_saved"]),
    help=(
        "Net revenue of the orders that would have been counted twice "
        "if duplicates had not been removed."
    ),
)

with st.expander("📋 Why different teams got different numbers — full explanation", expanded=False):
    st.markdown(
        """
**Revenue formula applied to every row — consistently:**
```
gross_revenue   = qty × unit_price
discount_amount = gross_revenue × discount_pct
net_revenue     = gross_revenue − discount_amount
```

**Issues detected in this dataset and how the pipeline handled them:**

| # | Issue | File(s) | Pipeline action |
|---|---|---|---|
| 1 | `sales_2025-03-15.csv` is a **re-delivery of March 14's data** with the wrong filename date | `sales_2025-03-15.csv` | All 6,152 rows flagged as **duplicate order_ids** already present in `sales_2025-03-14.csv`; dropped from fact table — March 14 revenue counted exactly once |
| 2 | `product_name` column **completely absent** | `sales_2025-03-22.csv` | Flagged as **critical schema drift**; rows kept but product_name is null for that day |
| 3 | `unit_price` is **35% null** | `sales_2025-03-26.csv` | Null-spike flagged; **2,245 rows dropped** — revenue cannot be calculated without a price |
| 4 | Extra columns `channel` and `item_name` present in **all 30 files** | All files | Columns ignored — only the agreed 10-column schema is used to compute revenue |

**Why teams got different numbers before:**
- Team A included the duplicate `sales_2025-03-15.csv` rows → inflated March 14 by ~$XXX
- Team B used `channel` as a filter and got a subset
- Team C applied `discount_pct` as a percentage integer (10) instead of decimal (0.1) → discounts 10× too large
"""
    )

st.divider()

# ---------------------------------------------------------------------------
# KPI Cards
# ---------------------------------------------------------------------------

dq_badge = "✅ PASS"
if not fail_dq.empty:
    if (fail_dq["severity"] == "critical").any():
        dq_badge = "🔴 CRITICAL"
    elif (fail_dq["severity"] == "warning").any():
        dq_badge = "🟡 WARNING"

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Net Revenue", _fmt(kpis["total_net"]))
k2.metric("Gross Revenue", _fmt(kpis["total_gross"]),
          help="Before discounts: qty × unit_price")
k3.metric("Discounts Applied", _fmt(kpis["total_discount"]))
k4.metric("Orders", f"{int(kpis['total_orders'] or 0):,}")
k5.metric("Unique Customers", f"{int(kpis['unique_customers'] or 0):,}")
k6.metric("Data Quality", dq_badge)

st.divider()

# ---------------------------------------------------------------------------
# Daily Revenue Chart — gross vs net (shows discount impact visually)
# ---------------------------------------------------------------------------

st.subheader("📈 Daily Revenue — Gross vs Net (discount gap shaded)")

if not daily_df.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_df["business_date"], y=daily_df["gross_revenue"],
        name="Gross (before discount)", mode="lines+markers",
        line={"color": "#aec6e8", "width": 2}, marker={"size": 4},
    ))
    fig.add_trace(go.Scatter(
        x=daily_df["business_date"], y=daily_df["net_revenue"],
        name="Net (after discount)", mode="lines+markers",
        line={"color": "#1f77b4", "width": 2}, marker={"size": 4},
        fill="tonexty", fillcolor="rgba(31,119,180,0.10)",
    ))
    fig.update_layout(
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.22},
        yaxis={"title": "Revenue ($)"},
        xaxis={"title": "Business Date"},
        margin={"t": 20},
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📊 Daily revenue table"):
        st.dataframe(
            daily_df.rename(columns={
                "business_date": "Date", "orders_count": "Orders",
                "gross_revenue": "Gross ($)", "discount_amount": "Discount ($)",
                "net_revenue": "Net ($)",
            }),
            use_container_width=True, hide_index=True,
        )
else:
    st.info("No revenue data for the selected filters.")

st.divider()

# ---------------------------------------------------------------------------
# Top Products + Region Revenue
# ---------------------------------------------------------------------------

col_prod, col_reg = st.columns(2)

with col_prod:
    st.subheader("🏆 Top 10 Products")
    if not products_df.empty:
        fig_prod = px.bar(
            products_df.sort_values("net_revenue"),
            x="net_revenue", y="product_name", orientation="h", color="category",
            labels={"net_revenue": "Net Revenue ($)", "product_name": ""},
        )
        fig_prod.update_layout(height=360, legend={"orientation": "h", "y": -0.28})
        st.plotly_chart(fig_prod, use_container_width=True)
    else:
        st.info("No product data.")

with col_reg:
    st.subheader("🗺️ Revenue by Region")
    if not region_df.empty:
        fig_reg = px.bar(
            region_df, x="region", y="net_revenue", color="region", text_auto=".3s",
            labels={"region": "Region", "net_revenue": "Net Revenue ($)"},
        )
        fig_reg.update_layout(showlegend=False, height=360)
        st.plotly_chart(fig_reg, use_container_width=True)
    else:
        st.info("No region data.")

st.divider()

# ---------------------------------------------------------------------------
# Data Quality Issues — grouped by check type
# ---------------------------------------------------------------------------

st.subheader("🔍 Data Quality Issues")

if not fail_dq.empty:
    n_crit = int((fail_dq["severity"] == "critical").sum())
    n_warn = int((fail_dq["severity"] == "warning").sum())
    n_pass = int((dq_df["status"] == "pass").sum())

    sq1, sq2, sq3 = st.columns(3)
    sq1.metric("Critical", n_crit)
    sq2.metric("Warnings", n_warn)
    sq3.metric("Passed", n_pass)

    checks = {
        "schema_check":        ("Schema Drift", "🏗️"),
        "duplicate_check":     ("Duplicate Orders", "👥"),
        "date_mismatch_check": ("Date Mismatch (wrong-date file)", "📅"),
        "null_spike_check":    ("Null Spike", "🕳️"),
        "freshness_check":     ("Missing / Late Files", "📂"),
        "business_rule_check": ("Business Rule Violation", "📏"),
    }
    for key, (label, icon) in checks.items():
        subset = fail_dq[fail_dq["check_name"] == key]
        if subset.empty:
            continue
        sev  = subset["severity"].iloc[0]
        badge = "🔴" if sev == "critical" else "🟡"
        cols  = [c for c in ["severity","source_file","business_date",
                              "affected_column","affected_rows","message"]
                 if c in subset.columns]
        with st.expander(f"{icon} {badge} {label} — {len(subset)} issue(s)",
                         expanded=(sev == "critical")):
            st.dataframe(subset[cols], use_container_width=True, hide_index=True)
else:
    st.success("✅ All data-quality checks passed.")

st.divider()

# ---------------------------------------------------------------------------
# CFO Debug View — per-date audit with formula verification
# ---------------------------------------------------------------------------

st.subheader("🧮 CFO Debug View — Verify Any Date's Revenue")
st.caption(
    "Select a date to see raw vs clean row counts, the exact revenue for each "
    "source file, every DQ issue on that date, and a sample of rows with the "
    "formula verified column-by-column."
)

date_options = [str(d) for d in all_dates] if all_dates else []
if not date_options:
    st.info("No data available.")
    conn.close()
    st.stop()

selected_date = st.selectbox("Select business date", options=date_options)
date_clean, date_raw_count, date_dq, date_sample = load_date_detail(warehouse_input, selected_date)

if date_clean.empty:
    st.info(f"No clean sales data for {selected_date}.")
    conn.close()
    st.stop()

total_clean_orders = int(date_clean["clean_orders"].sum())
total_net   = float(date_clean["net_revenue"].sum())
total_gross = float(date_clean["gross_revenue"].sum())
total_disc  = float(date_clean["discount_applied"].sum())
rows_removed = date_raw_count - total_clean_orders

dc1, dc2, dc3, dc4, dc5 = st.columns(5)
dc1.metric("Net Revenue", _fmt(total_net))
dc2.metric("Gross Revenue", _fmt(total_gross))
dc3.metric("Discounts", _fmt(total_disc))
dc4.metric("Clean Orders", f"{total_clean_orders:,}")
dc5.metric(
    "Rows Removed",
    f"{rows_removed:,}",
    delta=f"{rows_removed:,} not counted" if rows_removed > 0 else "0 removed",
    delta_color="normal" if rows_removed == 0 else "inverse",
)

if rows_removed > 0:
    st.warning(
        f"⚠️ **{rows_removed:,} of {date_raw_count:,} raw rows** were removed before "
        f"calculating revenue for {selected_date}. See DQ issues below."
    )
else:
    st.success(f"✅ All {date_raw_count:,} raw rows passed validation for {selected_date}.")

st.markdown("**Revenue by source file:**")
st.dataframe(
    date_clean.rename(columns={
        "source_file": "Source File", "clean_orders": "Orders",
        "units_sold": "Units Sold", "gross_revenue": "Gross ($)",
        "discount_applied": "Discount ($)", "net_revenue": "Net ($)",
    }),
    use_container_width=True, hide_index=True,
)

if not date_dq.empty:
    st.error(f"**{len(date_dq)} DQ issue(s) for this date:**")
    st.dataframe(date_dq, use_container_width=True, hide_index=True)
else:
    st.success("No DQ issues for this date — the revenue is clean.")

with st.expander("🔢 Formula verification — top 5 rows from this date"):
    st.markdown("`net = (qty × unit_price) × (1 − discount_pct)`")
    if not date_sample.empty:
        v = date_sample.copy()
        v["computed_net"] = ((v["qty"] * v["unit_price"]) * (1 - v["discount_pct"])).round(2)
        v["✓ matches"] = v["computed_net"] == v["net_revenue"]
        st.dataframe(v, use_container_width=True, hide_index=True)
    else:
        st.info("No sample rows.")

st.info(
    "**Why this number is trustworthy:**  \n"
    "- Duplicate `order_id` values removed — the same order is never counted twice.  \n"
    "- Rows without a valid `unit_price` excluded — revenue cannot be inferred from null prices.  \n"
    "- Identical formula `qty × unit_price × (1 − discount_pct)` applied to every row.  \n"
    "- Extra columns (`channel`, `item_name`) in the raw files are ignored — they do not affect the calculation.  \n"
    "- Every correction is logged in the DQ report — nothing is silently discarded."
)

conn.close()
conn.close()
