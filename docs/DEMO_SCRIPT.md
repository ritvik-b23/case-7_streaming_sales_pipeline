# Demo Script — Case 7: Streaming Sales Pipeline

**Duration:** 4–6 minutes  
**Audience:** Technical hiring panel / data engineering interview  
**Goal:** Show a working data pipeline that solves a real business problem (inconsistent revenue numbers) and demonstrate data-quality thinking

---

## 0:00 – 0:30 | Introduction

> "Let me walk you through Case 7 — a streaming sales pipeline I built for an e-commerce startup.
>
> The problem: different teams were pulling the same daily CSV files and calculating revenue differently, so Monday's revenue number was different depending on who you asked.
>
> My solution: a local-first data engineering pipeline that ingests those CSVs, detects data-quality issues automatically, cleans and models the data into a DuckDB warehouse, and serves one trusted revenue number through a Streamlit dashboard — with full transparency into why that number is trustworthy."

---

## 0:30 – 1:15 | Show the Dataset and File Discovery

**Show:** The `Data for sales/` folder in the file explorer.

> "The source data is 30 daily CSV files for March 2025, dropped into this folder by the e-commerce platform. Each file is named `sales_YYYY-MM-DD.csv`.
>
> The first thing the pipeline does is discover files. Let me show you `pipeline/discover_files.py`."

**Open** `pipeline/discover_files.py`. Point to:
- `discover_sales_files()` — uses `pathlib.Path.rglob()` so it works on paths with spaces
- `_is_late_arrival_path()` — detects files in `late_arrivals/` subfolders
- `find_missing_dates()` — compares found dates to the full March 2025 expected set

> "Notice I'm using `pathlib.Path` throughout — no string concatenation — so the folder name with spaces works correctly on every OS.
>
> I also found a real data quality issue while building this: `sales_2025-03-15.csv` actually contains March 14 order timestamps. That gets caught automatically by the date mismatch check."

---

## 1:15 – 2:15 | Run the Pipeline

**Run in terminal:**

```bash
python -m pipeline.run_pipeline --dataset-path "Data for sales"
```

**Watch the output together. Point to:**

> "Step 1: file discovery. Step 2: ingestion — every row gets source_file, business_date, and ingestion timestamp added.
>
> Step 3 is where data-quality checks run — I have five families: schema drift, duplicates, freshness, null spikes, and business rules. Step 4 transforms the data — types are cast, strings normalised, duplicates removed, and revenue calculated.
>
> The terminal summary at the end gives the CFO the key numbers at a glance: raw rows, clean rows, duplicate rows removed, DQ issues, and the total net revenue."

**Point to the summary block in the terminal.**

> "The pipeline is fully idempotent — I can run it 10 times and always get the same result. That matters in production."

---

## 2:15 – 3:30 | Open the Streamlit Dashboard

**Run:**

```bash
streamlit run app/dashboard.py
```

**Walk through the dashboard in order:**

**Step 1 — KPI Cards (top of page)**

> "The six KPI cards give the CFO the headline numbers at a glance: total net revenue, gross revenue, total orders, unique customers, average order value, and a data quality status badge — green, yellow, or red.
>
> Directly below is a pipeline audit row: raw rows ingested, duplicate orders removed, invalid rows dropped, clean rows in the fact table, and the dollar value of double-counting that was prevented by deduplication."

*(Point to KPI row and audit row)*

**Step 2 — Daily Revenue Trend**

> "The revenue trend shows gross vs net revenue as two lines with the discount gap shaded. Hover over any date to see the exact net revenue, orders count, and average order value.
>
> Below the line chart is a daily order volume bar — you can immediately spot outlier dates."

*(Point to the chart, hover over a date)*

**Step 3 — Top 10 Products**

> "The horizontal bar chart shows which products drive revenue, colour-coded by category. Hover for units sold and order count. This answers 'what moved the number?' in one view."

*(Point to products chart)*

**Step 4 — Revenue by Region and Category**

> "Region bars on the left, category donut on the right — these give the CFO geographic and product-mix context for the revenue number."

*(Point to region and category charts)*

---

## 3:30 – 4:30 | Show the DQ Command Center

**Scroll to "Data Quality Command Center".**

> "This is the transparency layer. The eight summary cards at the top show critical issues, warnings, passed checks, duplicate count, missing/late files, schema drift issues, and null spike count — all at a glance.
>
> Below that is a filterable issues table. I can filter by severity, check type, or business date. Critical rows are highlighted red, warnings yellow.
>
> Let me open the explanation panel."

*(Expand "What each issue type means")*

> "For every issue type — duplicates, late files, schema drift, null spikes, business rule failures — there's a plain-English explanation of what happened and what the revenue impact is.
>
> The DQ report is also written to disk as JSON and CSV so it can be emailed as an audit trail."

*(Point to the issues table, filter for 'critical')*

> "You can see the critical schema drift for `sales_2025-03-22.csv` where `product_name` was missing, and the critical null spike for `sales_2025-03-26.csv`. Both are flagged with the affected rows count."

---

## 4:30 – 5:30 | CFO Debug View

**Scroll to "If Monday's Number Changed by 3%, Start Here".**

> "This is the feature I'm most proud of. Pick any business date and the view shows: net revenue, gross revenue, orders, unique customers, average order value, and exactly how many rows were removed before the calculation.
>
> Below that is a source file table with an 'Arrival Status' column — I can see instantly whether any file for this date arrived late."

*(Select `2025-03-15`)*

> "For March 15, the rows-removed count is non-zero, and in the DQ issues panel below, you can see the date mismatch warning — this file actually contains March 14 data. We still count those orders because the data is valid, but it's flagged so the CFO understands the context."

*(Select `2025-03-26`)*

> "For March 26, the null spike on `unit_price` caused rows to be dropped — you can see that in the Rows Removed metric and the DQ issues table.
>
> At the bottom there's a formula verification table — I query the top 5 rows and recompute `net = qty × unit_price × (1 − discount_pct)` live, showing a 'formula matches' column so the CFO can see the arithmetic is correct."

> "If someone says 'the revenue changed by 3%', this view is where the investigation starts: check the arrival status, the duplicate count, the schema/null issues. Everything is here in one place."

*(Point to the plain-English investigation guide at the bottom of the section)*

**Step 5 — Data Lineage**

> "The data lineage section shows the full pipeline path from CSV files through to the dashboard. The key message: the dashboard never reads raw files — it reads from modelled DuckDB tables that were built after validation and cleaning."

---

## Closing

> "To summarise: one pipeline, one warehouse, one revenue number. The DQ checks run automatically on every ingest, the reports are saved for auditing, and the CFO can investigate any anomaly in under 10 minutes without needing to ask an engineer.
>
> Happy to go deeper on any part of it."

---

## Appendix: Commands to Run During Demo

```bash
# Run pipeline
python -m pipeline.run_pipeline --dataset-path "Data for sales"

# Open dashboard
streamlit run app/dashboard.py

# Run tests
pytest tests/ -v

# Lint check
ruff check .
```
