from __future__ import annotations

import logging
import re
from typing import Any

try:  # Support both package imports in the app and top-level imports in tests.
    from ..agentic_cpq_demo.cpq import attach_default_care_plans
    from ..agentic_cpq_demo.demo_data import (
        WARRANTY_SKUS,
        build_warranty_eligibility_rows,
        care_plan_eligible,
        warranty_rules_from_rows,
    )
    from . import lakebase
    from .models import DraftLineItem
except ImportError:  # pragma: no cover - exercised by legacy test import path.
    import importlib.util
    import sys
    import types
    from pathlib import Path

    app_demo_dir = Path(__file__).resolve().parents[1] / "agentic_cpq_demo"
    app_demo_pkg = "_agentic_cpq_demo_app"
    if app_demo_pkg not in sys.modules:
        pkg = types.ModuleType(app_demo_pkg)
        pkg.__path__ = [str(app_demo_dir)]
        sys.modules[app_demo_pkg] = pkg
    cpq_spec = importlib.util.spec_from_file_location(f"{app_demo_pkg}.cpq", app_demo_dir / "cpq.py")
    if cpq_spec is None or cpq_spec.loader is None:
        raise
    cpq_module = importlib.util.module_from_spec(cpq_spec)
    sys.modules[cpq_spec.name] = cpq_module
    cpq_spec.loader.exec_module(cpq_module)
    attach_default_care_plans = cpq_module.attach_default_care_plans
    # cpq's relative `from .demo_data import ...` registered the demo_data module.
    demo_data_module = sys.modules[f"{app_demo_pkg}.demo_data"]
    build_warranty_eligibility_rows = demo_data_module.build_warranty_eligibility_rows
    warranty_rules_from_rows = demo_data_module.warranty_rules_from_rows
    care_plan_eligible = demo_data_module.care_plan_eligible
    WARRANTY_SKUS = demo_data_module.WARRANTY_SKUS

    from server import lakebase
    from server.models import DraftLineItem

logger = logging.getLogger(__name__)

OPENAI_AGENTS_SDK_PROVIDER = "openai_agents_sdk"


class ConversationalAgentOutput(RuntimeError):
    """Raised when the build agent answers in prose instead of quote JSON."""

    def __init__(
        self,
        *,
        answer: str,
        query: str,
        endpoint_name: str,
        agent_provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("Build agent returned a conversational answer instead of a quote.")
        self.answer = answer.strip()
        self.query = query
        self.endpoint_name = endpoint_name
        self.agent_provider = agent_provider
        self.details = details or {}

    def payload(self) -> dict[str, Any]:
        provider = self.agent_provider or OPENAI_AGENTS_SDK_PROVIDER
        payload: dict[str, Any] = {
            "mode": "agent-conversation",
            "answer": self.answer,
            "query": self.query,
            "agent_provider": provider,
            "metadata": {"endpoint_name": self.endpoint_name, "agent_provider": provider},
        }
        details = dict(self.details)
        metadata = details.pop("metadata", None)
        payload.update(details)
        if isinstance(metadata, dict):
            payload["metadata"].update(metadata)
        return payload
# --------------------------------------------------------------------------- #
# Reference-data accessors — sourced from Lakebase cpq_ref synced tables
# (cached in lakebase). No static/mock catalog is read at runtime.
# --------------------------------------------------------------------------- #
def account_lookup() -> dict[str, dict[str, Any]]:
    return {a["account_id"]: a for a in lakebase.get_accounts()}


def account_names() -> dict[str, str]:
    return {a["account_id"]: a["name"] for a in lakebase.get_accounts()}


def products_by_sku() -> dict[str, dict[str, Any]]:
    return {p["sku"]: p for p in lakebase.get_products()}


def warranty_rules_by_sku() -> dict[str, dict[str, Any]]:
    """Equipment Care rules indexed by product SKU — the single source the whole server
    uses for eligibility, the specific warranty code, plan name, and rate.

    Reads the Lakebase-synced ``warranty_eligibility`` table (cached ~5 min) so the
    demo is data-driven and editable without a redeploy. Falls back to the in-memory
    seed if the table is unavailable or hasn't picked up the newer columns yet, so
    behavior is always well-defined."""
    try:
        rows = lakebase.get_warranty_eligibility()
    except Exception:  # table missing / older sync / connection blip
        rows = []
    return warranty_rules_from_rows(rows or build_warranty_eligibility_rows())


def _segment_pricing_index() -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["sku"], r["segment"]): r for r in lakebase.get_segment_pricing()}


