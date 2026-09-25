"""Test fixtures: fake the Lakebase reference-data seam.

The app reads accounts/products/pricing from Lakebase `cpq_ref` synced tables at
runtime (no static/mock). Tests shouldn't need a live Postgres, so we point the
`lakebase.get_*` read helpers at the same demo_data builders that seed those UC
tables — the values are therefore identical to production, just sourced in-process.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))
sys.path.insert(0, str(ROOT / "src" / "shared"))

from agentic_cpq_demo.demo_data import (  # noqa: E402
    ACCOUNTS,
    PRODUCTS,
    SAMPLE_PROMPTS,
    SOURCE_FRESHNESS,
    build_supplier_price_book_rows,
    build_supplier_segment_pricing_rows,
)
from server import lakebase  # noqa: E402


def _accounts() -> list[dict]:
    return [dict(a) for a in ACCOUNTS]


def _products() -> list[dict]:
    return [dict(p) for p in PRODUCTS]


# Repoint the read layer at the demo_data builders (the UC tables' own source).
lakebase.get_accounts = _accounts
lakebase.get_account = lambda account_id: next((a for a in _accounts() if a["account_id"] == account_id), None)
lakebase.get_products = _products
lakebase.get_product = lambda sku: next((p for p in _products() if p["sku"] == sku), None)
lakebase.get_segment_pricing = build_supplier_segment_pricing_rows
lakebase.get_price_book = build_supplier_price_book_rows
lakebase.get_sample_prompts = lambda: list(SAMPLE_PROMPTS)
lakebase.get_source_freshness = lambda: [dict(r) for r in SOURCE_FRESHNESS]
