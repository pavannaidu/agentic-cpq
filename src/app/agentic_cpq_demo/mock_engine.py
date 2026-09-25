from __future__ import annotations

import re
from typing import Any

from .cpq import _default_warranty_rules, attach_default_care_plans
from .demo_data import (
    ACCOUNTS,
    PRODUCTS,
    SOURCE_FRESHNESS,
    WARRANTY_SKUS,
    care_plan_eligible,
    gross_margin_pct,
    overpayment_for_line,
    recommended_price,
    supplier_cost,
)


def _account_lookup() -> dict[str, dict[str, Any]]:
    return {account["account_id"]: account for account in ACCOUNTS}


def _product_lookup() -> dict[str, dict[str, Any]]:
    return {product["sku"]: product for product in PRODUCTS}


ACCOUNTS_BY_ID = _account_lookup()
PRODUCTS_BY_SKU = _product_lookup()


def build_product_snapshot() -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for product in PRODUCTS:
        snapshot.append(
            {
                "sku": product["sku"],
                "title": product["title"],
                "category": product["category"],
                "unit_price": product["unit_price"],
                "bundle_tags": product["bundle_tags"],
                "financing_eligible": product["financing_eligible"],
            }
        )
    return snapshot


def find_product(sku: str) -> dict[str, Any] | None:
    return PRODUCTS_BY_SKU.get(sku)