def _price_book_index() -> dict[str, dict[str, Any]]:
    return {r["sku"]: r for r in lakebase.get_price_book()}


def gross_margin_pct(price: float, cost: float) -> float:
    if not price or price <= 0:
        return 0.0
    return round(((price - cost) / price) * 100, 1)


def recommended_price(product: dict[str, Any], segment: str) -> float:
    idx = _segment_pricing_index()
    row = idx.get((product["sku"], segment)) or idx.get((product["sku"], "mid-market"))
    if row and row.get("recommended_price") is not None:
        return float(row["recommended_price"])
    return float(product.get("unit_price") or 0.0)


def supplier_cost(product: dict[str, Any]) -> float:
    idx = _segment_pricing_index()
    row = idx.get((product["sku"], "mid-market")) or next(
        (v for k, v in idx.items() if k[0] == product["sku"]), None
    )
    if row and row.get("supplier_cost") is not None:
        return float(row["supplier_cost"])
    pb = _price_book_index().get(product["sku"])
    return float(pb["negotiated_cost"]) if pb and pb.get("negotiated_cost") is not None else 0.0


def overpayment_for_line(sku: str, quantity: int = 1) -> dict[str, Any]:
    pb = _price_book_index().get(sku)
    if not pb:
        return {"legacy_cost": None, "correct_cost": None, "overpay_amount": 0.0}
    qty = max(1, int(quantity or 1))
    per_unit = float(pb.get("overpay_per_unit") or 0.0)
    return {
        "legacy_cost": pb.get("legacy_wholesale_cost"),
        "correct_cost": pb.get("negotiated_cost"),
        "overpay_amount": round(max(per_unit, 0.0) * qty, 2),
    }
def build_catalog_line(
    sku: str,
    *,
    quantity: int,
    account_id: str | None,
    max_seller_discount_pct: float = 100.0,
) -> dict[str, Any] | None:
    """Build a fully-priced, catalog-authoritative quote line for a manual add
    (same pricing/governance rules the agent path uses)."""
    product = products_by_sku().get(sku)
    if product is None:
        return None
    account = account_lookup().get(account_id or "", {})
    segment = account.get("segment", "mid-market")
    qty = max(1, int(quantity or 1))
    price = recommended_price(product, segment)
    cost = supplier_cost(product)
    margin = gross_margin_pct(price, cost)
    approval_required = _approval_required(
        product,
        account,
        price,
        max_seller_discount_pct=max_seller_discount_pct,
    )
    overpay = overpayment_for_line(sku, qty)
    return {
        "sku": sku,
        "title": product["title"],
        "category": product["category"],
        "quantity": qty,
        "unit_price": price,
        "list_price": product["unit_price"],
        "recommended_price": price,
        "supplier_cost": cost,
        "gross_margin_pct": margin,
        "approval_required": approval_required,
        "approval_reason": (
            _approval_reason(
                product,
                account,
                price,
                margin,
                max_seller_discount_pct=max_seller_discount_pct,
            )
            if approval_required
            else ""
        ),
        "warranty_eligible": _warranty_eligible(product),
        "total_price": round(price * qty, 2),
        "overpay_amount": round(float(overpay.get("overpay_amount") or 0.0), 2),
        "legacy_supplier_cost": overpay.get("legacy_cost"),
        "correct_supplier_cost": overpay.get("correct_cost"),
    }


