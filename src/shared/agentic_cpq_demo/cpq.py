from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .demo_data import (
    build_warranty_eligibility_rows,
    care_plan_eligible,
    care_plan_supplier_cost,
    care_plan_unit_price,
    gross_margin_pct,
    warranty_rules_from_rows,
)

_DEFAULT_RULES_CACHE: dict[str, dict[str, Any]] | None = None
_DEFAULT_APPROVAL_THRESHOLD = 80_000.0


def _default_warranty_rules() -> dict[str, dict[str, Any]]:
    """In-memory warranty rules (the seed), used by the mock/test path and as the
    app's fallback when the Lakebase table is unavailable."""
    global _DEFAULT_RULES_CACHE
    if _DEFAULT_RULES_CACHE is None:
        _DEFAULT_RULES_CACHE = warranty_rules_from_rows(build_warranty_eligibility_rows())
    return _DEFAULT_RULES_CACHE


def care_plan_line_for(
    equipment_line: dict[str, Any],
    account: dict[str, Any] | None = None,
    rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Equipment Care care-plan line that covers one equipment line.

    The specific warranty code, plan name, and rate all come from ``rule`` (a row
    of the ``warranty_eligibility`` table), so a CBCT gets ``SUPPORT-CARE-IMG`` at
    its imaging rate while a chair gets ``SUPPORT-CARE-12`` at its operatory rate.
    Priced per covered unit and scaled to that equipment's value, so the warranty
    on a CBCT costs far more than the one on an autoclave. ``warranty_eligible`` is
    False so the plan never spawns a plan of its own; ``covers_sku`` links it back
    to the equipment it protects.
    """
    rule = rule or {}
    segment = (account or {}).get("segment", "mid-market")
    covered = {
        "unit_price": float(equipment_line.get("list_price") or equipment_line.get("unit_price") or 0.0),
        "category": equipment_line.get("category", "unknown"),
    }
    pct = float(rule.get("care_plan_pct") or 0.0)
    unit_price = care_plan_unit_price(covered, segment, pct)
    cost = care_plan_supplier_cost(unit_price)
    qty = int(equipment_line.get("quantity", 1) or 1)
    return {
        "sku": rule.get("warranty_sku") or "SUPPORT-CARE-12",
        "title": rule.get("warranty_title") or "Equipment Care · Equipment Care Plan",
        "category": "services",
        "quantity": qty,
        "unit_price": unit_price,
        "list_price": unit_price,
        "recommended_price": unit_price,
        "supplier_cost": cost,
        "gross_margin_pct": gross_margin_pct(unit_price, cost),
        "approval_required": False,
        "warranty_eligible": False,
        "total_price": round(unit_price * qty, 2),
        "overpay_amount": 0.0,
        "legacy_supplier_cost": cost,
        "correct_supplier_cost": cost,
        "overpay_risk": "Supplier cost checked",
        "is_addon": True,
        "covers_sku": equipment_line.get("sku"),
        "rationale": (
            f"Equipment Care extended warranty for {equipment_line.get('title', 'the covered equipment')}; "
            "auto-attached so the rep never has to add it manually."
        ),
        "confidence": "high",
    }


def attach_default_care_plans(
    lines: list[dict[str, Any]],
    account: dict[str, Any] | None = None,
    rules: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return ``lines`` with an Equipment Care plan auto-attached after each eligible
    equipment line that does not already have one.

    Eligibility, the specific warranty code, and the rate come from ``rules`` (the
    ``warranty_eligibility`` table, indexed by product SKU). ``rules`` defaults to
    the in-memory seed so the mock/test path needs no change; the live app passes a
    map read from Lakebase.

    Equipment Care is opt-out: the plan is added by default so the rep never has to
    remember it, and the seller can remove it in the workspace. Idempotent on
    ``covers_sku`` — an equipment line that already has a plan (or one just added)
    is not doubled up. This runs when a recommendation is assembled, not on every
    edit, so a plan the seller removes stays removed.
    """
    rules = rules if rules is not None else _default_warranty_rules()
    covered = {line.get("covers_sku") for line in lines if line.get("is_addon")}
    result: list[dict[str, Any]] = []
    for line in lines:
        result.append(line)
        sku = line.get("sku")
        if line.get("is_addon"):
            continue
        if care_plan_eligible(sku, rules) and sku not in covered:
            result.append(care_plan_line_for(line, account, rules.get(sku)))
            covered.add(sku)
    return result


def _quote_id(order_id: str, serialized_lines: str) -> str:
    digest = hashlib.sha1(f"{order_id}:{serialized_lines}".encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"Q-{digest[:10].upper()}"


def _line_total(line: dict[str, Any]) -> float:
    return round(float(line["quantity"]) * float(line["unit_price"]), 2)


def build_quote_payload(
    *,
    order_id: str,
    account_id: str,
    seller_id: str,
    environment: str,
    line_items: list[dict[str, Any]],
    account: dict[str, Any] | None = None,
    approval_threshold: float = _DEFAULT_APPROVAL_THRESHOLD,
) -> dict[str, Any]:
    sanitized_lines = [
        {
            "sku": line["sku"],
            "title": line["title"],
            "category": line.get("category", "unknown"),
            "quantity": int(line["quantity"]),
            "unit_price": float(line["unit_price"]),
            "list_price": float(line.get("list_price") or line["unit_price"]),
            "recommended_price": float(line.get("recommended_price") or line["unit_price"]),
            "supplier_cost": float(line.get("supplier_cost") or 0),
            "gross_margin_pct": float(line.get("gross_margin_pct") or 0),
            "approval_required": bool(line.get("approval_required", False)),
            "warranty_eligible": bool(line.get("warranty_eligible", False)),
            "total_price": _line_total(line),
        }
        for line in line_items
    ]
    serialized_lines = json.dumps(sanitized_lines, sort_keys=True)
    quote_id = _quote_id(order_id, serialized_lines)
    subtotal = round(sum(line["total_price"] for line in sanitized_lines), 2)
    account = account or {}
    approvals = [line for line in sanitized_lines if line["approval_required"]]
    warranty_lines = [line for line in sanitized_lines if line["warranty_eligible"]]
    threshold = float(approval_threshold)
    if threshold <= 0:
        raise ValueError("Approval threshold must be greater than zero.")
    exceeds_threshold = subtotal > threshold
    approval_status = "approval-required" if approvals or exceeds_threshold else "clear"
    line_count = len(sanitized_lines)
    payload = {
        "quote_id": quote_id,
        "quote_name": f"Quote-{environment}-{quote_id}",
        "platform": "Agentic CPQ",
        "sync_status": "document-ready",
        "created_at": datetime.now(tz=UTC).isoformat(),
        "quote_document": {
            "quote_header": {
                "account_id": account_id,
                "customer_name": account.get("name", "Unknown account"),
                "market_segment": account.get("segment", "unknown"),
                "owner_id": seller_id,
                "status": "Draft",
                "source": "future-state-equipment-quoting",
            },
            "equipment_lines": [
                {
                    "product_code": line["sku"],
                    "description": line["title"],
                    "quantity": line["quantity"],
                    "list_price": line["unit_price"],
                    "recommended_price": line["recommended_price"],
                    "supplier_cost": line["supplier_cost"],
                    "gross_margin_pct": line["gross_margin_pct"],
                    "approval_required": line["approval_required"],
                    "warranty_eligible": line["warranty_eligible"],
                    "net_price": line["unit_price"],
                    "extended_price": line["total_price"],
                }
                for line in sanitized_lines
            ],
            "pricing_controls": {
                "approval_status": approval_status,
                "approval_reasons": [
                    f"{line['sku']} requires manager review" for line in approvals
                ] + (
                    [f"Quote total exceeds ${threshold:,.0f}"]
                    if exceeds_threshold
                    else []
                ),
                "supplier_cost_checked": True,
                "dynamic_pricing_checked": True,
            },
            "recommended_addons": [
                {
                    "sku": "SUPPORT-CARE-12",
                    "title": "Equipment Care",
                    "status": "eligible",
                }
            ] if warranty_lines else [],
            "customer_document": {
                "status": "ready",
                "format": "PDF",
                "delivery": "browser_download",
            },
            "salesforce_order_link": {
                "status": "pending_acceptance",
                "target": "Equipment_Order_Form",
                "activation": "after_customer_acceptance",
                "account_id": account.get("salesforce_account_id", account_id),
            },
            "pipeline": {
                "status": "open_quote",
                "visibility": "available_at_quote_creation",
                "line_count": line_count,
                "follow_up_state": "ready",
                "conversion_baseline_pct": 31.0,
            },
            "access_controls": {
                "sso_status": "ready",
                "autosave_status": "enabled",
                "legacy_quote_system_access": "not_required",
            },
            "data_flow": [
                {"source": "ERP", "role": "customer_product_price_master", "status": "fresh"},
                {"source": "OMS", "role": "availability_order_po_install_context", "status": "fresh"},
                {"source": "Legacy CPQ", "role": "quote_history_only", "status": "reference"},
                {"source": "Agentic CPQ", "role": "customer_document_generation", "status": "ready"},
                {"source": "Salesforce", "role": "post_acceptance_order_link", "status": "pending_acceptance"},
            ],
        },
        "totals": {
            "subtotal": subtotal,
            "grand_total": subtotal,
            "currency_code": "USD",
        },
        "quote_notes": [
            "Customer-ready quote PDF is available for review and download.",
            "The generated revision is immutable; changes create a new revision.",
            "Salesforce order link opens after customer acceptance.",
        ],
    }
    return payload
