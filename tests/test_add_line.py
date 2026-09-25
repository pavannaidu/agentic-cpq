from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server.databricks_api import build_catalog_line, reprice_catalog_line
from server.redaction import redact_line_items_for_view


class BuildCatalogLineTests(unittest.TestCase):
    def test_prices_a_known_sku(self) -> None:
        line = build_catalog_line("EQUIP-CHAIR-500", quantity=2, account_id="acct-riverfront")
        self.assertEqual(line["sku"], "EQUIP-CHAIR-500")
        self.assertEqual(line["category"], "equipment")
        self.assertEqual(line["quantity"], 2)
        # mid-market: 26000 * (1 - 5%) = 24700; total = 49400
        self.assertEqual(line["unit_price"], 24700.0)
        self.assertEqual(line["total_price"], 49400.0)
        self.assertEqual(line["supplier_cost"], 18460.0)
        self.assertTrue(line["warranty_eligible"])
        # overpay: (20121.40 - 18460.00) * 2 = 3322.80
        self.assertEqual(line["overpay_amount"], 3322.8)
        self.assertGreater(line["gross_margin_pct"], 0)

    def test_unknown_sku_returns_none(self) -> None:
        self.assertIsNone(build_catalog_line("NOPE", quantity=1, account_id="acct-riverfront"))

    def test_reprice_below_floor_triggers_approval(self) -> None:
        # CBCT supplier cost 12580; at list-ish price margin is fine (no approval).
        ok = reprice_catalog_line("IMAG-CBCT-210", unit_price=17575, quantity=1, account_id="acct-riverfront")
        self.assertFalse(ok["approval_required"])  # 28.4% > 24% imaging floor
        # Drop net to a thin margin -> below the 24% imaging floor -> approval fires.
        low = reprice_catalog_line("IMAG-CBCT-210", unit_price=13000, quantity=2, account_id="acct-riverfront")
        self.assertTrue(low["approval_required"])
        self.assertEqual(low["total_price"], 26000.0)
        self.assertLess(low["gross_margin_pct"], 24)
        # Overpay is buy-side: unchanged by the sell-price edit (qty 2).
        self.assertEqual(low["overpay_amount"], 2767.6)

    def test_seller_line_redaction(self) -> None:
        order = {
            "line_items": [
                {"sku": "EQUIP-CHAIR-500", "supplier_cost": 18460.0, "gross_margin_pct": 29.0, "overpay_amount": 3322.8, "legacy_supplier_cost": 20121.4, "correct_supplier_cost": 18460.0}
            ]
        }
        seller = redact_line_items_for_view(order, "seller")
        line = seller["line_items"][0]
        self.assertIsNone(line["supplier_cost"])
        self.assertIsNone(line["gross_margin_pct"])
        self.assertEqual(line["overpay_amount"], 0.0)
        # manager untouched
        mgr = redact_line_items_for_view(order, "manager")
        self.assertEqual(mgr["line_items"][0]["supplier_cost"], 18460.0)


if __name__ == "__main__":
    unittest.main()
