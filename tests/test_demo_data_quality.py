from __future__ import annotations

import json
import unittest
from collections import Counter

from agentic_cpq_demo.demo_data import (
    ACCOUNTS,
    PRODUCTS,
    TABLE_NAMES,
    build_genie_serialized_space,
    build_inventory_rows,
    build_equipment_order_history_rows,
    build_pricebook_rows,
    build_supplier_price_book_rows,
    build_supplier_segment_pricing_rows,
    build_warranty_eligibility_rows,
)


class SupplierSegmentPricingQualityTests(unittest.TestCase):
    def test_genie_sources_include_account_context_and_source_freshness(self) -> None:
        serialized = json.loads(
            build_genie_serialized_space("catalog", "schema", "cpq_guidance")
        )
        identifiers = {
            table["identifier"]
            for table in serialized["data_sources"]["tables"]
        }

        self.assertIn("accounts", TABLE_NAMES)
        self.assertIn("source_freshness", TABLE_NAMES)
        self.assertIn("catalog.schema.accounts", identifiers)
        self.assertIn("catalog.schema.source_freshness", identifiers)
        self.assertEqual(
            serialized["data_sources"]["volumes"],
            [{"path": "/Volumes/catalog/schema/cpq_guidance/"}],
        )

    def test_supplier_segment_pricing_is_unique_by_segment_and_sku(self) -> None:
        rows = build_supplier_segment_pricing_rows()
        keys = [(row["segment"], row["sku"]) for row in rows]

        self.assertEqual(len(rows), 3 * len(PRODUCTS))
        self.assertFalse([key for key, count in Counter(keys).items() if count > 1])

    def test_cbct_has_one_price_row_per_segment(self) -> None:
        rows = [
            row
            for row in build_supplier_segment_pricing_rows()
            if row["sku"] == "IMAG-CBCT-210"
        ]

        self.assertEqual(
            {row["segment"]: row["recommended_price"] for row in rows},
            {"growth": 17945.0, "mid-market": 17575.0, "enterprise": 17020.0},
        )
        self.assertEqual({row["supplier_cost"] for row in rows}, {12580.0})


class SearchableDemoDataQualityTests(unittest.TestCase):
    def test_expanded_catalog_has_unique_skus_and_expected_categories(self) -> None:
        skus = [product["sku"] for product in PRODUCTS]
        added_skus = {
            "EQUIP-LIGHT-LED-210",
            "EQUIP-HANDPIECE-240",
            "IMAG-PSP-070",
            "IMAG-CEPH-140",
            "STERI-ULTRA-025",
            "SUPPLY-ENDO-080",
            "SOFT-RECALL-12",
            "SERV-MIGRATE-01",
        }

        self.assertGreaterEqual(len(PRODUCTS), 33)
        self.assertEqual(len(skus), len(set(skus)))
        self.assertTrue(added_skus.issubset(skus))
        self.assertEqual(
            {product["category"] for product in PRODUCTS if product["sku"] in added_skus},
            {"equipment", "imaging", "sterilization", "consumables", "software", "services"},
        )

    def test_product_derived_builders_cover_every_catalog_sku_once(self) -> None:
        expected_skus = {product["sku"] for product in PRODUCTS}
        for builder in (
            build_pricebook_rows,
            build_inventory_rows,
            build_supplier_price_book_rows,
            build_warranty_eligibility_rows,
        ):
            rows = builder()
            self.assertEqual(len(rows), len(PRODUCTS), builder.__name__)
            self.assertEqual({row["sku"] for row in rows}, expected_skus, builder.__name__)

    def test_accounts_have_unique_ids_and_public_prospect_count(self) -> None:
        account_ids = [account["account_id"] for account in ACCOUNTS]

        self.assertGreaterEqual(len(ACCOUNTS), 20)
        self.assertEqual(len(account_ids), len(set(account_ids)))
        self.assertTrue(all(account["demo_record"] is True for account in ACCOUNTS))

    def test_public_demo_prospects_have_official_provenance_without_customer_claims(self) -> None:
        expected = {
            "Heartland Dental": "https://heartland.com/",
            "PDS Health": "https://www.pdshealth.com/",
            "Aspen Dental": "https://www.aspendental.com/",
            "Dental Care Alliance": "https://www.dentalcarealliance.net/",
            "MB2 Dental": "https://mb2dental.com/",
        }
        prospects = {
            account["name"]: account
            for account in ACCOUNTS
            if account["account_record_type"] == "public_demo_prospect"
        }

        self.assertEqual(set(prospects), set(expected))
        for name, official_url in expected.items():
            account = prospects[name]
            self.assertEqual(account["relationship_status"], "demo_prospect_not_a_customer")
            self.assertEqual(account["provenance_source"], "official_website")
            self.assertEqual(account["provenance_url"], official_url)
            self.assertEqual(account["provenance_verified_on"], "2026-09-10")
            self.assertIsNone(account["erp_customer_id"])
            self.assertIsNone(account["salesforce_account_id"])
            self.assertIsNone(account["annual_spend_usd"])
            self.assertIsNone(account["days_since_last_purchase"])
            self.assertEqual(account["installed_base"], [])

        prospect_ids = {account["account_id"] for account in prospects.values()}
        order_account_ids = {row["account_id"] for row in build_equipment_order_history_rows()}
        self.assertFalse(prospect_ids & order_account_ids)

    def test_genie_account_guidance_preserves_public_prospect_boundary(self) -> None:
        serialized = json.loads(
            build_genie_serialized_space("catalog", "schema", "cpq_guidance")
        )
        account_table = next(
            table
            for table in serialized["data_sources"]["tables"]
            if table["identifier"] == "catalog.schema.accounts"
        )
        instructions = " ".join(
            instruction["content"][0]
            for instruction in serialized["instructions"]["text_instructions"]
        )

        self.assertIn("public_demo_prospect", account_table["description"][0])
        self.assertIn("do not assert a customer relationship", account_table["description"][0])
        self.assertIn("public research only", instructions)
        self.assertIn("never imply a customer relationship", instructions)


if __name__ == "__main__":
    unittest.main()