def _parse_budget(query: str) -> float | None:
    normalized = query.lower().replace(",", "")
    patterns = [
        r"\$([0-9]+(?:\.[0-9]+)?)(k|m)?",
        r"under\s+([0-9]+(?:\.[0-9]+)?)(k|m)?",
        r"budget\s+of\s+([0-9]+(?:\.[0-9]+)?)(k|m)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        amount = float(match.group(1))
        suffix = match.group(2)
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000
        if amount >= 1_000:
            return amount
    return None


def _infer_scenario(query: str) -> str:
    lowered = query.lower()
    if any(term in lowered for term in ("reorder", "restock", "consumable", "glove", "anesthetic")):
        return "reorder"
    if any(term in lowered for term in ("imaging", "sensor", "scanner", "cbct", "x-ray")):
        return "imaging"
    return "operatory"


def _scenario_tags(scenario: str) -> list[str]:
    if scenario == "reorder":
        return ["reorder", "consumables"]
    if scenario == "imaging":
        return ["imaging", "upgrade", "software", "services"]
    return ["operatory", "expansion", "sterilization", "software", "services", "consumables"]


def _citations_for(product: dict[str, Any], scenario: str) -> list[dict[str, str]]:
    return [
        {
            "source": "fit",
            "title": "Why it fits",
            "detail": f"Fits the {scenario} motion and aligns with the selected account profile.",
        },
        {
            "source": "control",
            "title": "Control",
            "detail": "Segment price, supplier cost, and approval threshold checked.",
        },
    ]


def _line_insights_for(
    product: dict[str, Any],
    rationale: str,
    *,
    margin: float,
    approval_required: bool,
    warranty_eligible: bool,
) -> list[dict[str, str]]:
    approval_status = "Approval Needed" if approval_required else "Clear"
    return [
        {"label": "Fit", "status": "Ready", "detail": rationale},
        {"label": "Margin", "status": f"{margin:.1f}% GM", "detail": "Segment price checked against supplier cost."},
        {"label": "Approval", "status": approval_status, "detail": "Tiered quote control applied before document generation."},
        {
            "label": "Equipment Care",
            "status": "Eligible" if warranty_eligible else "Not Eligible",
            "detail": "Warranty prompt follows eligible equipment through customer acceptance.",
        },
    ]


def _approval_required(
    product: dict[str, Any],
    account: dict[str, Any],
    price: float,
) -> bool:
    if price <= 0:
        return False
    margin = gross_margin_pct(price, supplier_cost(product))
    if product["category"] in {"equipment", "imaging", "sterilization"} and margin < 24:
        return True
    return account.get("segment") == "enterprise" and product["unit_price"] >= 15000


def _warranty_eligible(product: dict[str, Any]) -> bool:
    """Table-driven: does this SKU carry an Equipment Care plan? Reads the in-memory
    warranty rules (the seed); the live app path uses the Lakebase-backed map."""
    return care_plan_eligible(product["sku"], _default_warranty_rules())


def _approval_reason(
    product: dict[str, Any],
    account: dict[str, Any],
    price: float,
    margin: float,
) -> str:
    capital_categories = {"equipment", "imaging", "sterilization"}
    if product["category"] in capital_categories and margin < 24:
        return f"Gross margin {margin:.1f}% is below the {product['category'].title()} approval floor of 24%."
    if account.get("segment") == "enterprise" and product["unit_price"] >= 15000:
        return f"Enterprise-segment capital purchase over ${product['unit_price']:,.0f} requires manager review."
    return "Tiered quote control flagged this line for review."


def _quote_controls(items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    total = sum(item["total_price"] for item in items)
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    min_margin = min((item.get("gross_margin_pct") or 0 for item in items), default=0)
    pricing_controls = [
        {"label": "Margin", "status": "OK" if min_margin >= 24 else "Review", "detail": f"Lowest margin {min_margin:.1f}%"},
        {"label": "Price", "status": "Segment", "detail": "Recommended price uses customer segment."},
    ]
    approval_path = [
        {
            "label": "Approval",
            "status": "Needed" if approvals or total > 80000 else "Clear",
            "detail": "Manager review required." if approvals or total > 80000 else "No next-level approval triggered.",
        }
    ]
    addons = [
        {"sku": "SUPPORT-CARE-12", "title": "Equipment Care", "reason": "Eligible equipment in quote.", "status": "eligible"}
    ] if warranty_items else []
    business_impact = [
        {"label": "Overpay Risk", "status": "Reduced", "detail": "Supplier cost checked before quote stage."},
        {"label": "Quote PDF", "status": "Ready", "detail": "Customer-ready document can be generated in the app."},
    ]
    return pricing_controls, approval_path, addons, business_impact


def _intelligence_signals(items: list[dict[str, Any]], overpay_total: float) -> list[dict[str, str]]:
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    return [
        {"label": "Supplier Cost", "status": "Checked", "detail": "Negotiated supplier cost applied per line."},
        {
            "label": "Overpay",
            "status": f"${overpay_total:,.0f} Saved" if overpay_total > 0 else "Monitored",
            "detail": (
                f"Price check caught ${overpay_total:,.0f} in supplier overpayment vs. legacy CPQ cost."
                if overpay_total > 0
                else "Segment pricing and supplier cost guardrails are active."
            ),
        },
        {
            "label": "Approval",
            "status": "Routed" if approvals else "Clear",
            "detail": (approvals[0].get("approval_reason") if approvals else "") or "Margin, role, and quote-size controls checked.",
        },
        {
            "label": "Equipment Care",
            "status": "Prompt" if warranty_items else "Review",
            "detail": "Keep Equipment Care visible through customer review." if warranty_items else "Review attach eligibility.",
        },
    ]


def _quote_readiness(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    total = sum(float(item.get("total_price", 0)) for item in items)
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    min_margin = min((float(item.get("gross_margin_pct") or 0) for item in items), default=0)
    return [
        {"label": "Margin", "status": "OK" if min_margin >= 24 else "Review", "detail": f"Lowest line margin {min_margin:.1f}%."},
        {"label": "Approval", "status": "Needed" if approvals or total > 80000 else "Clear", "detail": "Tiered controls checked."},
        {"label": "Equipment Care", "status": "Eligible" if warranty_items else "Pending", "detail": "Eligible equipment prompts at acceptance."},
        {"label": "Customer Document", "status": "Ready", "detail": "A branded PDF can be generated in the app."},
        {"label": "Revision Control", "status": "Ready", "detail": "Generated quotes are locked and changes create a revision."},
        {"label": "Salesforce", "status": "Order Link", "detail": "Order intake opens after customer acceptance."},
        {"label": "SSO", "status": "Ready", "detail": "Future-state access follows enterprise identity controls."},
        {
            "label": "Pricing Controls",
            "status": "Standard",
            "detail": "Segment pricing authority applied.",
        },
    ]


def _requirements_coverage(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    has_warranty = any(item.get("warranty_eligible") for item in items)
    has_approval = any(item.get("approval_required") for item in items)
    return [
        {"label": "Dynamic Pricing", "status": "Covered", "detail": "Segment price drives the recommended quote amount."},
        {"label": "Supplier Overpay", "status": "Controlled", "detail": "Supplier cost is checked before PO handoff."},
        {
            "label": "Approval Controls",
            "status": "Needed" if has_approval else "Clear",
            "detail": "Margin, category, and quote size are evaluated.",
        },
        {
            "label": "Equipment Care",
            "status": "Prompted" if has_warranty else "No Eligible Line",
            "detail": "Attach prompt stays visible through order acceptance.",
        },
        {"label": "Customer Document", "status": "PDF", "detail": "The quote is generated as a customer-ready document."},
        {"label": "Pipeline Visibility", "status": "Open Quote", "detail": "Quote is trackable before OMS order commitment."},
        {
            "label": "Guided Quoting",
            "status": "Available",
            "detail": "Controls support expanding quoting authority safely.",
        },
        {"label": "Autosave", "status": "Enabled", "detail": "Draft state is preserved before final quote staging."},
        {"label": "SSO / Security", "status": "Ready", "detail": "Future state avoids standalone legacy CPQ access risk."},
        {"label": "Legacy CPQ Risk", "status": "Reduced", "detail": "Legacy quotes inform context but are not the destination."},
    ]


def _workflow_steps(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"label": "1. Recommend", "status": f"{len(items)} Lines", "detail": "Build-agent output normalized into quote-ready equipment lines."},
        {"label": "2. Review", "status": "Controls", "detail": "Pricing, approvals, and Equipment Care are checked together."},
        {"label": "3. Generate", "status": "PDF", "detail": "The approved revision becomes a customer-ready document."},
        {"label": "4. Follow Up", "status": "Salesforce", "detail": "The existing order-intake process continues after acceptance."},
    ]


def _current_state_risks() -> list[dict[str, str]]:
    return [
        {"label": "Manual SFTP", "status": "Replaced", "detail": "ERP and OMS data are modeled as automated source feeds."},
        {"label": "Key Person Risk", "status": "Reduced", "detail": "Legacy CPQ remains only as historical quote context."},
        {"label": "Quote Loss", "status": "Autosave", "detail": "Draft quote state is maintained in-app before staging."},
        {"label": "Disconnected Documents", "status": "Unified", "detail": "Quote configuration and PDF generation share one revision history."},
    ]


def _source_lineage() -> list[dict[str, str]]:
    return [
        {"label": "ERP Master", "status": "Fresh", "detail": "Customer, product, and price master."},
        {"label": "OMS Availability", "status": "Fresh", "detail": "Equipment availability, order, PO, and install context."},
        {"label": "Legacy CPQ", "status": "History", "detail": "Prior quotes and conversion context only."},
        {"label": "Agentic CPQ", "status": "Destination", "detail": "Customer-ready PDF and revision history."},
        {"label": "Salesforce Order Link", "status": "Post-Acceptance", "detail": "Existing order intake form remains the handoff."},
    ]


def _bundle_line_insights(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "label": item.get("sku", "Line"),
            "status": "Approval Needed" if item.get("approval_required") else "Ready",
            "detail": item.get("rationale", ""),
        }
        for item in items
    ]


def _score_product(product: dict[str, Any], query: str, scenario: str) -> int:
    lowered = query.lower()
    score = 0
    for tag in _scenario_tags(scenario):
        if tag in product["bundle_tags"]:
            score += 3
    for token in lowered.split():
        if token in product["title"].lower() or token in product["description"].lower():
            score += 1
    if scenario == "operatory" and product["category"] in {"equipment", "sterilization", "software"}:
        score += 2
    if scenario == "imaging" and product["category"] in {"imaging", "software", "services"}:
        score += 2
    if scenario == "reorder" and product["category"] == "consumables":
        score += 2
    if "finance" in lowered or "budget" in lowered:
        score += 1 if product["financing_eligible"] else 0
    return score


def _is_equipment_care_followup(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in ("equipment care", "warranty", "care plan", "protect")) and any(
        term in lowered for term in ("add", "attach", "include", "need", "eligible", "quote")
    )


def _context_lines(
    current_order_lines: list[dict[str, Any]] | None,
    last_recommendation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if current_order_lines:
        return current_order_lines
    if isinstance(last_recommendation, dict):
        items = last_recommendation.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _line_is_warranty_context(line: dict[str, Any]) -> bool:
    product = PRODUCTS_BY_SKU.get(str(line.get("sku", "")), {})
    category = line.get("category") or product.get("category")
    return bool(line.get("warranty_eligible")) or category in {"equipment", "imaging", "sterilization"}


def _recommendation_item_for(
    product: dict[str, Any],
    *,
    account: dict[str, Any],
    segment: str,
    scenario: str,
) -> dict[str, Any]:
    price = recommended_price(product, segment)
    cost = supplier_cost(product)
    margin = gross_margin_pct(price, cost)
    quantity = product["default_quantity"]
    approval_required = _approval_required(product, account, price)
    approval_reason = (
        _approval_reason(product, account, price, margin) if approval_required else ""
    )
    warranty_eligible = _warranty_eligible(product)
    overpay = overpayment_for_line(product["sku"], quantity)
    overpay_amount = round(float(overpay.get("overpay_amount") or 0.0), 2)
    overpay_prevented = overpay_amount > 0
    rationale = (
        f"{product['title']} supports the {scenario} workflow and aligns with "
        f"{account.get('name', 'the account context')}."
    )
    return {
        "sku": product["sku"],
        "title": product["title"],
        "category": product["category"],
        "quantity": quantity,
        "unit_price": price,
        "list_price": product["unit_price"],
        "recommended_price": price,
        "supplier_cost": cost,
        "gross_margin_pct": margin,
        "approval_required": approval_required,
        "approval_reason": approval_reason,
        "warranty_eligible": warranty_eligible,
        "total_price": round(price * quantity, 2),
        "financing_eligible": product["financing_eligible"],
        "supplier_cost_checked": True,
        "overpay_prevented": overpay_prevented,
        "overpay_amount": overpay_amount,
        "legacy_supplier_cost": overpay.get("legacy_cost"),
        "correct_supplier_cost": overpay.get("correct_cost"),
        "overpay_risk": (
            f"Caught ${overpay_amount:,.0f} supplier overpayment vs. legacy CPQ cost."
            if overpay_prevented
            else "Supplier cost checked"
        ),
        "rationale": rationale,
        "confidence": "high" if product["category"] in {"equipment", "imaging", "software"} else "medium",
        "line_insights": _line_insights_for(
            product,
            rationale,
            margin=margin,
            approval_required=approval_required,
            warranty_eligible=warranty_eligible,
        ),
        "insights": _citations_for(product, scenario),
        "citations": _citations_for(product, scenario),
    }


def build_cart_recommendation(
    query: str,
    account_id: str | None = None,
    current_order_lines: list[dict[str, Any]] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    last_recommendation: dict[str, Any] | None = None,
    mode: str = "mock",
) -> dict[str, Any]:
    scenario = _infer_scenario(query)
    budget = _parse_budget(query)
    account = ACCOUNTS_BY_ID.get(account_id or "", {})
    segment = account.get("segment", "mid-market")
    existing_skus = {line.get("sku") for line in (current_order_lines or [])}
    context_lines = _context_lines(current_order_lines, last_recommendation)

    chosen: list[dict[str, Any]] = []
    running_total = 0.0
    followup_warning = ""
    if _is_equipment_care_followup(query) and context_lines:
        protect = PRODUCTS_BY_SKU["SUPPORT-CARE-12"]
        if protect["sku"] in existing_skus:
            followup_warning = "Equipment Care is already in the active quote cart."
        elif any(_line_is_warranty_context(line) for line in context_lines):
            scenario = "protection"
            item = _recommendation_item_for(
                protect,
                account=account,
                segment=segment,
                scenario=scenario,
            )
            chosen.append(item)
            running_total = item["total_price"]
        else:
            followup_warning = "No eligible equipment line is available for Equipment Care in the active quote context."
    else:
        ranked = sorted(
            PRODUCTS,
            key=lambda product: (_score_product(product, query, scenario), -product["unit_price"]),
            reverse=True,
        )

        for product in ranked:
            if product["sku"] in existing_skus:
                continue
            # Equipment Care is auto-attached per eligible equipment line, so never
            # surface a standalone care-plan SKU as its own recommendation.
            if product["sku"] in WARRANTY_SKUS:
                continue
            if scenario == "reorder" and product["category"] != "consumables":
                continue
            if scenario == "imaging" and product["category"] not in {"imaging", "software", "services", "financing"}:
                continue
            if product["category"] == "financing" and budget is not None and running_total < budget * 0.6:
                continue
            projected_total = running_total + (recommended_price(product, segment) * product["default_quantity"])
            if budget is not None and product["unit_price"] > 0 and projected_total > budget and chosen:
                continue
            item = _recommendation_item_for(
                product,
                account=account,
                segment=segment,
                scenario=scenario,
            )
            chosen.append(item)
            running_total += item["total_price"]
            if len(chosen) >= 5:
                break

    # Equipment Care is opt-out: auto-attach a scaled care plan under each eligible
    # equipment line so the rep never has to remember it. The seller can remove it
    # in the workspace. Recompute the running total so it flows into budget checks.
    chosen = attach_default_care_plans(chosen, account)
    running_total = round(sum(float(item.get("total_price") or 0.0) for item in chosen), 2)

    warnings: list[str] = []
    if followup_warning:
        warnings.append(followup_warning)
    if budget is not None and running_total > budget:
        warnings.append(
            f"Draft recommendation is ${running_total:,.0f}, which exceeds the requested budget of ${budget:,.0f}."
        )
    elif budget is not None:
        warnings.append(
            f"Draft recommendation stays inside the requested budget of ${budget:,.0f}; confirm discounts in CPQ."
        )
    if existing_skus:
        warnings.append("Existing cart lines were excluded from the new recommendation to avoid duplicate items.")

    account_hint = ""
    if account:
        account_hint = f" for {account['name']} ({account['specialty']}, {account['growth_stage']})"

    pricing_controls, approval_path, recommended_addons, business_impact = _quote_controls(chosen)
    quote_readiness = _quote_readiness(chosen)
    requirements_coverage = _requirements_coverage(chosen)
    overpay_total = round(sum(float(item.get("overpay_amount") or 0.0) for item in chosen), 2)
    intelligence_signals = _intelligence_signals(chosen, overpay_total)

    return {
        "mode": mode,
        "summary": f"{scenario.title()} quote{account_hint}",
        "bundle_rationale": "Segment price, margin, Equipment Care, and document controls are ready to review.",
        "items": chosen,
        "overpay_prevented_total": overpay_total,
        "intelligence_signals": intelligence_signals,
        "pricing_controls": pricing_controls,
        "approval_path": approval_path,
        "recommended_addons": recommended_addons,
        "business_impact": business_impact,
        "quote_readiness": quote_readiness,
        "line_insights": _bundle_line_insights(chosen),
        "requirements_coverage": requirements_coverage,
        "workflow_steps": _workflow_steps(chosen),
        "current_state_risks": _current_state_risks(),
        "source_lineage": _source_lineage(),
        "source_freshness": SOURCE_FRESHNESS,
        "warnings": warnings,
        "next_steps": [
            "Review approval flags.",
            "Attach Equipment Care where eligible.",
            "Generate the customer quote PDF.",
        ],
        "agent_path": ["OpenAI Agent", "Genie Agent"] if mode != "mock" else ["Mock Engine"],
        "metadata": {
            "scenario": scenario,
            "budget": budget,
            "account_id": account_id,
            "context_turns": len(conversation_history or []),
        },
    }
