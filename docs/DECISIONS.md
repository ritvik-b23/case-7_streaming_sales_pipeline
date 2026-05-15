# Decisions Log — Case 7

## Assumptions I made

1. The CFO needs one trusted revenue number, not just charts — because different teams were calculating revenue from the same files and getting different answers.
2. CSVs may arrive late or contain quality issues — so the pipeline treats late-arrival detection and DQ reporting as first-class requirements, not afterthoughts.
3. DuckDB is sufficient as a local analytics warehouse — because the dataset is small, the pipeline is single-process, and a file-based warehouse is trivially portable for a demo.
4. Streamlit is acceptable as the dashboard layer — because the case asks for a runnable dashboard and Streamlit can be started with one command without any server setup.
5. The pipeline should prioritise traceability from dashboard numbers back to source files — so every row in the fact table carries the source filename, business date, and ingestion timestamp.

## Trade-offs

| Choice | Alternative | Why I picked this |
|---|---|---|
| DuckDB (local file) | Postgres / BigQuery | No server, no credentials, single portable file — easy to run and demo locally |
| Streamlit | Metabase / Superset | Pure Python, zero infrastructure, evaluator can run it in one command |
| Plain Python CLI (`run_pipeline.py`) | Airflow / Prefect / Dagster | Orchestrators add significant setup overhead for a single pipeline; a CLI is easier to run, test, and explain |
| Custom `quality_checks.py` | Great Expectations / Soda | GE adds setup overhead; the custom module is transparent, testable, and covers the required check families |
| Local runnable dashboard | Deployed cloud dashboard | Avoids cloud credentials and deployment complexity during a time-boxed submission |

## What I de-scoped and why

- **Incremental ingestion** — not needed for a 30-file static dataset; full reload on each run is fast enough.
- **Historical DQ report retention** — reports are overwritten per run; appending to a history table would be the obvious next step.
- **Alerting / notifications** — out of scope for a local pipeline; a Slack webhook would be the first production addition.
- **User authentication on the dashboard** — not required for a local demo environment.
- **Airflow DAG** — explicitly out of scope per the case requirements.

## What I'd do differently with another day

- Deploy the dashboard to Streamlit Community Cloud or a Hugging Face Space so evaluators don't need to run it locally.
- Add a `pipeline_runs` table to track processed files and enable incremental ingestion on re-runs.
- Append DQ issues to a rolling history table so trends (e.g. growing null spikes) can be visualised over time.
- Add a Slack or email alert triggered when `critical_issues > 0` so the data team acts before the CFO opens the dashboard.
- Parameterise the date range so the pipeline can be run for any month, not only March 2025.
