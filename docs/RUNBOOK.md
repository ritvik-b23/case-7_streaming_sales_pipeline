# Runbook — Streaming Sales Pipeline

## How to Run Locally

### First-time setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Run the pipeline

```bash
python -m pipeline.run_pipeline --dataset-path "Data for sales"
```

### Open the dashboard

```bash
streamlit run app/dashboard.py
```

The dashboard opens at `http://localhost:8501` by default.

---

## How to Refresh Data

When new CSV files are added to `Data for sales/`, rerun the pipeline:

```bash
python -m pipeline.run_pipeline --dataset-path "Data for sales"
```

The pipeline is **idempotent** — it drops and recreates all tables on each run. There is no risk of double-counting if you run it multiple times.

After the pipeline completes, click **Refresh** in the Streamlit sidebar to reload the dashboard.

---

## How to Handle Missing Files

If a file is missing for an expected March 2025 date, the pipeline will:
1. Continue without error
2. Report the missing date in the terminal summary
3. Record a `freshness_check` warning in the DQ report

**To add a missing file:**
1. Place the CSV in `Data for sales/` with the correct filename (`sales_YYYY-MM-DD.csv`)
2. Rerun the pipeline

For files that arrive late (after the original expected date), place them in `Data for sales/late_arrivals/`. They will be flagged as `is_late_arrival = True` in the warehouse.

---

## How to Handle Schema Drift

If a file has unexpected columns or is missing required columns:

1. The pipeline detects this in `quality_checks.py` (schema check)
2. Critical: missing required columns → affected rows are excluded from `fact_sales_orders`
3. Warning: extra columns → extra columns are ignored

**To investigate:**

```bash
cat data/dq_reports/latest_dq_issues.csv | grep schema_check
```

Or open the dashboard → Data Quality Status → filter by `check_name = schema_check`.

**To fix:** Coordinate with the source team to restore the expected schema. Rerun the pipeline after the file is corrected.

---

## How to Handle Null Spikes

If a null spike is detected for a column in a specific file:

1. Check the DQ report: `data/dq_reports/latest_dq_issues.csv`
2. Open the suspect file and verify the null pattern
3. Determine if the nulls are real (product IDs not yet assigned) or a delivery error

Null rows for critical columns (`order_id`, `qty`, `unit_price`) are dropped during transformation. Null rows for non-critical columns (`product_name`, `category`) are kept.

---

## How to Rerun Safely

The pipeline can be rerun any number of times. Each run:
- Drops and recreates `raw_sales_orders` and `fact_sales_orders`
- Overwrites `data/dq_reports/latest_dq_report.json` and `latest_dq_issues.csv`
- Rebuilds all mart views

There is no state between runs. Running twice produces the same result.

---

## Where Reports Are Stored

| Report | Location |
|---|---|
| DQ summary (JSON) | `data/dq_reports/latest_dq_report.json` |
| DQ issues (CSV) | `data/dq_reports/latest_dq_issues.csv` |
| DuckDB warehouse | `data/warehouse/sales.duckdb` |

---

## Common Failure Modes and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: Dataset folder not found` | Wrong path or folder doesn't exist | Check that `Data for sales/` exists at the project root; use `--dataset-path` to specify the path |
| `ModuleNotFoundError: No module named 'duckdb'` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `streamlit: command not found` | Streamlit not installed or venv not activated | Activate the virtual environment and run `pip install -r requirements.txt` |
| Dashboard shows "Warehouse not found" | Pipeline hasn't been run yet | Run `python -m pipeline.run_pipeline --dataset-path "Data for sales"` |
| `pytest` fails with import errors | Running from wrong directory or venv not activated | Run `pytest` from the project root with the venv activated |
| Revenue looks wrong | Duplicate rows not yet removed, or null values defaulting | Check `data/dq_reports/latest_dq_issues.csv` for duplicate or null issues |
| `ruff check .` reports errors | Code style violations | Run `ruff check . --fix` to auto-fix safe violations |
