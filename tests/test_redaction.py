from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server.redaction import normalize_view_role, redact_recommendation_for_view


_FORBIDDEN_SELLER_PROSE = re.compile(
    r"\b(?:buy[-\s]?side|costs?|cogs|floors?|gm|margins?|markups?|profits?|"
    r"wholesale|over[-\s]?pay(?:ment|ing)?s?|percent(?:age)?|pct)\b|"
    r"(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)\s*%",
    re.IGNORECASE,
)


def _string_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _string_values(item)]
    return [value] if isinstance(value, str) else []


def _sample() -> dict:
    return {
        "overpay_prevented_total": 1383.8,
        "items": [
            {
                "sku": "IMAG-CBCT-210",
                "supplier_cost": 12580.0,
                "legacy_supplier_cost": 13963.8,
                "correct_supplier_cost": 12580.0,
                "gross_margin_pct": 28.4,
                "overpay_amount": 1383.8,
                "overpay_prevented": True,
                "overpay_risk": "Caught $1,384 supplier overpayment vs. legacy legacy CPQ cost.",
                "line_insights": [
                    {"label": "Fit", "status": "Ready", "detail": "Good fit."},
                    {"label": "Margin", "status": "28.4% GM", "detail": "x"},
                ],
            }
        ],
        "intelligence_signals": [
            {"label": "Supplier Cost", "status": "Checked"},
            {"label": "Overpay", "status": "$1,384 Saved"},
            {"label": "Equipment Care", "status": "Prompt"},
        ],
        "pricing_controls": [{"label": "Margin", "status": "OK"}, {"label": "Price", "status": "Segment"}],
        "quote_readiness": [{"label": "Margin", "status": "OK"}, {"label": "Approval", "status": "Clear"}],
        "business_impact": [{"label": "Overpay Risk", "status": "Reduced", "detail": "..."}],
        "requirements_coverage": [{"label": "Supplier Overpay", "status": "Controlled", "detail": "..."}],
        "metadata": {},
        "evidence": [
            {
                "status": "success",
                "answer": "A product is available. Supplier cost is $12,580.",
                "sql_attachments": [
                    {
                        "sql": "SELECT sku, supplier_cost FROM pricing",
                        "description": "Internal query",
                        "columns": ["sku", "supplier_cost", "recommended_price"],
                        "rows": [["IMAG-CBCT-210", 12580, 17575]],
                    }
                ],
            }
        ],
    }


def _prose_leak_sample() -> dict:
    payload = _sample()
    item = payload["items"][0]
    item.update(
        {
            "approval_required": True,
            "approval_reason": "Gross margin 18.7% is below the approval floor of 24%.",
            "rationale": "Strong fit for the expansion. Supplier cost supports a 28.4% GM.",
            "pricing_guardrail": "Do not cross the 24 percent margin floor.",
            "line_insights": [
                {
                    "label": "Control",
                    "status": "18.7% GM",
                    "detail": "Supplier cost is $12,580 and gross margin is 18.7%.",
                },
                {"label": "Fit", "status": "Ready", "detail": "Strong account fit."},
            ],
            "insights": [
                {
                    "source": "buy-side-policy",
                    "title": "Margin floor guide",
                    "detail": "Approval floor is 24%. Installation fit is confirmed.",
                }
            ],
            "citations": [
                {
                    "source": "control",
                    "title": "Supplier cost check",
                    "detail": "Overpayment avoided. Governed guidance is current.",
                }
            ],
        }
    )
    payload.update(
        {
            "summary": "Quote is ready. Gross margin is 18.7%.",
            "bundle_rationale": "Supplier cost and the 24% floor were evaluated.",
            "pricing_controls": [
                {"label": "Margin", "status": "Review", "detail": "Lowest margin 18.7%."},
                {"label": "Price", "status": "Segment", "detail": "Account pricing applied."},
            ],
            "approval_path": [
                {
                    "label": "Approval",
                    "status": "Routed",
                    "detail": "Gross margin is below 24%. Approval has been routed.",
                }
            ],
            "line_insights": [
                {
                    "label": "IMAG-CBCT-210",
                    "status": "Ready",
                    "detail": "Negotiated cost produces 18.7% margin.",
                }
            ],
            "intelligence_signals": [
                {
                    "label": "Policy Check",
                    "status": "24%",
                    "detail": "Approval floor and supplier cost were checked.",
                },
                {
                    "label": "Approval",
                    "status": "Routed",
                    "detail": "Gross margin is 18.7%. Approval has been routed.",
                },
            ],
            "manager_insights": [
                {"label": "Win Probability", "status": "72%", "detail": "Manager only."}
            ],
            "warnings": ["Margin floor is 24%. Review is already routed."],
            "metadata": {
                "final_message_excerpt": "Supplier cost is $12,580 and margin is 18.7%.",
                "query": "Show cost, margin, floor, and overpay percentages.",
                "gross_margin_pct": 18.7,
            },
            "evidence": [
                {
                    "status": "success",
                    "answer": "The product is available. Gross margin is 18.7%.",
                    "text": "The product is available. Gross margin is 18.7%.",
                    "freshness": {
                        "status": "live",
                        "detail": "Supplier cost refreshed today.",
                    },
                    "citations": [
                        {
                            "title": "Margin floor policy",
                            "uri": "https://example.test/margin-floor-24-percent",
                            "snippet": "Approval floor is 24%. Guidance is current.",
                            "source": "supplier-cost-policy",
                        }
                    ],
                    "knowledge_fallback": {
                        "used": True,
                        "reason": "Supplier cost lookup unavailable.",
                        "answer": "Overpay is $1,384. General guidance is available.",
                    },
                    "sql_attachments": [
                        {
                            "sql": "SELECT sku, margin_floor_pct, note FROM pricing",
                            "description": "Gross margin evidence",
                            "columns": [
                                "sku",
                                "margin_floor_pct",
                                "note",
                                "recommended_price",
                            ],
                            "rows": [
                                [
                                    "IMAG-CBCT-210",
                                    24.0,
                                    "Gross margin is 18.7%. Product is available.",
                                    17575,
                                ]
                            ],
                        }
                    ],
                }
            ],
        }
    )
    return payload


