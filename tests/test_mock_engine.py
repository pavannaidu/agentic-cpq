from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))

from agentic_cpq_demo.demo_data import overpay_runrate_projection, overpayment_for_line
from agentic_cpq_demo.mock_engine import build_cart_recommendation


class OverpaymentTests(unittest.TestCase):
    def test_overpayment_for_line_catches_legacy_delta(self) -> None:
        result = overpayment_for_line("EQUIP-CHAIR-500", 2)
        # negotiated 18460.00, legacy 18460*1.09 = 20121.40 -> delta 1661.40 * 2
        self.assertEqual(result["correct_cost"], 18460.0)
        self.assertEqual(result["legacy_cost"], 20121.4)
        self.assertEqual(result["overpay_amount"], 3322.8)

    def test_overpayment_zero_for_software(self) -> None:
        self.assertEqual(overpayment_for_line("SOFT-PRACTICE-12", 1)["overpay_amount"], 0.0)

    def test_unknown_sku_is_safe(self) -> None:
        self.assertEqual(overpayment_for_line("NOPE", 5)["overpay_amount"], 0.0)

    def test_runrate_projection_is_material_and_labeled(self) -> None:
        projection = overpay_runrate_projection()
        self.assertTrue(projection["is_projection"])
        self.assertGreater(projection["annualized_overpay_prevented"], 1_000_000)
        self.assertTrue(projection["by_sku"])


class MockEngineTests(unittest.TestCase):
    def test_mock_quote_surfaces_overpay_total(self) -> None:
        recommendation = build_cart_recommendation(
            "Build a two-operatory expansion bundle under $80000.",
            account_id="acct-riverfront",
        )
        self.assertGreater(recommendation["overpay_prevented_total"], 0)
        signals = {s["label"]: s["status"] for s in recommendation["intelligence_signals"]}
        self.assertIn("Saved", signals["Overpay"])

    def test_operatory_prompt_returns_core_categories(self) -> None:
        recommendation = build_cart_recommendation(
            "Build a two-operatory expansion bundle under $80000.",
            account_id="acct-riverfront",
        )
        categories = {item["category"] for item in recommendation["items"]}
        self.assertIn("equipment", categories)
        self.assertIn("software", categories)
        self.assertTrue(recommendation["pricing_controls"])
        self.assertTrue(recommendation["approval_path"])
        self.assertIn("source_freshness", recommendation)
        self.assertTrue(recommendation["quote_readiness"])
        self.assertTrue(recommendation["requirements_coverage"])
        self.assertTrue(recommendation["workflow_steps"])
        self.assertTrue(recommendation["current_state_risks"])
        self.assertTrue(recommendation["source_lineage"])
        self.assertIn("Guided Quoting", {item["label"] for item in recommendation["requirements_coverage"]})
        self.assertNotIn("Supervisor Agent", recommendation["items"][0]["insights"][0]["detail"])

    def test_reorder_prompt_focuses_on_consumables(self) -> None:
        recommendation = build_cart_recommendation(
            "Restock consumables and gloves for Lakeside.",
            account_id="acct-lakeside",
        )
        categories = {item["category"] for item in recommendation["items"]}
        self.assertEqual(categories, {"consumables"})

    def test_equipment_care_followup_uses_active_quote_context(self) -> None:
        recommendation = build_cart_recommendation(
            "Add Equipment Care",
            account_id="acct-riverfront",
            current_order_lines=[
                {
                    "sku": "EQUIP-CHAIR-500",
                    "title": "A-dec 500 Operatory Package",
                    "category": "equipment",
                    "quantity": 1,
                    "unit_price": 24700.0,
                    "total_price": 24700.0,
                    "warranty_eligible": True,
                }
            ],
            conversation_history=[
                {"role": "user", "content": "Build an operatory quote."},
                {"role": "assistant", "content": "3 recommendations ready."},
            ],
        )

        self.assertEqual([item["sku"] for item in recommendation["items"]], ["SUPPORT-CARE-12"])
        self.assertEqual(recommendation["metadata"]["scenario"], "protection")
        self.assertEqual(recommendation["metadata"]["context_turns"], 2)


if __name__ == "__main__":
    unittest.main()
