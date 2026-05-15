"""Tests for pipeline.transform."""

from __future__ import annotations

from datetime import date

import pandas as pd

from pipeline.transform import _deduplicate, _remove_invalid_rows, transform


def _make_raw(rows: list[dict]) -> pd.DataFrame:
    """Build a raw-style DataFrame with required metadata columns."""
    for r in rows:
        r.setdefault("source_file", "sales_2025-03-01.csv")
        r.setdefault("business_date", date(2025, 3, 1))
        r.setdefault("ingested_at", "2025-03-01T00:00:00+00:00")
        r.setdefault("is_late_arrival", False)
    return pd.DataFrame(rows)


def _valid_row(**overrides) -> dict:
    base = {
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
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_keeps_first_on_duplicate_order_id(self):
        import pandas as pd
        rows = [
            {"order_id": "ORD001", "unit_price": 10.0},
            {"order_id": "ORD001", "unit_price": 20.0},
        ]
        df = pd.DataFrame(rows)
        clean, removed = _deduplicate(df)
        assert len(clean) == 1
        assert removed == 1
        assert clean.iloc[0]["unit_price"] == 10.0  # first row kept

    def test_no_removal_when_unique(self):
        rows = [{"order_id": "ORD001"}, {"order_id": "ORD002"}]
        df = pd.DataFrame(rows)
        clean, removed = _deduplicate(df)
        assert len(clean) == 2
        assert removed == 0


# ---------------------------------------------------------------------------
# Invalid row removal
# ---------------------------------------------------------------------------

class TestRemoveInvalidRows:
    def test_removes_null_order_id(self):
        import pandas as pd
        df = pd.DataFrame([
            {"order_id": None, "order_timestamp": pd.Timestamp("2025-03-01"), "customer_id": "C1",
             "product_id": "P1", "qty": 1.0, "unit_price": 5.0, "discount_pct": 0.0},
            {"order_id": "ORD1", "order_timestamp": pd.Timestamp("2025-03-01"), "customer_id": "C1",
             "product_id": "P1", "qty": 1.0, "unit_price": 5.0, "discount_pct": 0.0},
        ])
        clean, dropped = _remove_invalid_rows(df)
        assert len(clean) == 1
        assert dropped == 1

    def test_removes_zero_qty(self):
        import pandas as pd
        df = pd.DataFrame([
            {"order_id": "ORD1", "order_timestamp": pd.Timestamp("2025-03-01"), "customer_id": "C1",
             "product_id": "P1", "qty": 0.0, "unit_price": 5.0, "discount_pct": 0.0},
        ])
        clean, dropped = _remove_invalid_rows(df)
        assert len(clean) == 0

    def test_removes_negative_price(self):
        import pandas as pd
        df = pd.DataFrame([
            {"order_id": "ORD1", "order_timestamp": pd.Timestamp("2025-03-01"), "customer_id": "C1",
             "product_id": "P1", "qty": 1.0, "unit_price": -1.0, "discount_pct": 0.0},
        ])
        clean, dropped = _remove_invalid_rows(df)
        assert len(clean) == 0


# ---------------------------------------------------------------------------
# Full transform
# ---------------------------------------------------------------------------

class TestTransform:
    def test_basic_transform_produces_revenue_columns(self):
        raw = _make_raw([_valid_row()])
        fact, stats = transform(raw)
        assert "gross_revenue" in fact.columns
        assert "discount_amount" in fact.columns
        assert "net_revenue" in fact.columns

    def test_dedup_removes_duplicate_order_ids(self):
        raw = _make_raw([
            _valid_row(order_id="ORD001"),
            _valid_row(order_id="ORD001"),
            _valid_row(order_id="ORD002"),
        ])
        fact, stats = transform(raw)
        assert len(fact) == 2
        assert stats["duplicate_rows_removed"] == 1

    def test_string_normalisation(self):
        raw = _make_raw([_valid_row(region="  north  ", category="  ELECTRONICS  ")])
        fact, stats = transform(raw)
        assert fact.iloc[0]["region"] == "North"
        assert fact.iloc[0]["category"] == "Electronics"

    def test_invalid_rows_dropped(self):
        raw = _make_raw([
            _valid_row(order_id="ORD001"),
            _valid_row(order_id="ORD002", qty="-1"),   # invalid qty
            _valid_row(order_id="ORD003", unit_price="-5"),  # invalid price
        ])
        fact, stats = transform(raw)
        assert len(fact) == 1
        assert stats["invalid_rows_dropped"] == 2

    def test_stats_match_actual_output(self):
        raw = _make_raw([_valid_row(order_id=f"ORD{i:03d}") for i in range(5)])
        fact, stats = transform(raw)
        assert stats["clean_rows"] == len(fact)
        assert stats["raw_rows"] == 5

    def test_empty_input_returns_empty(self):
        import pandas as pd
        fact, stats = transform(pd.DataFrame())
        assert fact.empty