class RedactionTests(unittest.TestCase):
    def test_manager_view_is_unchanged(self) -> None:
        payload = _prose_leak_sample()
        expected = copy.deepcopy(payload)
        result = redact_recommendation_for_view(payload, "manager")
        self.assertIs(result, payload)
        self.assertEqual(result, expected)
        self.assertEqual(result["overpay_prevented_total"], 1383.8)
        self.assertEqual(result["items"][0]["gross_margin_pct"], 28.4)
        self.assertEqual(result["items"][0]["overpay_amount"], 1383.8)
        self.assertIn("Gross margin 18.7%", result["items"][0]["approval_reason"])
        self.assertEqual(result["manager_insights"][0]["status"], "72%")

    def test_seller_view_strips_cost_margin_overpay(self) -> None:
        result = redact_recommendation_for_view(_sample(), "seller")
        item = result["items"][0]
        self.assertIsNone(item["supplier_cost"])
        self.assertIsNone(item["legacy_supplier_cost"])
        self.assertIsNone(item["correct_supplier_cost"])
        self.assertIsNone(item["gross_margin_pct"])
        self.assertEqual(item["overpay_amount"], 0.0)
        self.assertFalse(item["overpay_prevented"])
        self.assertEqual(item["overpay_risk"], "Internal pricing checks are complete.")
        self.assertEqual(result["overpay_prevented_total"], 0.0)
        # No Margin / Overpay / Supplier Cost labeled signals leak through.
        self.assertNotIn("Margin", [li["label"] for li in item["line_insights"]])
        sig_labels = [s["label"] for s in result["intelligence_signals"]]
        self.assertNotIn("Overpay", sig_labels)
        self.assertNotIn("Supplier Cost", sig_labels)
        self.assertNotIn("Margin", [c["label"] for c in result["pricing_controls"]])
        self.assertNotIn("Margin", [c["label"] for c in result["quote_readiness"]])
        self.assertEqual(result["metadata"]["view_role"], "seller")
        evidence = result["evidence"][0]
        self.assertEqual(evidence["answer"], "A product is available.")
        self.assertEqual(evidence["sql_attachments"][0]["sql"], "")
        self.assertEqual(
            evidence["sql_attachments"][0]["columns"],
            ["sku", "recommended_price"],
        )

    def test_seller_view_sanitizes_restricted_prose_across_all_surfaces(self) -> None:
        result = redact_recommendation_for_view(_prose_leak_sample(), "seller")
        item = result["items"][0]

        self.assertEqual(item["approval_reason"], "Additional approval is required.")
        self.assertEqual(item["rationale"], "Strong fit for the expansion.")
        self.assertEqual(item["line_insights"][0]["status"], "Checked")
        self.assertEqual(item["line_insights"][1]["detail"], "Strong account fit.")

        pricing_check = result["pricing_controls"][0]
        self.assertEqual(pricing_check["label"], "Pricing Check")
        self.assertEqual(pricing_check["status"], "Review")
        approval = result["approval_path"][0]
        self.assertEqual(approval["status"], "Routed")
        self.assertEqual(approval["detail"], "Approval has been routed.")
        self.assertEqual(result["intelligence_signals"][1]["status"], "Routed")
        self.assertEqual(
            result["intelligence_signals"][1]["detail"],
            "Approval has been routed.",
        )
        self.assertEqual(result["manager_insights"], [])

        evidence = result["evidence"][0]
        self.assertEqual(evidence["answer"], "The product is available.")
        self.assertEqual(evidence["citations"][0]["snippet"], "Guidance is current.")
        self.assertEqual(evidence["citations"][0]["uri"], "")
        self.assertEqual(
            evidence["knowledge_fallback"]["answer"],
            "General guidance is available.",
        )
        self.assertEqual(
            evidence["sql_attachments"][0]["columns"],
            ["sku", "note", "recommended_price"],
        )
        self.assertEqual(
            evidence["sql_attachments"][0]["rows"][0][1],
            "Product is available.",
        )
        self.assertIsNone(result["metadata"]["gross_margin_pct"])

        for text in _string_values(result):
            self.assertNotRegex(text, _FORBIDDEN_SELLER_PROSE)

    def test_seller_view_does_not_mutate_input(self) -> None:
        payload = _sample()
        redact_recommendation_for_view(payload, "seller")
        # original is untouched (deep copy)
        self.assertEqual(payload["items"][0]["gross_margin_pct"], 28.4)
        self.assertEqual(payload["overpay_prevented_total"], 1383.8)

    def test_normalize_view_role(self) -> None:
        self.assertEqual(normalize_view_role("seller"), "seller")
        self.assertEqual(normalize_view_role("manager"), "manager")
        self.assertEqual(normalize_view_role("demo"), "demo")
        self.assertEqual(normalize_view_role(None), "seller")
        self.assertEqual(normalize_view_role("bogus"), "seller")


if __name__ == "__main__":
    unittest.main()