def reprice_catalog_line(
    sku: str,
    *,
    unit_price: float,
    quantity: int,
    account_id: str | None,
    max_seller_discount_pct: float = 100.0,
) -> dict[str, Any] | None:
    """Reprice a quote line at a rep-entered net price, recomputing margin and
    approval from the catalog rules (real CPQ: net edit -> margin -> approval).
    Supplier overpayment is buy-side, so it is unaffected by the sell price."""
    product = products_by_sku().get(sku)
    if product is None:
        return None
    account = account_lookup().get(account_id or "", {})
    qty = max(1, int(quantity or 1))
    price = round(max(float(unit_price), 0.0), 2)
    cost = supplier_cost(product)
    margin = gross_margin_pct(price, cost)
    approval_required = _approval_required(
        product,
        account,
        price,
        max_seller_discount_pct=max_seller_discount_pct,
    )
    overpay = overpayment_for_line(sku, qty)
    return {
        "sku": sku,
        "title": product["title"],
        "category": product["category"],
        "quantity": qty,
        "unit_price": price,
        "list_price": product["unit_price"],
        "recommended_price": recommended_price(product, account.get("segment", "mid-market")),
        "supplier_cost": cost,
        "gross_margin_pct": margin,
        "approval_required": approval_required,
        "approval_reason": (
            _approval_reason(
                product,
                account,
                price,
                margin,
                max_seller_discount_pct=max_seller_discount_pct,
            )
            if approval_required
            else ""
        ),
        "warranty_eligible": _warranty_eligible(product),
        "total_price": round(price * qty, 2),
        "overpay_amount": round(float(overpay.get("overpay_amount") or 0.0), 2),
        "legacy_supplier_cost": overpay.get("legacy_cost"),
        "correct_supplier_cost": overpay.get("correct_cost"),
    }


def _recommendation_from_structured_output(
    structured: dict[str, Any],
    *,
    final_text: str,
    output: list[dict[str, Any]],
    query: str,
    account_id: str | None,
    current_order_lines: list[DraftLineItem],
    endpoint_name: str,
    apply_mode: str = "add",
    auto_attach_care_plan: bool = True,
    max_seller_discount_pct: float = 100.0,
) -> dict[str, Any]:
    account = account_lookup().get(account_id or "", {})
    existing_skus = {line.sku for line in current_order_lines}
    replace_existing = apply_mode == "replace"
    items: list[dict[str, Any]] = []
    raw_items = [raw_item for raw_item in structured.get("items", []) if isinstance(raw_item, dict)]
    for raw_item in raw_items:
        sku = str(raw_item.get("sku", "")).strip()
        if not sku or (not replace_existing and sku in existing_skus):
            continue
        items.append(
            _structured_item_from_agent(
                raw_item,
                account=account,
                max_seller_discount_pct=max_seller_discount_pct,
            )
        )

    warnings: list[str] = []
    if existing_skus and items and not replace_existing:
        warnings.append("Existing draft-quote items were omitted from the new live recommendation.")
    if not items and not (existing_skus and raw_items):
        warnings.append("The build agent returned structured guidance, but no cart-ready SKUs were parsed.")

    # Equipment Care is modeled as a scaled plan attached per covered equipment line.
    # When the quote has eligible equipment, drop any flat protection line the
    # agent returned on its own and attach the scaled per-unit care plans, so the
    # live path matches the rest of the app (indented child, priced as a % of the
    # equipment it covers). Only a real equipment line is ever stripped-proof:
    # protection detection is limited to non-capital lines. If the agent asked
    # for coverage but there is no equipment to attach to, keep its line as-is.
    if auto_attach_care_plan:
        capital_categories = {"equipment", "imaging", "sterilization"}
        warranty_rules = warranty_rules_by_sku()
        has_eligible_equipment = any(
            str(item.get("category", "")) in capital_categories for item in items
        )
        has_agent_protection = any(
            _looks_like_protection_line(
                str(item.get("sku", "")),
                str(item.get("title", "")),
                str(item.get("rationale", "")),
            )
            for item in items
        )
        if has_eligible_equipment:
            items = [
                item
                for item in items
                if str(item.get("category", "")) in capital_categories
                or not _looks_like_protection_line(
                    str(item.get("sku", "")),
                    str(item.get("title", "")),
                    str(item.get("rationale", "")),
                )
            ]
            items = attach_default_care_plans(items, account, rules=warranty_rules)
        elif not has_agent_protection:
            items = attach_default_care_plans(items, account, rules=warranty_rules)

    pricing_controls, approval_path, recommended_addons, business_impact = _quote_controls(items)
    quote_readiness = _quote_readiness(items)
    reconciliation_notes = _quote_reconciliation_notes(structured, items)
    intelligence_signals = _intelligence_signals(structured, items)
    manager_insights = _manager_insights(structured, items)
    return {
        "mode": OPENAI_AGENTS_SDK_PROVIDER,
        "summary": _clean_structured_text(structured.get("summary")) or _build_agent_summary(account_id=account_id, items=items),
        "bundle_rationale": _clean_structured_text(structured.get("bundle_rationale")) or _default_bundle_rationale(account_id=account_id, items=items),
        "items": items,
        "pricing_controls": pricing_controls,
        "approval_path": approval_path,
        "recommended_addons": recommended_addons,
        "business_impact": business_impact,
        "quote_readiness": quote_readiness,
        "line_insights": _bundle_line_insights(items),
        "requirements_coverage": _requirements_coverage(items),
        "workflow_steps": _workflow_steps(items),
        "current_state_risks": _current_state_risks(),
        "source_lineage": _source_lineage() + reconciliation_notes,
        "source_freshness": lakebase.get_source_freshness(),
        "intelligence_signals": intelligence_signals,
        "manager_insights": manager_insights,
        "warnings": warnings,
        "next_steps": _structured_next_steps(structured),
        "agent_path": _agent_path(output),
        "win_probability": _normalized_probability(structured.get("win_probability")),
        "follow_up_action": _clean_structured_text(structured.get("follow_up_action")) or _default_follow_up_action(items),
        "conversion_risk": _clean_structured_text(structured.get("conversion_risk")) or _default_conversion_risk(items),
        "equipment_care_prompt": _clean_structured_text(structured.get("equipment_care_prompt")) or _default_equipment_care_prompt(items),
        "pdf_ready": _bool_or_default(structured.get("pdf_ready"), True),
        "salesforce_order_link_ready": _bool_or_default(structured.get("salesforce_order_link_ready"), True),
        "overpay_prevented_total": round(sum(float(item.get("overpay_amount") or 0.0) for item in items), 2),
        "metadata": {
            "account_id": account_id,
            "endpoint_name": endpoint_name,
            "output_events": len(output),
            "final_message_excerpt": final_text[:600],
            "query": query,
            "parsed_from": "agent_structured_output",
            "quote_subtotal": _quote_subtotal(items),
            "agent_quote_subtotal": _optional_positive_float(structured.get("quote_subtotal")),
        },
    }


