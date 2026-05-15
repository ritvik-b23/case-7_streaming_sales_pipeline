# Case 7: Streaming Sales Pipeline

**Live demo:** Runnable locally with `streamlit run app/dashboard.py`
**Repo:** <ADD_GITHUB_REPO_URL>  
**Demo video:** <ADD_DEMO_VIDEO_LINK>

## What this is

An e-commerce startup had teams pulling the same daily CSV files and calculating revenue differently, so Monday's number was never the same twice. This pipeline ingests those CSVs, runs data-quality checks, and loads a DuckDB warehouse that powers a Streamlit dashboard — giving the CFO one trusted revenue figure with a clear audit trail.

## How to run locally

1. `git clone <ADD_GITHUB_REPO_URL>`
2. `cd case-7_streaming_sales_pipeline`
3. `python -m venv .venv`
4. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - macOS / Linux: `source .venv/bin/activate`
5. `pip install -r requirements.txt`
6. `python -m pipeline.run_pipeline --dataset-path "Data for sales"`
7. `streamlit run app/dashboard.py`
8. Open the Streamlit local URL, usually `http://localhost:8501`

## Stack

- **Python** — single-language stack keeps the pipeline easy to run and test locally.
- **pandas** — straightforward DataFrame operations for ingestion, cleaning, and revenue calculation.
- **DuckDB** — embeds a columnar warehouse in a single file; no server or credentials needed.
- **Streamlit** — turns a Python script into a shareable dashboard with one command.
- **Plotly** — interactive charts for revenue trends and product breakdowns.
- **pytest** — unit tests cover the revenue formula, transforms, and DQ checks.
- **ruff** — fast linter to keep code style consistent.

## What's NOT done

- No cloud scheduler or orchestrator; the pipeline is triggered manually via CLI.
- No production warehouse (BigQuery, Postgres) — DuckDB is local only.
- No automated Slack or email alerts on DQ failures.
- No historical DQ trend storage; reports are overwritten on each run.
- No role-based dashboard access or authentication.

## In production, I would also add

- Scheduled daily ingestion (e.g. cron or Airflow) so the pipeline runs without manual triggering.
- Slack or email alerts when critical DQ issues are detected before the CFO sees the numbers.
- A rolling DQ history table so the team can spot worsening trends over time.
- A production warehouse (BigQuery or Postgres) for multi-user access and longer retention.
- Role-based access and an audit log so every number can be traced to its source.