"""Data-quality checks for the raw sales DataFrame.

Five check families:
  A. Schema check        — missing / extra columns per file
  B. Duplicate check     — duplicate order_id values
  C. Freshness check     — missing or late-arriving dates
  D. Null-spike check    — per-file null % vs global median
  E. Business-rule check — qty, unit_price, discount_pct, order_id, timestamps

Outputs:
  - summary dict
  - issues DataFrame
  - JSON report  → data/dq_reports/latest_dq_report.json
  - CSV report   → data/dq_reports/latest_dq_issues.csv
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from config.settings import (
    CRITICAL_COLUMNS,
    DQ_REPORTS_DIR,
    EXPECTED_COLUMNS,
    NULL_SPIKE_ABSOLUTE_THRESHOLD,
    NULL_SPIKE_MULTIPLIER,
)
from pipeline.discover_files import FileRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Issue record helpers
# ---------------------------------------------------------------------------

def _issue(
    check_name: str,
    severity: str,
    status: str,
    source_file: str = "",
    business_date: str = "",
    affected_column: str = "",
    affected_rows: int = 0,
    message: str = "",
    run_id: str = "",
    run_timestamp: str = "",
) -> dict:
    return {
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "check_name": check_name,
        "severity": severity,
        "status": status,
        "source_file": source_file,
        "business_date": str(business_date),
        "affected_column": affected_column,
        "affected_rows": affected_rows,
        "message": message,
    }


# ---------------------------------------------------------------------------
# A. Schema check
# ---------------------------------------------------------------------------

def check_schema(raw_df: pd.DataFrame, run_id: str, run_ts: str) -> list[dict]:
    issues: list[dict] = []
    expected = set(EXPECTED_COLUMNS)

    for src_file, group in raw_df.groupby("source_file"):
        actual_cols = set(group.columns) - {
            "source_file", "business_date", "ingested_at",
            "is_late_arrival", "row_number_in_file",
        }
        missing = expected - actual_cols
        # When multiple files are concatenated, a column absent in one file is
        # padded with NaN.  Treat all-null expected columns as effectively missing.
        all_null_cols = {
            col for col in expected
            if col in group.columns and group[col].isna().all()
        }
        missing = missing | all_null_cols
        extra = actual_cols - expected - all_null_cols

        if missing:
            issues.append(_issue(
                check_name="schema_check",
                severity="critical",
                status="fail",
                source_file=src_file,
                business_date=str(group["business_date"].iloc[0]),
                affected_column=", ".join(sorted(missing)),
                affected_rows=len(group),
                message=f"Missing required columns: {sorted(missing)}",
                run_id=run_id,
                run_timestamp=run_ts,
            ))
        if extra:
            issues.append(_issue(
                check_name="schema_check",
                severity="warning",
                status="fail",
                source_file=src_file,
                business_date=str(group["business_date"].iloc[0]),
                affected_column=", ".join(sorted(extra)),
                affected_rows=len(group),
                message=f"Unexpected extra columns: {sorted(extra)}",
                run_id=run_id,
                run_timestamp=run_ts,
            ))

    if not issues:
        issues.append(_issue(
            check_name="schema_check",
            severity="info",
            status="pass",
            message="All files match expected schema.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))
    return issues


# ---------------------------------------------------------------------------
# B. Duplicate check
# ---------------------------------------------------------------------------

def check_duplicates(raw_df: pd.DataFrame, run_id: str, run_ts: str) -> list[dict]:
    issues: list[dict] = []
    if "order_id" not in raw_df.columns:
        return issues

    total = len(raw_df)
    dup_mask = raw_df.duplicated(subset=["order_id"], keep="first")
    dup_count = int(dup_mask.sum())
    dup_rate = dup_count / total if total else 0.0

    if dup_count > 0:
        # Per-file breakdown
        dup_df = raw_df[dup_mask]
        for src_file, grp in dup_df.groupby("source_file"):
            issues.append(_issue(
                check_name="duplicate_check",
                severity="warning",
                status="fail",
                source_file=src_file,
                business_date=str(grp["business_date"].iloc[0]),
                affected_column="order_id",
                affected_rows=len(grp),
                message=(
                    f"{len(grp)} duplicate order_id rows in {src_file} "
                    f"(overall dup rate: {dup_rate:.2%})"
                ),
                run_id=run_id,
                run_timestamp=run_ts,
            ))
    else:
        issues.append(_issue(
            check_name="duplicate_check",
            severity="info",
            status="pass",
            message="No duplicate order_id values found.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))
    return issues


# ---------------------------------------------------------------------------
# C. Freshness / missing-file check
# ---------------------------------------------------------------------------

def check_freshness(
    file_records: list[FileRecord],
    missing_dates: list[date],
    run_id: str,
    run_ts: str,
) -> list[dict]:
    issues: list[dict] = []

    if missing_dates:
        for d in missing_dates:
            issues.append(_issue(
                check_name="freshness_check",
                severity="warning",
                status="fail",
                business_date=str(d),
                affected_rows=0,
                message=f"No sales file found for expected date {d}.",
                run_id=run_id,
                run_timestamp=run_ts,
            ))
    else:
        issues.append(_issue(
            check_name="freshness_check",
            severity="info",
            status="pass",
            message="All expected March 2025 dates have a sales file.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))

    # Late arrivals
    late = [r for r in file_records if r["is_late_arrival"]]
    for r in late:
        issues.append(_issue(
            check_name="freshness_check",
            severity="info",
            status="warn",
            source_file=r["file_name"],
            business_date=str(r["business_date"]),
            affected_rows=0,
            message=f"Late-arrival file detected: {r['file_name']}",
            run_id=run_id,
            run_timestamp=run_ts,
        ))

    return issues


# ---------------------------------------------------------------------------
# D. Null-spike check
# ---------------------------------------------------------------------------

def check_null_spikes(raw_df: pd.DataFrame, run_id: str, run_ts: str) -> list[dict]:
    issues: list[dict] = []
    monitor_cols = [c for c in CRITICAL_COLUMNS if c in raw_df.columns]

    if not monitor_cols or "source_file" not in raw_df.columns:
        return issues

    # Global null % per column across all files (median)
    global_null_pct: dict[str, float] = {}
    for col in monitor_cols:
        per_file = raw_df.groupby("source_file")[col].apply(
            lambda s: s.isna().mean()
        )
        global_null_pct[col] = float(per_file.median())

    for src_file, group in raw_df.groupby("source_file"):
        bdate = str(group["business_date"].iloc[0])
        for col in monitor_cols:
            if col not in group.columns:
                continue
            file_null_pct = float(group[col].isna().mean())
            global_median = global_null_pct.get(col, 0.0)

            spike = file_null_pct > NULL_SPIKE_ABSOLUTE_THRESHOLD or (
                global_median > 0
                and file_null_pct > NULL_SPIKE_MULTIPLIER * global_median
            )
            if spike:
                issues.append(_issue(
                    check_name="null_spike_check",
                    severity="warning",
                    status="fail",
                    source_file=src_file,
                    business_date=bdate,
                    affected_column=col,
                    affected_rows=int(group[col].isna().sum()),
                    message=(
                        f"Null spike in '{col}' for {src_file}: "
                        f"{file_null_pct:.1%} null "
                        f"(global median: {global_median:.1%})"
                    ),
                    run_id=run_id,
                    run_timestamp=run_ts,
                ))

    if not issues:
        issues.append(_issue(
            check_name="null_spike_check",
            severity="info",
            status="pass",
            message="No null spikes detected.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))
    return issues


# ---------------------------------------------------------------------------
# E. Business-rule check
# ---------------------------------------------------------------------------

def check_business_rules(raw_df: pd.DataFrame, run_id: str, run_ts: str) -> list[dict]:
    issues: list[dict] = []

    def _count_violations(mask: pd.Series, col: str, msg_tpl: str, sev: str = "warning"):
        count = int(mask.sum())
        if count == 0:
            return
        for src_file, grp in raw_df[mask].groupby("source_file"):
            issues.append(_issue(
                check_name="business_rule_check",
                severity=sev,
                status="fail",
                source_file=src_file,
                business_date=str(grp["business_date"].iloc[0]),
                affected_column=col,
                affected_rows=len(grp),
                message=msg_tpl.format(count=len(grp), file=src_file),
                run_id=run_id,
                run_timestamp=run_ts,
            ))

    # order_id must not be null
    if "order_id" in raw_df.columns:
        _count_violations(
            raw_df["order_id"].isna(),
            "order_id",
            "{count} rows with null order_id in {file}",
            sev="critical",
        )

    # product_id must not be null
    if "product_id" in raw_df.columns:
        _count_violations(
            raw_df["product_id"].isna(),
            "product_id",
            "{count} rows with null product_id in {file}",
            sev="critical",
        )

    # qty > 0
    if "qty" in raw_df.columns:
        qty_num = pd.to_numeric(raw_df["qty"], errors="coerce")
        _count_violations(
            qty_num.notna() & (qty_num <= 0),
            "qty",
            "{count} rows with qty <= 0 in {file}",
        )

    # unit_price >= 0
    if "unit_price" in raw_df.columns:
        price_num = pd.to_numeric(raw_df["unit_price"], errors="coerce")
        _count_violations(
            price_num.notna() & (price_num < 0),
            "unit_price",
            "{count} rows with unit_price < 0 in {file}",
        )

    # discount_pct between 0 and 1
    if "discount_pct" in raw_df.columns:
        disc_num = pd.to_numeric(raw_df["discount_pct"], errors="coerce")
        _count_violations(
            disc_num.notna() & ((disc_num < 0) | (disc_num > 1)),
            "discount_pct",
            "{count} rows with discount_pct outside [0,1] in {file}",
        )

    # order_timestamp parseable
    if "order_timestamp" in raw_df.columns:
        parsed = pd.to_datetime(raw_df["order_timestamp"], errors="coerce")
        _count_violations(
            raw_df["order_timestamp"].notna() & parsed.isna(),
            "order_timestamp",
            "{count} rows with unparseable order_timestamp in {file}",
        )

    if not issues:
        issues.append(_issue(
            check_name="business_rule_check",
            severity="info",
            status="pass",
            message="All business-rule checks passed.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))
    return issues


# ---------------------------------------------------------------------------
# F. Date-mismatch check (filename date vs actual data timestamps)
# ---------------------------------------------------------------------------

def check_date_mismatch(raw_df: pd.DataFrame, run_id: str, run_ts: str) -> list[dict]:
    """Flag files where the actual order dates differ from the filename date."""
    issues: list[dict] = []
    if "order_timestamp" not in raw_df.columns or "business_date" not in raw_df.columns:
        return issues

    parsed_ts = pd.to_datetime(raw_df["order_timestamp"], errors="coerce")
    actual_dates = parsed_ts.dt.date

    for src_file, group in raw_df.groupby("source_file"):
        filename_date = group["business_date"].iloc[0]
        # Get the unique actual calendar dates from this file's timestamps
        group_actual = actual_dates.loc[group.index].dropna().unique()
        mismatched = [d for d in group_actual if d != filename_date]
        if mismatched:
            issues.append(_issue(
                check_name="date_mismatch_check",
                severity="warning",
                status="fail",
                source_file=src_file,
                business_date=str(filename_date),
                affected_column="order_timestamp",
                affected_rows=int(
                    actual_dates.loc[group.index].isin(mismatched).sum()
                ),
                message=(
                    f"File '{src_file}' (filename date {filename_date}) contains "
                    f"orders dated {sorted(str(d) for d in mismatched)}. "
                    "Possible late-delivery or mis-dated file."
                ),
                run_id=run_id,
                run_timestamp=run_ts,
            ))

    if not issues:
        issues.append(_issue(
            check_name="date_mismatch_check",
            severity="info",
            status="pass",
            message="All files contain orders matching their filename date.",
            run_id=run_id,
            run_timestamp=run_ts,
        ))
    return issues


# ---------------------------------------------------------------------------
# Master runner
# ---------------------------------------------------------------------------

def run_all_checks(
    raw_df: pd.DataFrame,
    file_records: list[FileRecord],
    missing_dates: list[date],
) -> tuple[dict, pd.DataFrame]:
    """Run all DQ checks and return (summary, issues_df)."""
    run_id = str(uuid.uuid4())
    run_ts = datetime.now(timezone.utc).isoformat()

    all_issues: list[dict] = []
    all_issues.extend(check_schema(raw_df, run_id, run_ts))
    all_issues.extend(check_duplicates(raw_df, run_id, run_ts))
    all_issues.extend(check_freshness(file_records, missing_dates, run_id, run_ts))
    all_issues.extend(check_null_spikes(raw_df, run_id, run_ts))
    all_issues.extend(check_business_rules(raw_df, run_id, run_ts))
    all_issues.extend(check_date_mismatch(raw_df, run_id, run_ts))

    issues_df = pd.DataFrame(all_issues)

    fail_issues = issues_df[issues_df["status"].isin(["fail", "warn"])]
    summary = {
        "run_id": run_id,
        "run_timestamp": run_ts,
        "total_checks": len(issues_df),
        "critical_issues": int((fail_issues["severity"] == "critical").sum()),
        "warning_issues": int((fail_issues["severity"] == "warning").sum()),
        "info_issues": int((issues_df["severity"] == "info").sum()),
        "overall_status": (
            "critical" if (fail_issues["severity"] == "critical").any()
            else "warning" if not fail_issues.empty
            else "pass"
        ),
    }
    return summary, issues_df


def save_dq_reports(summary: dict, issues_df: pd.DataFrame) -> tuple[Path, Path]:
    """Write JSON summary and CSV issues to data/dq_reports/."""
    DQ_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = DQ_REPORTS_DIR / "latest_dq_report.json"
    csv_path = DQ_REPORTS_DIR / "latest_dq_issues.csv"

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    issues_df.to_csv(csv_path, index=False)

    logger.info("DQ reports saved: %s, %s", json_path, csv_path)
    return json_path, csv_path