def _structured_item_from_agent(
    raw_item: dict[str, Any],
    *,
    account: dict[str, Any] | None = None,
    max_seller_discount_pct: float = 100.0,
) -> dict[str, Any]:
    sku = _clean_structured_text(raw_item.get("sku"))
    product = products_by_sku().get(sku)
    rationale = (
        _clean_structured_text(raw_item.get("rationale"))
        or _clean_structured_text(raw_item.get("why_it_fits"))
        or _clean_structured_text(raw_item.get("fit"))
    )
    quantity = _positive_int(raw_item.get("quantity"), 1)
    unit_price, total_price, recommended = _normalize_agent_prices(raw_item, quantity)

    # The catalog is authoritative for every commercial fact. The agent chooses
    # SKU, quantity, and narrative; known SKU pricing, margin, approval, and
    # warranty classification are always recomputed server-side.
    if product is not None:
        title = product["title"]
        category = product["category"]
        segment = (account or {}).get("segment", "mid-market")
        unit_price = recommended_price(product, segment)
        total_price = round(unit_price * quantity, 2)
        recommended = unit_price
        supplier = supplier_cost(product)
        margin = gross_margin_pct(unit_price, supplier)
        warranty_eligible = _warranty_eligible(product)
        approval_required = _approval_required(
            product,
            account or {},
            unit_price,
            max_seller_discount_pct=max_seller_discount_pct,
        )
        approval_reason = (
            _approval_reason(
                product,
                account or {},
                unit_price,
                margin,
                max_seller_discount_pct=max_seller_discount_pct,
            )
            if approval_required
            else ""
        )
        overpay = overpayment_for_line(sku, quantity)
        if not rationale:
            rationale = f"{title} fits this account's quote motion with segment pricing and supplier-cost controls applied."
    else:
        title = _clean_structured_text(raw_item.get("title")) or sku
        category = _clean_structured_text(raw_item.get("category")) or _infer_agent_category(sku, title, rationale)
        supplier = _optional_positive_float(raw_item.get("supplier_cost"))
        margin = _optional_positive_float(raw_item.get("gross_margin_pct") or raw_item.get("margin"))
        approval_required = _bool_or_default(raw_item.get("approval_required"), False)
        approval_reason = _clean_structured_text(raw_item.get("approval_reason"))
        warranty_eligible = _bool_or_default(
            raw_item.get("warranty_eligible"),
            _looks_like_protection_line(sku, title, rationale),
        )
        overpay = {"legacy_cost": None, "correct_cost": None, "overpay_amount": 0.0}
        if not rationale:
            rationale = f"{title} was recommended by the build agent for this quote."

    overpay_amount = round(float(overpay.get("overpay_amount") or 0.0), 2)
    overpay_prevented = overpay_amount > 0
    overpay_risk = (
        f"Caught ${overpay_amount:,.0f} supplier overpayment vs. legacy CPQ cost."
        if overpay_prevented
        else _clean_structured_text(raw_item.get("overpay_risk")) or "Supplier cost checked"
    )

    line_insights = _normalize_structured_insights(raw_item.get("line_insights"))
    if not any(insight.get("label") == "Fit" for insight in line_insights):
        line_insights.append({"label": "Fit", "status": "Ready", "detail": rationale})
    if not any(insight.get("label") == "Control" for insight in line_insights):
        detail = "Segment price and supplier cost checked before staging."
        if approval_required:
            detail = approval_reason or "Tiered approval control applied."
        elif warranty_eligible:
            detail = "Protection coverage stays visible through quote acceptance."
        line_insights.append({"label": "Control", "status": "Ready", "detail": detail})
    source = {"source": "Build agent", "title": title, "detail": rationale}
    return {
        "sku": sku,
        "title": title,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "list_price": (product["unit_price"] if product is not None else _optional_positive_float(raw_item.get("list_price"))),
        "recommended_price": recommended,
        "supplier_cost": supplier,
        "gross_margin_pct": margin,
        "approval_required": approval_required,
        "approval_reason": approval_reason,
        "warranty_eligible": warranty_eligible,
        "total_price": total_price,
        "financing_eligible": (product["financing_eligible"] if product is not None else _bool_or_default(raw_item.get("financing_eligible"), False)),
        "supplier_cost_checked": supplier is not None,
        "overpay_prevented": overpay_prevented,
        "overpay_amount": overpay_amount,
        "legacy_supplier_cost": overpay.get("legacy_cost"),
        "correct_supplier_cost": overpay.get("correct_cost"),
        "overpay_risk": overpay_risk,
        "pricing_guardrail": _clean_structured_text(raw_item.get("pricing_guardrail")),
        "attach_recommendation": _clean_structured_text(raw_item.get("attach_recommendation")),
        "rationale": rationale,
        "confidence": _clean_structured_text(raw_item.get("confidence")) or "high",
        "line_insights": line_insights,
        "insights": [source],
        "citations": [source],
    }


