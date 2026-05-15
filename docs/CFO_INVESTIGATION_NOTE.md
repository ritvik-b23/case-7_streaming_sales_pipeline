# If Monday's Revenue Number Changed by 3%, Here Is How I Would Investigate It in Under 10 Minutes

**Prepared for:** CFO  
**Author:** Data Engineering Team  
**Purpose:** Step-by-step investigation protocol for unexpected revenue changes

---

## The Situation

It's Monday. Last week's total revenue is $124,583. This week the same period shows $128,120 — a 3% increase. Or decrease. Either way, someone is asking: *"Is this real, or a data problem?"*

Here is how to find out in 10 minutes.

---

## Step 1 — Check the DQ Summary (1 minute)

Open the dashboard → **Data Quality Status** tab.

Or from the terminal:

```bash
cat data/dq_reports/latest_dq_report.json
```

Look for:
- `critical_issues > 0` → stop here and fix the critical issue first
- `warning_issues > 0` → note which checks fired, continue to Step 2
- `overall_status: "pass"` → data looks clean; change is likely real business movement

**If critical issues exist:** The revenue number may be wrong. Do not share it until the issue is resolved.

---

## Step 2 — Check for Late-Arriving Files (1 minute)

In the DQ report, look for `check_name = "freshness_check"` rows with `is_late_arrival = true`.

Late-arriving files from a prior period can inflate or deflate the current period's revenue if they contain dates outside the expected window.

**Action:** Check `is_late_arrival` column in the fact table for any affected dates.

---

## Step 3 — Check Duplicate Order ID Count (2 minutes)

Run in Python or DuckDB:

```sql
SELECT COUNT(*) - COUNT(DISTINCT order_id) AS dup_count
FROM raw_sales_orders;
```

Or check the DQ report for `check_name = "duplicate_check"`.

- If `dup_count` increased since last run → a source file sent repeated orders, inflating revenue
- If `dup_count` decreased → a dedup issue was fixed, reducing revenue

**Action:** Compare this week's duplicate count to last week's. A jump here explains many "surprise" revenue changes.

---

## Step 4 — Check Schema Drift (1 minute)

Look for `check_name = "schema_check"` failures in the DQ report.

- A new column in one file could indicate the source system changed how it exports prices or discounts
- A missing column means affected rows were dropped → revenue goes down

**Action:** If schema drift is present, check whether the affected file's rows were excluded or included with incorrect values.

---

## Step 5 — Check Null Spikes (1 minute)

Look for `check_name = "null_spike_check"` in the DQ report.

Pay special attention to null spikes in:
- `unit_price` → rows with null price default to $0, suppressing revenue
- `qty` → same effect
- `discount_pct` → null is filled with 0.0 in the pipeline, which may inflate net_revenue

**Action:** If a null spike appears on a specific date, revenue for that date is unreliable.

---

## Step 6 — Compare Daily Revenue Before and After Rerun (2 minutes)

Open the dashboard → **CFO Debug View** → select the affected business date.

Compare:
- `gross_revenue` — total before discounts
- `discount_amount` — total discounts applied
- `net_revenue` — the final number

If gross and net are both up proportionally, it's real volume. If net moved but gross didn't, discounts changed.

You can also query directly:

```sql
SELECT business_date, orders_count, gross_revenue, discount_amount, net_revenue
FROM mart_daily_revenue
ORDER BY business_date;
```

---

## Step 7 — Trace Affected Dates to Source Files (1 minute)

In the dashboard's CFO Debug View, the **Revenue breakdown by source file** table shows which CSV contributed what revenue for the selected date.

Or via SQL:

```sql
SELECT source_file, COUNT(*) AS orders, SUM(net_revenue) AS net_revenue
FROM fact_sales_orders
WHERE business_date = '2025-03-XX'
GROUP BY source_file;
```

If a new file was added or re-delivered for a prior date, it will appear here.

---

## Step 8 — Classify the Change (1 minute)

Based on your investigation, the revenue change falls into one of three categories:

| Classification | Signal | Response |
|---|---|---|
| **Real business movement** | DQ clean, no dupes, no schema issues, volume changed | Share the number with confidence |
| **Data correction** | A prior duplicate or null was fixed | Communicate "corrected revenue" to stakeholders |
| **Pipeline bug** | Logic error, formula change, or infrastructure issue | Revert the pipeline, investigate root cause, rerun |

---

## Summary

| Step | Time | Tool |
|---|---|---|
| Check DQ summary | 1 min | Dashboard or `latest_dq_report.json` |
| Check late arrivals | 1 min | DQ report `freshness_check` |
| Check duplicate count | 2 min | DQ report `duplicate_check` or SQL |
| Check schema drift | 1 min | DQ report `schema_check` |
| Check null spikes | 1 min | DQ report `null_spike_check` |
| Compare daily revenue | 2 min | Dashboard CFO Debug View |
| Trace to source files | 1 min | Dashboard or SQL |
| **Total** | **~10 min** | |
