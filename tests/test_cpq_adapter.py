from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))

from agentic_cpq_demo.cpq import build_quote_payload


class QuoteAdapterTests(unittest.TestCase):
    def test_quote_payload_is_deterministic(self) -> None:
        line_items = [
            {
                "sku": "EQUIP-CHAIR-500",
                "title": "A-dec 500 Operatory Package",
                "category": "equipment",
                "quantity": 1,
                "unit_price": 24700.0,
                "list_price": 26000.0,
                "recommended_price": 24700.0,
                "supplier_cost": 18460.0,
                "gross_margin_pct": 25.3,
                "approval_required": False,
                "warranty_eligible": True,
            },
            {
                "sku": "SOFT-PRACTICE-12",
                "title": "Cloud Practice Management Growth Bundle",
                "category": "software",
                "quantity": 1,
                "unit_price": 6115.2,
                "list_price": 6240.0,
                "recommended_price": 6115.2,
                "supplier_cost": 1747.2,
                "gross_margin_pct": 71.4,
                "approval_required": False,
                "warranty_eligible": False,
            },
        ]

        first = build_quote_payload(
            order_id="draft-123",
            account_id="acct-riverfront",
            seller_id="seller-demo",
            environment="dev",
            line_items=line_items,
        )
        second = build_quote_payload(
            order_id="draft-123",
            account_id="acct-riverfront",
            seller_id="seller-demo",
            environment="dev",
            line_items=line_items,
        )

        self.assertEqual(first["quote_id"], second["quote_id"])
        self.assertEqual(first["platform"], "Agentic CPQ")
        self.assertEqual(first["sync_status"], "document-ready")
        self.assertEqual(first["totals"]["grand_total"], 30815.2)
        self.assertEqual(first["quote_document"]["pricing_controls"]["approval_status"], "clear")
        self.assertEqual(first["quote_document"]["recommended_addons"][0]["title"], "Equipment Care")
        self.assertEqual(first["quote_document"]["customer_document"]["format"], "PDF")
        self.assertEqual(first["quote_document"]["pipeline"]["status"], "open_quote")
        self.assertEqual(first["quote_document"]["access_controls"]["sso_status"], "ready")
        self.assertEqual(first["quote_document"]["salesforce_order_link"]["target"], "Equipment_Order_Form")
        self.assertEqual(first["quote_document"]["salesforce_order_link"]["activation"], "after_customer_acceptance")
        self.assertEqual(first["quote_document"]["data_flow"][-1]["source"], "Salesforce")

    def test_quote_payload_uses_configurable_approval_threshold_with_default_compatibility(
        self,
    ) -> None:
        line_items = [
            {
                "sku": "EQUIP-TEST-900",
                "title": "Test equipment package",
                "category": "equipment",
                "quantity": 1,
                "unit_price": 90_000.0,
                "approval_required": False,
                "warranty_eligible": False,
            }
        ]
        common = {
            "order_id": "draft-threshold",
            "account_id": "acct-riverfront",
            "seller_id": "seller-demo",
            "environment": "dev",
            "line_items": line_items,
        }

        default_payload = build_quote_payload(**common)
        custom_payload = build_quote_payload(**common, approval_threshold=50_000.0)
        default_controls = default_payload["quote_document"]["pricing_controls"]
        custom_controls = custom_payload["quote_document"]["pricing_controls"]

        self.assertEqual(default_controls["approval_status"], "approval-required")
        self.assertIn("Quote total exceeds $80,000", default_controls["approval_reasons"])
        self.assertEqual(custom_controls["approval_status"], "approval-required")
        self.assertIn("Quote total exceeds $50,000", custom_controls["approval_reasons"])
        self.assertNotIn("Quote total exceeds $80,000", custom_controls["approval_reasons"])


if __name__ == "__main__":
    unittest.main()