def _approval_reason(
    product: dict[str, Any],
    account: dict[str, Any],
    price: float,
    margin: float,
    max_seller_discount_pct: float = 100.0,
) -> str:
    """Human-readable reason matching the rule that actually fired in _approval_required."""
    discount_pct = _seller_discount_pct(product, price)
    if discount_pct > max_seller_discount_pct:
        return (
            f"Seller discount {discount_pct:.1f}% exceeds the configured "
            f"{max_seller_discount_pct:.1f}% limit."
        )
    capital_categories = {"equipment", "imaging", "sterilization"}
    if product["category"] in capital_categories and margin < 24:
        return f"Gross margin {margin:.1f}% is below the {product['category'].title()} approval floor of 24%."
    if account.get("segment") == "enterprise" and product["unit_price"] >= 15000:
        return f"Enterprise-segment capital purchase over ${product['unit_price']:,.0f} requires manager review."
    return "Tiered quote control flagged this line for review."


def _normalize_agent_prices(raw_item: dict[str, Any], quantity: int) -> tuple[float, float, float]:
    unit = _optional_positive_float(raw_item.get("unit_price"))
    line_total = _optional_positive_float(raw_item.get("line_total") or raw_item.get("total_price"))
    recommended = _optional_positive_float(raw_item.get("recommended_price") or raw_item.get("price"))

    if line_total is None and unit is not None:
        line_total = round(unit * quantity, 2)
    if line_total is None and recommended is not None:
        line_total = recommended
    if line_total is None:
        line_total = 0.0

    if unit is None:
        unit = round(line_total / quantity, 2) if quantity > 0 else line_total
    if recommended is None:
        recommended = line_total
    return unit, line_total, recommended


def _quote_subtotal(items: list[dict[str, Any]]) -> float:
    return round(sum(float(item.get("total_price") or 0) for item in items), 2)


