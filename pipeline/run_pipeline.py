"""Pipeline entry point.

Usage:
    python -m pipeline.run_pipeline
    python -m pipeline.run_pipeline --dataset-path "Data for sales"
    python -m pipeline.run_pipeline --dataset-path "Data for sales" --warehouse-path data/warehouse/sales.duckdb
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config.settings import DATASET_PATH, WAREHOUSE_PATH
from pipeline.discover_files import discover_sales_files, find_missing_dates
from pipeline.ingest import ingest_files
from pipeline.quality_checks import run_all_checks, save_dq_reports
from pipeline.transform import transform
from pipeline.warehouse import build_warehouse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Case 7 — Streaming Sales Pipeline"
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=None,
        help='Path to the folder containing sales CSV files (default: "Data for sales")',
    )
    parser.add_argument(
        "--warehouse-path",
        type=Path,
        default=None,
        help="Path to the DuckDB warehouse file (default: data/warehouse/sales.duckdb)",
    )
    return parser.parse_args()


def _print_summary(
    file_records,
    missing_dates,
    failed_files,
    transform_stats,
    dq_summary,
    warehouse_path: Path,
    json_path: Path,
) -> None:
    late_count = sum(1 for r in file_records if r["is_late_arrival"])
    sep = "─" * 52

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║      Case 7 · Streaming Sales Pipeline — Summary      ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(sep)
    print(f"  Files discovered         : {len(file_records)}")
    print(f"  Late-arriving files      : {late_count}")
    print(f"  Missing expected dates   : {len(missing_dates)}")
    if missing_dates:
        print(f"    → {[str(d) for d in missing_dates]}")
    if failed_files:
        print(f"  Files failed to read     : {len(failed_files)}")
        for f in failed_files:
            print(f"    → {f}")
    print(sep)
    print(f"  Raw rows ingested        : {transform_stats.get('raw_rows', 0):,}")
    print(f"  Invalid rows dropped     : {transform_stats.get('invalid_rows_dropped', 0):,}")
    print(f"  Duplicate rows removed   : {transform_stats.get('duplicate_rows_removed', 0):,}")
    print(f"  Clean rows (fact table)  : {transform_stats.get('clean_rows', 0):,}")
    print(sep)
    print(f"  Critical DQ issues       : {dq_summary.get('critical_issues', 0)}")
    print(f"  Warning DQ issues        : {dq_summary.get('warning_issues', 0)}")
    print(f"  Overall DQ status        : {dq_summary.get('overall_status', 'unknown').upper()}")
    print(sep)
    print(f"  Total net revenue        : ${transform_stats.get('total_net_revenue', 0):,.2f}")
    print(sep)
    print(f"  Warehouse               : {warehouse_path}")
    print(f"  DQ report               : {json_path}")
    print()


def run(dataset_path: Path, warehouse_path: Path) -> None:
    """Execute the full pipeline."""
    print(f"\n[1/6] Discovering files in: {dataset_path}")
    file_records = discover_sales_files(dataset_path)
    missing_dates = find_missing_dates(file_records)
    print(f"      Found {len(file_records)} files, {len(missing_dates)} missing dates.")

    print("[2/6] Ingesting CSV files …")
    raw_df, failed_files = ingest_files(file_records)
    print(f"      Ingested {len(raw_df):,} raw rows.")

    print("[3/6] Running data-quality checks …")
    dq_summary, issues_df = run_all_checks(raw_df, file_records, missing_dates)
    json_path, csv_path = save_dq_reports(dq_summary, issues_df)
    print(
        f"      Critical: {dq_summary['critical_issues']}  "
        f"Warnings: {dq_summary['warning_issues']}  "
        f"Status: {dq_summary['overall_status'].upper()}"
    )

    print("[4/6] Transforming data …")
    fact_df, transform_stats = transform(raw_df)
    print(f"      Clean rows: {transform_stats.get('clean_rows', 0):,}  "
          f"Net revenue: ${transform_stats.get('total_net_revenue', 0):,.2f}")

    print("[5/6] Writing warehouse …")
    conn = build_warehouse(fact_df, issues_df, raw_df, warehouse_path)
    conn.close()
    print(f"      Warehouse written: {warehouse_path}")

    print("[6/6] Done.\n")

    _print_summary(
        file_records,
        missing_dates,
        failed_files,
        transform_stats,
        dq_summary,
        warehouse_path,
        json_path,
    )


def main() -> None:
    args = _parse_args()

    dataset_path = args.dataset_path if args.dataset_path else DATASET_PATH
    warehouse_path = args.warehouse_path if args.warehouse_path else WAREHOUSE_PATH

    # Resolve relative paths from cwd so the CLI works from any directory
    if not dataset_path.is_absolute():
        dataset_path = Path.cwd() / dataset_path
    if not warehouse_path.is_absolute():
        warehouse_path = Path.cwd() / warehouse_path

    try:
        run(dataset_path, warehouse_path)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
