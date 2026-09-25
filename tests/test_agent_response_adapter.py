from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server.databricks_api import _recommendation_from_structured_output
from server.models import DraftLineItem


def _translate_typed_agent_fixture(
    response: dict[str, object],
    *,
    query: str,
    account_id: str | None,
    current_order_lines: list[DraftLineItem],
    endpoint_name: str,
) -> dict[str, object]:
    output = response.get("output", [])
    if not isinstance(output, list):
        raise AssertionError("Fixture output must be a list.")
    message = next(
        item for item in reversed(output)
        if isinstance(item, dict) and item.get("type") == "message"
    )
    content = message.get("content", [])
    if not isinstance(content, list):
        raise AssertionError("Fixture message content must be a list.")
    part = next(part for part in content if isinstance(part, dict) and part.get("text"))
    final_text = str(part["text"]).strip()
    json_text = final_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    structured = json.loads(json_text)
    return _recommendation_from_structured_output(
        structured,
        final_text=final_text,
        output=output,
        query=query,
        account_id=account_id,
        current_order_lines=current_order_lines,
        endpoint_name=endpoint_name,
    )


class AgentResponseAdapterTests(unittest.TestCase):
    def test_structured_output_prefers_small_json_payload(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "structured_pricing",
                    "arguments": "{}",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """```json
{
  "summary": "quote PDF-ready CBCT recommendation",
  "bundle_rationale": "CBCT plus onboarding creates a clean imaging upgrade story.",
  "items": [
    {
      "sku": "IMAG-CBCT-210",
      "title": "Vatech CBCT Imaging Starter",
      "quantity": 1,
      "recommended_price": 17500,
      "rationale": "agent-provided fit note from the unified Genie Agent.",
      "line_insights": {"Fit": "Adds 3D imaging capability.", "Control": "Segment price checked."}
    }
  ],
  "next_steps": ["Send quote link via Salesforce."]
}
```""",
                        }
                    ],
                },
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a CBCT quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        self.assertEqual(recommendation["summary"], "quote PDF-ready CBCT recommendation")
        self.assertEqual(recommendation["bundle_rationale"], "CBCT plus onboarding creates a clean imaging upgrade story.")
        self.assertEqual(recommendation["items"][0]["sku"], "IMAG-CBCT-210")
        # Known SKUs are repriced from the account's governed segment price; the
        # model-supplied $17,500 is advisory and is discarded.
        self.assertEqual(recommendation["items"][0]["recommended_price"], 17575)
        self.assertEqual(
            recommendation["items"][0]["rationale"],
            "agent-provided fit note from the unified Genie Agent.",
        )
        self.assertEqual(recommendation["metadata"]["parsed_from"], "agent_structured_output")
        self.assertEqual(recommendation["next_steps"], ["Send quote link via Salesforce."])
        fit = {insight["label"]: insight["detail"] for insight in recommendation["items"][0]["line_insights"]}
        self.assertEqual(fit["Fit"], "Adds 3D imaging capability.")
        self.assertEqual(fit["Control"], "Segment price checked.")

    def test_existing_structured_items_do_not_emit_no_cart_ready_warning(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "Current quote is ready",
  "bundle_rationale": "The existing CBCT line is already staged.",
  "items": [
    {
      "sku": "IMAG-CBCT-210",
      "title": "Vatech CBCT Imaging Starter",
      "quantity": 1,
      "recommended_price": 17500,
      "rationale": "Already present in the seller quote."
    }
  ],
  "next_steps": ["Present the quote."]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="show me the current quote status",
            account_id="acct-riverfront",
            current_order_lines=[
                DraftLineItem(
                    sku="IMAG-CBCT-210",
                    title="Vatech CBCT Imaging Starter",
                    category="imaging",
                    quantity=1,
                    unit_price=17500.0,
                    warranty_eligible=True,
                )
            ],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        self.assertEqual(recommendation["items"], [])
        self.assertFalse(any("no cart-ready SKUs" in warning for warning in recommendation["warnings"]))

    def test_structured_output_uses_catalog_title_and_price(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "CBCT quote for Riverfront",
  "bundle_rationale": "CBCT with Equipment Care keeps the capital investment protected.",
  "items": [
    {
      "sku": "SUPPORT-CARE-12",
      "title": "Equipment Care - CBCT Coverage",
      "quantity": 1,
      "recommended_price": 1600,
      "rationale": "Protects the CBCT investment.",
      "line_insights": {"Fit": "Coverage stays visible through quote acceptance.", "Control": "Attach checked before quote PDF staging."}
    }
  ],
  "next_steps": ["Generate the customer quote PDF."]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a CBCT quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        item = recommendation["items"][0]
        # The catalog is authoritative for a known SKU's title; the agent's
        # creative relabeling ("Equipment Care - CBCT Coverage") is discarded.
        self.assertEqual(item["title"], "Equipment Care · Operatory Care")
        self.assertEqual(item["category"], "services")
        self.assertEqual(item["recommended_price"], 1568)
        self.assertEqual(item["unit_price"], 1568)
        self.assertEqual(item["total_price"], 1568)
        self.assertEqual(item["rationale"], "Protects the CBCT investment.")

    def test_live_structured_output_replaces_flat_protection_with_scaled_plan(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "CBCT quote with protection",
  "bundle_rationale": "Imaging plus protection keeps acceptance clean.",
  "items": [
    {
      "sku": "IMAG-CBCT-210",
      "title": "Vatech CBCT Imaging Starter",
      "quantity": 1,
      "recommended_price": 17575,
      "rationale": "Adds 3D imaging capability.",
      "line_insights": {"Fit": "Fits the imaging motion.", "Control": "Segment price checked."}
    },
    {
      "sku": "EQUIP-CARE",
      "title": "Equipment Care - CBCT Coverage",
      "quantity": 1,
      "recommended_price": 1850,
      "rationale": "Protects the CBCT investment.",
      "line_insights": {"Fit": "Coverage remains visible during quote acceptance.", "Control": "Attach checked before quote PDF staging."}
    }
  ],
  "next_steps": ["Generate the customer quote PDF."]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a CBCT quote with Equipment Care.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        # The agent's flat protection line is dropped and replaced by a scaled
        # Equipment Care care plan attached to the CBCT it covers — with the imaging
        # family's specific code (SUPPORT-CARE-IMG), not a universal one.
        self.assertEqual([item["sku"] for item in recommendation["items"]], ["IMAG-CBCT-210", "SUPPORT-CARE-IMG"])
        plan = recommendation["items"][1]
        self.assertTrue(plan["is_addon"])
        self.assertEqual(plan["covers_sku"], "IMAG-CBCT-210")
        self.assertEqual(plan["category"], "services")
        self.assertFalse(plan["warranty_eligible"])  # the plan never spawns a plan of its own
        # 12% of the CBCT's segment net (18,500 list -> 17,575 mid-market -> 2,109).
        self.assertEqual(plan["unit_price"], 2109.0)
        self.assertEqual(plan["total_price"], 2109.0)
        self.assertGreater(plan["gross_margin_pct"], 0)
        self.assertFalse(any("demo catalog" in warning for warning in recommendation["warnings"]))

    def test_live_structured_output_counts_all_agent_items_in_readiness(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "Two-line Agent quote",
  "bundle_rationale": "Two agent lines should render exactly.",
  "items": [
    {"sku": "SKU-A", "title": "agent Practice Software", "quantity": 1, "recommended_price": 100, "rationale": "Fits the practice workflow."},
    {"sku": "SKU-B", "title": "agent Supply Kit", "quantity": 2, "recommended_price": 25, "rationale": "Restocks operatory supplies."}
  ],
  "next_steps": []
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        self.assertEqual(len(recommendation["items"]), 2)
        self.assertEqual(sum(item["total_price"] for item in recommendation["items"]), 125)
        self.assertEqual(recommendation["workflow_steps"][0]["status"], "2 Lines")
        self.assertEqual(recommendation["summary"], "Two-line Agent quote")

    def test_live_structured_output_uses_line_total_without_double_counting(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "Two-operatory bundle at $79,040",
  "bundle_rationale": "Expansion quote.",
  "quote_subtotal": 79040,
  "items": [
    {
      "sku": "EQUIP-CHAIR-500",
      "title": "A-dec 500 Operatory Package",
      "quantity": 2,
      "unit_price": 26000,
      "line_total": 52000,
      "recommended_price": 52000,
      "rationale": "Two rooms.",
      "line_insights": {"Fit": "Room readiness.", "Control": "Standard pricing at $26,000 per unit."}
    },
    {
      "sku": "STERI-M11-90",
      "title": "Midmark M11 Sterilization Suite",
      "quantity": 2,
      "unit_price": 7800,
      "line_total": 15600,
      "recommended_price": 15600,
      "rationale": "Sterilization coverage.",
      "line_insights": {"Fit": "Compliance.", "Control": "Standard pricing at $7,800 per unit."}
    }
  ],
  "next_steps": []
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a two-operatory quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        items_by_sku = {item["sku"]: item for item in recommendation["items"]}
        chair = items_by_sku["EQUIP-CHAIR-500"]
        steri = items_by_sku["STERI-M11-90"]
        # Governed segment pricing wins over the model-supplied line totals.
        self.assertEqual(chair["unit_price"], 24700)
        self.assertEqual(chair["total_price"], 49400)
        self.assertEqual(steri["unit_price"], 7410)
        self.assertEqual(steri["total_price"], 14820)
        # Equipment Care is auto-attached to both eligible equipment lines.
        plans = [item for item in recommendation["items"] if item.get("is_addon")]
        self.assertEqual({plan["covers_sku"] for plan in plans}, {"EQUIP-CHAIR-500", "STERI-M11-90"})
        # The agent's stated subtotal is still reconciled against actual line totals.
        notes = {lineage["label"]: lineage["detail"] for lineage in recommendation["source_lineage"]}
        self.assertIn("Subtotal Reconciled", notes)
        self.assertIn("$79,040", notes["Subtotal Reconciled"])

    def test_live_structured_output_treats_recommended_price_as_line_total_fallback(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "Consumables line",
  "bundle_rationale": "Consumables.",
  "items": [
    {"sku": "SUPPLY-START-050", "title": "Operatory Consumables Starter Kit", "quantity": 2, "recommended_price": 4800, "rationale": "Two kits."}
  ],
  "next_steps": []
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        item = recommendation["items"][0]
        self.assertEqual(item["unit_price"], 2352)
        self.assertEqual(item["recommended_price"], 2352)
        self.assertEqual(item["total_price"], 4704)

    def test_live_structured_output_preserves_intelligence_fields(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "Segment-aware quote",
  "bundle_rationale": "Databricks intelligence prevents overpay and routes approvals.",
  "quote_subtotal": 52000,
  "supplier_cost_checked": true,
  "overpay_prevented": true,
  "equipment_care_prompt": "Prompt Equipment Care before acceptance.",
  "pdf_ready": true,
  "salesforce_order_link_ready": true,
  "win_probability": 62,
  "conversion_risk": "Approval delay",
  "follow_up_action": "Route approval and send quote PDF link.",
  "items": [
    {
      "sku": "EQUIP-CHAIR-500",
      "title": "A-dec 500 Operatory Package",
      "quantity": 2,
      "unit_price": 26000,
      "line_total": 52000,
      "supplier_cost": 16120,
      "gross_margin_pct": 38,
      "supplier_cost_checked": true,
      "overpay_prevented": true,
      "overpay_risk": "legacy CPQ single wholesale price avoided.",
      "pricing_guardrail": "Segment price and supplier cost checked.",
      "approval_required": true,
      "approval_reason": "Capital quote requires tiered review.",
      "attach_recommendation": "Offer Equipment Care at acceptance.",
      "rationale": "Two operatories.",
      "line_insights": {"Fit": "Room readiness.", "Control": "Approval routed."}
    }
  ],
  "next_steps": ["Route approval."]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a two-operatory quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        item = recommendation["items"][0]
        # Narrative fields stay agent-authored; governance + cost facts are
        # re-derived from the catalog so they can't contradict the rules.
        self.assertEqual(item["pricing_guardrail"], "Segment price and supplier cost checked.")
        self.assertEqual(item["attach_recommendation"], "Offer Equipment Care at acceptance.")
        self.assertTrue(item["supplier_cost_checked"])
        self.assertEqual(item["supplier_cost"], 18460.0)  # negotiated, not the agent's 16120
        self.assertTrue(item["overpay_prevented"])
        # EQUIP-CHAIR-500 x2: (20121.40 legacy - 18460.00 negotiated) * 2 = 3322.80
        self.assertEqual(item["overpay_amount"], 3322.8)
        self.assertIn("$3,323", item["overpay_risk"])
        # EQUIP-CHAIR-500 at $26,000 sits at 29% margin (above the 24% floor) for a
        # mid-market account, so the catalog re-derives no approval requirement.
        self.assertFalse(item["approval_required"])
        self.assertEqual(item["approval_reason"], "")
        self.assertEqual(recommendation["overpay_prevented_total"], 3322.8)
        self.assertEqual(recommendation["win_probability"], 62)
        self.assertEqual(recommendation["follow_up_action"], "Route approval and send quote PDF link.")
        self.assertEqual(recommendation["conversion_risk"], "Approval delay")
        signals = {signal["label"]: signal["status"] for signal in recommendation["intelligence_signals"]}
        self.assertEqual(signals["Supplier Cost"], "Checked")
        self.assertEqual(signals["Overpay"], "$3,323 Saved")
        self.assertEqual(signals["Win Signal"], "62%")

    def test_known_sku_overrides_agent_miscategorization(self) -> None:
        # Reproduces the live defect: the agent returned CBCT as category
        # "services" with warranty_eligible false. The catalog must win so
        # Equipment Care attaches to the imaging unit and the approval reason is
        # never self-contradictory.
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "CBCT quote",
  "bundle_rationale": "Imaging upgrade.",
  "items": [
    {
      "sku": "IMAG-CBCT-210",
      "title": "CBCT Imaging System",
      "category": "services",
      "quantity": 1,
      "unit_price": 17575,
      "line_total": 17575,
      "warranty_eligible": false,
      "approval_required": true,
      "approval_reason": "Gross margin 28.4% exceeds Imaging Director threshold of 24%.",
      "rationale": "Adds 3D diagnostics."
    }
  ]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a CBCT quote for Riverfront with Equipment Care.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        item = recommendation["items"][0]
        self.assertEqual(item["category"], "imaging")
        self.assertTrue(item["warranty_eligible"])
        # Margin 28.4% is ABOVE the 24% floor, so the contradictory reason is
        # gone; no other rule fires for a mid-market Equipment Specialist.
        self.assertFalse(item["approval_required"])
        self.assertNotIn("exceeds", item["approval_reason"])
        # Imaging carries a real legacy-vs-negotiated overpay delta.
        self.assertGreater(item["overpay_amount"], 0)
        self.assertGreater(recommendation["overpay_prevented_total"], 0)

    def test_decimal_win_probability_is_normalized_to_percent(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": """{
  "summary": "CBCT quote",
  "bundle_rationale": "Protects imaging investment.",
  "quote_subtotal": 19175,
  "win_probability": 0.78,
  "items": [
    {
      "sku": "IMAG-CBCT-210",
      "title": "CBCT Imaging System",
      "quantity": 1,
      "unit_price": 17575,
      "line_total": 17575,
      "rationale": "Adds imaging capacity.",
      "line_insights": {"Fit": "Good fit.", "Control": "Segment price checked."}
    }
  ]
}""",
                        }
                    ],
                }
            ]
        }

        recommendation = _translate_typed_agent_fixture(
            response,
            query="Build a CBCT quote.",
            account_id="acct-riverfront",
            current_order_lines=[],
            endpoint_name="databricks-gpt-5-6-terra",
        )

        self.assertEqual(recommendation["win_probability"], 78)
        signals = {signal["label"]: signal["status"] for signal in recommendation["intelligence_signals"]}
        self.assertEqual(signals["Win Signal"], "78%")
        manager = {signal["label"]: signal["status"] for signal in recommendation["manager_insights"]}
        self.assertEqual(manager["Win Probability"], "78%")


if __name__ == "__main__":
    unittest.main()
