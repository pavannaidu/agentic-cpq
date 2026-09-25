from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from agentic_cpq_demo.cpq import attach_default_care_plans, care_plan_line_for
from agentic_cpq_demo.demo_data import (
    WARRANTY_PLANS,
    WARRANTY_SKUS,
    build_warranty_eligibility_rows,
    care_plan_unit_price,
    recommended_price,
    warranty_rules_from_rows,
)
from agentic_cpq_demo.mock_engine import build_cart_recommendation
from server.redaction import redact_recommendation_for_view


def _seed_rules():
    return warranty_rules_from_rows(build_warranty_eligibility_rows())


def _equipment_line(sku="EQUIP-CHAIR-500", category="equipment", list_price=26000.0, qty=2):
    return {
        "sku": sku,
        "title": f"{sku} title",
        "category": category,
        "quantity": qty,
        "unit_price": list_price,
        "list_price": list_price,
    }


class CarePlanPricingTests(unittest.TestCase):
    def test_price_scales_per_covered_unit(self) -> None:
        product = {"unit_price": 26000.0, "category": "equipment"}
        pct = WARRANTY_PLANS["equipment"]["care_plan_pct"]
        expected = round(recommended_price(product, "mid-market") * pct, 2)
        self.assertEqual(care_plan_unit_price(product, "mid-market", pct), expected)

    def test_higher_value_equipment_costs_more_to_protect(self) -> None:
        cheap = {"unit_price": 6000.0, "category": "sterilization"}
        pricey = {"unit_price": 148000.0, "category": "imaging"}
        self.assertLess(
            care_plan_unit_price(cheap, "mid-market", WARRANTY_PLANS["sterilization"]["care_plan_pct"]),
            care_plan_unit_price(pricey, "mid-market", WARRANTY_PLANS["imaging"]["care_plan_pct"]),
        )


class CarePlanLineTests(unittest.TestCase):
    def test_line_uses_family_specific_code_and_rate(self) -> None:
        # An imaging line gets the imaging Equipment Care code, not a universal one.
        rule = WARRANTY_PLANS["imaging"]
        line = care_plan_line_for(
            _equipment_line("IMAG-CBCT-210", "imaging", 148000.0, 1), {"segment": "mid-market"}, rule
        )
        self.assertEqual(line["sku"], "SUPPORT-CARE-IMG")
        self.assertEqual(line["title"], rule["warranty_title"])
        self.assertTrue(line["is_addon"])
        self.assertEqual(line["covers_sku"], "IMAG-CBCT-210")
        self.assertFalse(line["warranty_eligible"])  # never spawns a plan of its own
        expected_unit = care_plan_unit_price(
            {"unit_price": 148000.0, "category": "imaging"}, "mid-market", rule["care_plan_pct"]
        )
        self.assertEqual(line["unit_price"], expected_unit)
        self.assertGreater(line["gross_margin_pct"], 0)  # profit center, not a drag

    def test_operatory_line_uses_operatory_code(self) -> None:
        line = care_plan_line_for(_equipment_line(), {"segment": "mid-market"}, WARRANTY_PLANS["equipment"])
        self.assertEqual(line["sku"], "SUPPORT-CARE-12")
        self.assertEqual(line["quantity"], 2)  # matches covered equipment qty
        self.assertEqual(line["total_price"], round(line["unit_price"] * 2, 2))


class BuildWarrantyRowsTests(unittest.TestCase):
    def test_rows_carry_family_code_and_rate(self) -> None:
        rules = _seed_rules()
        cbct = rules["IMAG-CBCT-210"]
        self.assertTrue(cbct["eligible"])
        self.assertEqual(cbct["warranty_sku"], "SUPPORT-CARE-IMG")
        self.assertEqual(cbct["care_plan_pct"], WARRANTY_PLANS["imaging"]["care_plan_pct"])
        # a warranty plan SKU itself is never eligible for a plan of its own
        self.assertFalse(rules["SUPPORT-CARE-IMG"]["eligible"])

    def test_non_eligible_category_has_no_plan(self) -> None:
        rules = _seed_rules()
        soft = rules["SOFT-PRACTICE-12"]
        self.assertFalse(soft["eligible"])
        self.assertIsNone(soft["warranty_sku"])
        self.assertEqual(soft["care_plan_pct"], 0.0)


