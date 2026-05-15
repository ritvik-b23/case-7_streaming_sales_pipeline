"""Tests for pipeline.quality_checks."""

from __future__ import annotations

from datetime import date

import pandas as pd

from pipeline.quality_checks import (
    check_business_rules,
    check_date_mismatch,
    check_duplicates,
    check_null_spikes,
    check_schema,
)

# Shared run identifiers for tests
RUN_ID = "test-run"
RUN_TS = "2025-03-01T00:00:00+00:00"


def _base_df(rows: list[dict] | None = None) -> pd.DataFrame:
    """Build a minimal valid raw DataFrame for testing."""
    default = [
        {
            "order_id": "ORD001",
            "order_timestamp": "2025-03-01T10:00:00",
            "customer_id": "C001",
            "product_id": "P001",
            "product_name": "Widget",
            "category": "Electronics",
            "qty": "2",
            "unit_price": "10.0",
            "discount_pct": "0.1",
            "region": "North",
            "source_file": "sales_2025-03-01.csv",
            "business_date": date(2025, 3, 1),
        }
    ]
    data = rows if rows is not None else default
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Schema check
# ---------------------------------------------------------------------------

class TestCheckSchema:
    def test_pass_when_all_columns_present(self):
        df = _base_df()
        issues = check_schema(df, RUN_ID, RUN_TS)
        assert any(i["status"] == "pass" for i in issues)

    def test_critical_when_required_column_missing(self):
        df = _base_df()
        df = df.drop(columns=["order_id"])
        issues = check_schema(df, RUN_ID, RUN_TS)
        crits = [i for i in issues if i["severity"] == "critical"]
        assert len(crits) > 0
        assert "order_id" in crits[0]["affected_column"]

    def test_warning_when_extra_column_present(self):
        df = _base_df()
        df["extra_col"] = "surprise"
        issues = check_schema(df, RUN_ID, RUN_TS)
        warns = [i for i in issues if i["severity"] == "warning" and i["check_name"] == "schema_check"]
        assert len(warns) > 0

    def test_per_file_schema_drift_detected(self):
        """Two files: one good, one missing a column."""
        row1 = _base_df()[_base_df().columns.tolist()].copy()
        row2 = row1.copy()
        row2["source_file"] = "sales_2025-03-02.csv"
        row2 = row2.drop(columns=["product_name"])
        df = pd.concat([row1, row2], ignore_index=True)
        issues = check_schema(df, RUN_ID, RUN_TS)
        crits = [i for i in issues if i["severity"] == "critical"]
        assert any("sales_2025-03-02.csv" in i["source_file"] for i in crits)


# ---------------------------------------------------------------------------
# Duplicate check
# ---------------------------------------------------------------------------

class TestCheckDuplicates:
    def test_pass_when_no_duplicates(self):
        df = _base_df()
        issues = check_duplicates(df, RUN_ID, RUN_TS)
        assert any(i["status"] == "pass" for i in issues)

    def test_detects_duplicate_order_id(self):
        row = _base_df().iloc[0].to_dict()
        df = pd.DataFrame([row, row])  # exact duplicate
        issues = check_duplicates(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail"]
        assert len(fails) > 0
        assert fails[0]["affected_rows"] == 1  # one dup (first kept)

    def test_cross_file_duplicate_detected(self):
        row = _base_df().iloc[0].to_dict()
        row2 = dict(row)
        row2["source_file"] = "sales_2025-03-02.csv"
        df = pd.DataFrame([row, row2])
        issues = check_duplicates(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail"]
        assert len(fails) > 0


# ---------------------------------------------------------------------------
# Null spike check
# ---------------------------------------------------------------------------

class TestCheckNullSpikes:
    def test_no_spike_on_clean_data(self):
        rows = [_base_df().iloc[0].to_dict() for _ in range(20)]
        df = pd.DataFrame(rows)
        issues = check_null_spikes(df, RUN_ID, RUN_TS)
        assert any(i["status"] == "pass" for i in issues)

    def test_spike_detected_when_null_exceeds_threshold(self):
        """Create a file where >20% of order_id is null — should trigger absolute spike."""
        good_rows = []
        for i in range(10):
            r = _base_df().iloc[0].to_dict()
            r["order_id"] = f"ORD{i:03d}"
            r["source_file"] = "sales_2025-03-02.csv"
            good_rows.append(r)

        bad_rows = []
        for i in range(10):
            r = _base_df().iloc[0].to_dict()
            r["order_id"] = None  # null
            r["source_file"] = "sales_2025-03-03.csv"
            bad_rows.append(r)

        df = pd.DataFrame(good_rows + bad_rows)
        issues = check_null_spikes(df, RUN_ID, RUN_TS)
        spikes = [i for i in issues if i["status"] == "fail"]
        assert len(spikes) > 0


# ---------------------------------------------------------------------------
# Business rules check
# ---------------------------------------------------------------------------

class TestCheckBusinessRules:
    def test_pass_on_valid_data(self):
        df = _base_df()
        issues = check_business_rules(df, RUN_ID, RUN_TS)
        assert any(i["status"] == "pass" for i in issues)

    def test_invalid_qty_flagged(self):
        df = _base_df()
        df.loc[0, "qty"] = "0"
        issues = check_business_rules(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail" and i["affected_column"] == "qty"]
        assert len(fails) > 0

    def test_negative_price_flagged(self):
        df = _base_df()
        df.loc[0, "unit_price"] = "-5.0"
        issues = check_business_rules(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail" and i["affected_column"] == "unit_price"]
        assert len(fails) > 0

    def test_discount_out_of_range_flagged(self):
        df = _base_df()
        df.loc[0, "discount_pct"] = "1.5"  # > 1
        issues = check_business_rules(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail" and i["affected_column"] == "discount_pct"]
        assert len(fails) > 0

    def test_null_order_id_flagged_as_critical(self):
        df = _base_df()
        df.loc[0, "order_id"] = None
        issues = check_business_rules(df, RUN_ID, RUN_TS)
        crits = [i for i in issues if i["severity"] == "critical" and i["affected_column"] == "order_id"]
        assert len(crits) > 0


# ---------------------------------------------------------------------------
# Date mismatch check
# ---------------------------------------------------------------------------

class TestCheckDateMismatch:
    def test_pass_when_dates_match(self):
        df = _base_df()
        issues = check_date_mismatch(df, RUN_ID, RUN_TS)
        assert any(i["status"] == "pass" for i in issues)

    def test_detects_mismatch(self):
        """File named 2025-03-15 but contains 2025-03-14 timestamps."""
        df = _base_df([
            {
                "order_id": "ORD001",
                "order_timestamp": "2025-03-14T10:00:00",  # March 14
                "customer_id": "C001",
                "product_id": "P001",
                "product_name": "Widget",
                "category": "Electronics",
                "qty": "1",
                "unit_price": "10.0",
                "discount_pct": "0.0",
                "region": "North",
                "source_file": "sales_2025-03-15.csv",
                "business_date": date(2025, 3, 15),  # filename says March 15
            }
        ])
        issues = check_date_mismatch(df, RUN_ID, RUN_TS)
        fails = [i for i in issues if i["status"] == "fail"]
        assert len(fails) > 0
        assert "2025-03-14" in fails[0]["message"]
