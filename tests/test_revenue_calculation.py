"""Tests for revenue calculation correctness.

Ensures the formula:
    gross_revenue  = qty * unit_price
    discount_amount = gross_revenue * discount_pct
    net_revenue    = gross_revenue - discount_amount

is applied consistently everywhere.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.transform import _calculate_revenue, transform


def _fact_row(**overrides) -> dict:
    base = {
        "order_id": "ORD001",
        "order_timestamp": "2025-03-01T10:00:00",
        "customer_id": "C001",
        "product_id": "P001",
        "product_name": "Widget",
        "category": "Electronics",
        "qty": "3",
        "unit_price": "20.0",
        "discount_pct": "0.1",
        "region": "North",
        "source_file": "sales_2025-03-01.csv",
        "business_date": date(2025, 3, 1),
        "ingested_at": "2025-03-01T00:00:00+00:00",
        "is_late_arrival": False,
    }
    base.update(overrides)
    return base


class TestRevenueFormula:
    def test_gross_revenue_correct(self):
        df = pd.DataFrame([{"qty": 3.0, "unit_price": 20.0, "discount_pct": 0.1}])
        result = _calculate_revenue(df)
        assert result.iloc[0]["gross_revenue"] == pytest.approx(60.0)

    def test_discount_amount_correct(self):
        df = pd.DataFrame([{"qty": 3.0, "unit_price": 20.0, "discount_pct": 0.1}])
        result = _calculate_revenue(df)
        assert result.iloc[0]["discount_amount"] == pytest.approx(6.0)

    def test_net_revenue_correct(self):
        df = pd.DataFrame([{"qty": 3.0, "unit_price": 20.0, "discount_pct": 0.1}])
        result = _calculate_revenue(df)
        assert result.iloc[0]["net_revenue"] == pytest.approx(54.0)

    def test_zero_discount(self):
        df = pd.DataFrame([{"qty": 5.0, "unit_price": 10.0, "discount_pct": 0.0}])
        result = _calculate_revenue(df)
        assert result.iloc[0]["gross_revenue"] == pytest.approx(50.0)
        assert result.iloc[0]["discount_amount"] == pytest.approx(0.0)
        assert result.iloc[0]["net_revenue"] == pytest.approx(50.0)

    def test_full_discount(self):
        """discount_pct=1.0 should result in net_revenue=0."""
        df = pd.DataFrame([{"qty": 2.0, "unit_price": 15.0, "discount_pct": 1.0}])
        result = _calculate_revenue(df)
        assert result.iloc[0]["net_revenue"] == pytest.approx(0.0)

    def test_transform_produces_correct_revenue(self):
        raw = pd.DataFrame([_fact_row(qty="4", unit_price="25.0", discount_pct="0.2")])
        fact, _ = transform(raw)
        row = fact.iloc[0]
        assert row["gross_revenue"] == pytest.approx(100.0)
        assert row["discount_amount"] == pytest.approx(20.0)
        assert row["net_revenue"] == pytest.approx(80.0)

    def test_revenue_consistent_across_multiple_rows(self):
        """Sum of net_revenue must equal sum of individual calculations."""
        rows = [
            _fact_row(order_id=f"ORD{i:03d}", qty=str(i + 1), unit_price="10.0", discount_pct="0.05")
            for i in range(10)
        ]
        raw = pd.DataFrame(rows)
        fact, stats = transform(raw)

        expected_net = sum(
            (i + 1) * 10.0 * (1 - 0.05) for i in range(10)
        )
        assert stats["total_net_revenue"] == pytest.approx(expected_net, rel=1e-4)