def _quote_reconciliation_notes(structured: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    subtotal = _quote_subtotal(items)
    agent_subtotal = _optional_positive_float(structured.get("quote_subtotal"))
    if agent_subtotal is not None and abs(agent_subtotal - subtotal) >= 0.01:
        notes.append(
            {
                "label": "Subtotal Reconciled",
                "status": "Line Totals",
                "detail": f"Agent quote_subtotal ${agent_subtotal:,.0f} was reconciled to ${subtotal:,.0f} from item line totals.",
            }
        )

    summary = _clean_structured_text(structured.get("summary"))
    summary_amounts = _extract_dollar_amounts(summary)
    mismatches = [amount for amount in summary_amounts if abs(amount - subtotal) >= 0.01]
    if mismatches:
        notes.append(
            {
                "label": "Summary Total Checked",
                "status": "Reconciled",
                "detail": f"Summary amount ${mismatches[0]:,.0f} did not match line subtotal ${subtotal:,.0f}.",
            }
        )
    return notes


def _extract_dollar_amounts(text: str) -> list[float]:
    amounts: list[float] = []
    for match in re.finditer(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text):
        value = match.group(1).replace(",", "")
        try:
            amounts.append(float(value))
        except ValueError:
            continue
    return amounts


def _structured_next_steps(structured: dict[str, Any]) -> list[str]:
    steps = structured.get("next_steps")
    if not isinstance(steps, list):
        return [
            "Review approval flags.",
            "Attach Equipment Care where eligible.",
            "Generate the customer quote PDF.",
        ]
    cleaned = [_clean_structured_text(step) for step in steps]
    return [step for step in cleaned if step][:4]


def _normalize_structured_insights(raw_insights: Any) -> list[dict[str, str]]:
    if isinstance(raw_insights, dict):
        raw_insights = [
            {"label": str(label), "status": "Ready", "detail": str(detail)}
            for label, detail in raw_insights.items()
        ]
    if not isinstance(raw_insights, list):
        return []
    normalized = []
    for insight in raw_insights:
        if not isinstance(insight, dict):
            continue
        label = _clean_structured_text(insight.get("label"))
        detail = _clean_structured_text(insight.get("detail") or insight.get("note") or insight.get("value"))
        status = _clean_structured_text(insight.get("status")) or "Ready"
        if label and (detail or status):
            normalized.append({"label": label, "status": status, "detail": detail})
    return normalized


def _clean_structured_text(value: Any) -> str:
    if value is None:
        return ""
    return _clean_markdown(str(value))


def _optional_positive_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalized_probability(value: Any) -> float | None:
    parsed = _optional_positive_float(value)
    if parsed is None:
        return None
    if 0 <= parsed <= 1:
        return round(parsed * 100, 1)
    return min(parsed, 100)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return parsed if parsed > 0 else int(default)


def _bool_or_default(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "needed", "required", "eligible"}:
            return True
        if lowered in {"false", "no", "clear", "not eligible"}:
            return False
    return default


def _infer_agent_category(sku: str, title: str, rationale: str) -> str:
    text = f"{sku} {title} {rationale}".lower()
    if _looks_like_protection_line(sku, title, rationale):
        return "services"
    if any(token in text for token in ("service", "onboarding", "support", "care")):
        return "services"
    if any(token in text for token in ("cbct", "imaging", "sensor", "scanner", "x-ray")):
        return "imaging"
    if any(token in text for token in ("software", "practice management", "cloud platform")):
        return "software"
    if any(token in text for token in ("steril", "autoclave")):
        return "sterilization"
    if any(token in text for token in ("consumable", "supply", "glove")):
        return "consumables"
    return "equipment"


def _looks_like_protection_line(sku: str, title: str, rationale: str) -> bool:
    # An exact Equipment Care code (any family) is definitive; otherwise fall back to a
    # keyword heuristic for free-form live-agent output.
    if sku in WARRANTY_SKUS:
        return True
    text = f"{sku} {title} {rationale}".lower()
    return any(token in text for token in ("equipment care", "protect", "warranty", "coverage", "care plan"))


def _clean_markdown(text: str) -> str:
    cleaned = re.sub(r"[#*`_]", "", text).strip(" -:\t|")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _build_agent_summary(*, account_id: str | None, items: list[dict[str, Any]]) -> str:
    account_name = account_names().get(account_id or "", "the selected account")
    if items:
        return f"Prepared {len(items)} recommendation{'s' if len(items) != 1 else ''} for {account_name} from governed agent output."
    return f"Prepared a live recommendation for {account_name}."


def _agent_path(output: list[dict[str, Any]]) -> list[str]:
    path = ["OpenAI Agents SDK"]
    tool_map = {
        "genie_intelligence": "Genie Agent",
        "web_search": "Databricks Web Search",
    }
    for item in output:
        if item.get("type") != "function_call":
            continue
        tool_name = tool_map.get(item.get("name", ""), item.get("name", ""))
        if tool_name and tool_name not in path:
            path.append(tool_name)
    return path


def _default_bundle_rationale(
    *,
    account_id: str | None,
    items: list[dict[str, Any]],
) -> str:
    if items:
        titles = [str(item.get("title", "")).strip() for item in items if item.get("title")]
        title_phrase = ", ".join(titles[:3])
        return f"{title_phrase} keeps the quote aligned to the governed recommendation and ready for customer review."
    account_name = account_names().get(account_id or "", "the selected account")
    return f"This recommendation is tailored to {account_name} and prioritizes fit, rollout readiness, and commercial clarity."


def _quote_controls(items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    total = sum(float(item.get("total_price", 0)) for item in items)
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    margins = _known_margins(items)
    min_margin = min(margins) if margins else None
    pricing_controls = [
        {
            "label": "Margin",
            "status": "OK" if min_margin is not None and min_margin >= 24 else "Checked",
            "detail": f"Lowest margin {min_margin:.1f}%" if min_margin is not None else "Margin is shown when governed pricing supplies it.",
        },
        {"label": "Price", "status": "Segment", "detail": "Recommended price uses customer segment."},
    ]
    approval_path = [
        {
            "label": "Approval",
            "status": "Needed" if approvals or total > 80000 else "Clear",
            "detail": "Manager review required." if approvals or total > 80000 else "No next-level approval triggered.",
        }
    ]
    # Reflect the actual per-family Equipment Care plans attached to the quote (distinct
    # warranty codes), not a single hardcoded code. Fall back to a generic eligible
    # prompt when equipment is eligible but no plan is attached yet.
    plan_addons: dict[str, str] = {}
    for line in items:
        if line.get("is_addon") and line.get("sku"):
            plan_addons.setdefault(str(line["sku"]), str(line.get("title") or "Equipment Care"))
    if plan_addons:
        recommended_addons = [
            {"sku": sku, "title": title, "reason": "Auto-attached Equipment Care for covered equipment.", "status": "attached"}
            for sku, title in plan_addons.items()
        ]
    elif warranty_items:
        recommended_addons = [
            {"sku": "CARE-PLAN-ELIGIBLE", "title": "Equipment Care", "reason": "Eligible equipment in quote.", "status": "eligible"}
        ]
    else:
        recommended_addons = []
    business_impact = [
        {"label": "Overpay Risk", "status": "Reduced", "detail": "Supplier cost checked before quote stage."},
        {"label": "Quote PDF", "status": "Ready", "detail": "Customer-ready document can be generated in the app."},
    ]
    return pricing_controls, approval_path, recommended_addons, business_impact


def _intelligence_signals(structured: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, str]]:
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    supplier_checked = _bool_or_default(
        structured.get("supplier_cost_checked"),
        bool(items) and all(item.get("supplier_cost_checked") for item in items),
    )
    overpay_total = round(sum(float(item.get("overpay_amount") or 0.0) for item in items), 2)
    overpay_prevented = overpay_total > 0
    win_probability = _normalized_probability(structured.get("win_probability"))
    return [
        {
            "label": "Supplier Cost",
            "status": "Checked" if supplier_checked else "Needs Data",
            "detail": "Genie supplied supplier cost and margin facts." if supplier_checked else "Supplier cost should be confirmed by Genie.",
        },
        {
            "label": "Overpay",
            "status": f"${overpay_total:,.0f} Saved" if overpay_prevented else "Monitored",
            "detail": (
                f"Price check caught ${overpay_total:,.0f} in supplier overpayment vs. legacy CPQ cost."
                if overpay_prevented
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
            "detail": _default_equipment_care_prompt(items),
        },
        {
            "label": "Win Signal",
            "status": f"{win_probability:.0f}%" if win_probability is not None else "Pending",
            "detail": _clean_structured_text(structured.get("conversion_risk")) or _default_conversion_risk(items),
        },
        {
            "label": "Quote PDF",
            "status": "Ready" if _bool_or_default(structured.get("pdf_ready"), True) else "Blocked",
            "detail": "Customer-ready document generation is available.",
        },
    ]


def _manager_insights(structured: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, str]]:
    win_probability = _normalized_probability(structured.get("win_probability"))
    return [
        {
            "label": "Win Probability",
            "status": f"{win_probability:.0f}%" if win_probability is not None else "Not Scored",
            "detail": "Score should come from historical quote conversion once model-backed scoring is connected.",
        },
        {
            "label": "Follow-up Priority",
            "status": "High" if any(item.get("approval_required") for item in items) else "Standard",
            "detail": _clean_structured_text(structured.get("follow_up_action")) or _default_follow_up_action(items),
        },
        {
            "label": "Conversion Risk",
            "status": _clean_structured_text(structured.get("conversion_risk")) or _default_conversion_risk(items),
            "detail": "Manager view ties open-quote follow-up to the conversion recovery opportunity.",
        },
    ]


def _default_follow_up_action(items: list[dict[str, Any]]) -> str:
    if any(item.get("approval_required") for item in items):
        return "Route approval, then generate the customer quote PDF with Equipment Care visible."
    return "Generate the customer quote PDF and schedule a follow-up before the quote stalls."


def _default_conversion_risk(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No quote lines scored yet"
    if any(item.get("approval_required") for item in items):
        return "Approval delay"
    if any(item.get("warranty_eligible") for item in items):
        return "Attach decision pending"
    return "Standard follow-up"


def _default_equipment_care_prompt(items: list[dict[str, Any]]) -> str:
    if any(item.get("warranty_eligible") for item in items):
        return "Keep Equipment Care visible through customer review."
    return "Review attach eligibility before quote acceptance."


def _known_margins(items: list[dict[str, Any]]) -> list[float]:
    margins: list[float] = []
    for item in items:
        margin = _optional_positive_float(item.get("gross_margin_pct"))
        if margin is not None:
            margins.append(margin)
    return margins


def _quote_readiness(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    total = sum(float(item.get("total_price", 0)) for item in items)
    approvals = [item for item in items if item.get("approval_required")]
    warranty_items = [item for item in items if item.get("warranty_eligible")]
    margins = _known_margins(items)
    min_margin = min(margins) if margins else None
    return [
        {
            "label": "Margin",
            "status": "OK" if min_margin is not None and min_margin >= 24 else "Checked",
            "detail": f"Lowest line margin {min_margin:.1f}%." if min_margin is not None else "Margin is shown when governed pricing supplies it.",
        },
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
    line_count = len(items)
    return [
        {"label": "1. Recommend", "status": f"{line_count} Lines", "detail": "Agent output normalized into quote-ready equipment lines."},
        {"label": "2. Review", "status": "Controls", "detail": "Pricing, approvals, and Equipment Care are checked together."},
        {"label": "3. Generate", "status": "PDF", "detail": "The approved revision becomes a customer-ready document."},
        {"label": "4. Follow Up", "status": "Salesforce", "detail": "The existing order-intake process continues after acceptance."},
    ]


def _current_state_risks() -> list[dict[str, str]]:
    return [
        {"label": "Manual SFTP", "status": "Replaced", "detail": "ERP and OMS data are modeled as automated source feeds."},
        {"label": "Key Person Risk", "status": "Reduced", "detail": "legacy CPQ remains only as historical quote context."},
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


def _approval_required(
    product: dict[str, Any],
    account: dict[str, Any],
    price: float,
    max_seller_discount_pct: float = 100.0,
) -> bool:
    if price <= 0:
        return False
    if _seller_discount_pct(product, price) > max_seller_discount_pct:
        return True
    margin = gross_margin_pct(price, supplier_cost(product))
    if product["category"] in {"equipment", "imaging", "sterilization"} and margin < 24:
        return True
    return account.get("segment") == "enterprise" and product["unit_price"] >= 15000


def _seller_discount_pct(product: dict[str, Any], price: float) -> float:
    list_price = float(product.get("unit_price") or 0.0)
    if list_price <= 0 or price >= list_price:
        return 0.0
    return round(((list_price - price) / list_price) * 100, 2)


def _warranty_eligible(product: dict[str, Any]) -> bool:
    """Table-driven eligibility: does this SKU carry an Equipment Care plan? Resolved
    from the ``warranty_eligibility`` table (with in-memory fallback)."""
    return care_plan_eligible(product.get("sku", ""), warranty_rules_by_sku())