class AttachTests(unittest.TestCase):
    def test_attaches_family_specific_plan_after_each_line(self) -> None:
        lines = [_equipment_line("IMAG-CBCT-210", "imaging", 148000.0, 1), _equipment_line()]
        out = attach_default_care_plans(lines, {"segment": "mid-market"})
        plans = [l for l in out if l.get("is_addon")]
        self.assertEqual(len(plans), 2)
        self.assertEqual(out[0]["sku"], "IMAG-CBCT-210")
        self.assertEqual(out[1]["sku"], "SUPPORT-CARE-IMG")  # imaging code
        self.assertEqual(out[1]["covers_sku"], "IMAG-CBCT-210")
        self.assertEqual(out[2]["sku"], "EQUIP-CHAIR-500")
        self.assertEqual(out[3]["sku"], "SUPPORT-CARE-12")  # operatory code
        self.assertEqual(out[3]["covers_sku"], "EQUIP-CHAIR-500")

    def test_idempotent_no_double_attach(self) -> None:
        lines = [_equipment_line()]
        once = attach_default_care_plans(lines, {"segment": "mid-market"})
        twice = attach_default_care_plans(once, {"segment": "mid-market"})
        self.assertEqual(len([l for l in twice if l.get("is_addon")]), 1)

    def test_non_eligible_categories_get_no_plan(self) -> None:
        lines = [
            _equipment_line("SOFT-PRACTICE-12", "software", 6400.0, 1),
            _equipment_line("REORDER-GLOVE-24", "consumables", 120.0, 1),
        ]
        out = attach_default_care_plans(lines, {"segment": "mid-market"})
        self.assertEqual([l for l in out if l.get("is_addon")], [])

    def test_behavior_is_table_driven_not_hardcoded(self) -> None:
        # Flip eligibility + rate in the rules map: the attached plan must reflect
        # the injected table, proving the logic reads data rather than category.
        rules = _seed_rules()
        rules["EQUIP-CHAIR-500"] = {
            "sku": "EQUIP-CHAIR-500",
            "eligible": True,
            "warranty_sku": "SUPPORT-CARE-CUSTOM",
            "warranty_title": "Equipment Care · Custom",
            "care_plan_pct": 0.25,
        }
        out = attach_default_care_plans([_equipment_line()], {"segment": "mid-market"}, rules=rules)
        plan = next(l for l in out if l.get("is_addon"))
        self.assertEqual(plan["sku"], "SUPPORT-CARE-CUSTOM")
        expected_unit = care_plan_unit_price({"unit_price": 26000.0, "category": "equipment"}, "mid-market", 0.25)
        self.assertEqual(plan["unit_price"], expected_unit)

    def test_disabled_rule_attaches_nothing(self) -> None:
        rules = _seed_rules()
        rules["EQUIP-CHAIR-500"]["eligible"] = False
        out = attach_default_care_plans([_equipment_line()], {"segment": "mid-market"}, rules=rules)
        self.assertEqual([l for l in out if l.get("is_addon")], [])


class EngineIntegrationTests(unittest.TestCase):
    def test_mock_engine_auto_attaches_family_plans(self) -> None:
        rec = build_cart_recommendation("CBCT imaging and operatory setup", account_id="acct-riverfront")
        plans = [i for i in rec["items"] if i.get("is_addon")]
        self.assertTrue(plans, "expected at least one auto-attached Equipment Care plan")
        for plan in plans:
            self.assertIn(plan["sku"], WARRANTY_SKUS)
            self.assertIsNotNone(plan["covers_sku"])
        for item in rec["items"]:
            if item["category"] in {"equipment", "imaging", "sterilization"}:
                self.assertIsNotNone(item["legacy_supplier_cost"])
                self.assertIsNotNone(item["correct_supplier_cost"])
                self.assertIn("overpay_amount", item)

    def test_no_standalone_care_plan_line(self) -> None:
        rec = build_cart_recommendation("CBCT imaging and operatory setup", account_id="acct-riverfront")
        standalone = [i for i in rec["items"] if i["sku"] in WARRANTY_SKUS and not i.get("is_addon")]
        self.assertEqual(standalone, [], "a care-plan SKU should never be its own standalone line")


class ResolverFallbackTests(unittest.TestCase):
    def test_resolver_falls_back_to_seed_without_db(self) -> None:
        # No Postgres in tests → lakebase.get_warranty_eligibility raises →
        # warranty_rules_by_sku returns the in-memory seed.
        from server.databricks_api import warranty_rules_by_sku

        rules = warranty_rules_by_sku()
        self.assertEqual(rules["IMAG-CBCT-210"]["warranty_sku"], "SUPPORT-CARE-IMG")
        self.assertTrue(rules["EQUIP-CHAIR-500"]["eligible"])


class RedactionTests(unittest.TestCase):
    def test_seller_view_nulls_buyside_on_all_lines(self) -> None:
        payload = {
            "overpay_prevented_total": 1383.8,
            "items": [
                {
                    "sku": "IMAG-CBCT-210",
                    "supplier_cost": 12580.0,
                    "legacy_supplier_cost": 13963.8,
                    "correct_supplier_cost": 12580.0,
                    "gross_margin_pct": 29.0,
                    "overpay_amount": 1383.8,
                    "is_addon": False,
                },
                care_plan_line_for(
                    _equipment_line("IMAG-CBCT-210", "imaging", 148000.0, 1),
                    {"segment": "mid-market"},
                    WARRANTY_PLANS["imaging"],
                ),
            ],
        }
        redacted = redact_recommendation_for_view(payload, "seller")
        for item in redacted["items"]:
            self.assertIsNone(item.get("supplier_cost"))
            self.assertIsNone(item.get("legacy_supplier_cost"))
            self.assertIsNone(item.get("correct_supplier_cost"))
            self.assertEqual(item.get("overpay_amount"), 0.0)


if __name__ == "__main__":
    unittest.main()
