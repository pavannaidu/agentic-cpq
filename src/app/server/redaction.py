from __future__ import annotations

import copy
import re
from typing import Any

# Buy-side / margin fields that must never reach a seller- or customer-facing view.
SENSITIVE_LINE_FIELDS = (
    "supplier_cost",
    "legacy_supplier_cost",
    "correct_supplier_cost",
    "gross_margin_pct",
)

# View roles that are allowed to see supplier cost, margin, and overpayment dollars.
PRIVILEGED_VIEW_ROLES = {"manager", "demo"}
_SENSITIVE_PROSE = re.compile(
    r"\b(?:buy[-\s]?side|costs?|cogs|floors?|gm|margins?|markups?|profits?|wholesale|"
    r"legacy[-\s]+(?:wholesale|supplier)[-\s]+cost|negotiated[-\s]+cost|"
    r"over[-\s]?pay(?:ment|ing)?s?)\b",
    re.IGNORECASE,
)
_PERCENTAGE_PROSE = re.compile(
    r"(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)\s*%|"
    r"\b(?:percent(?:age)?|pct)\b",
    re.IGNORECASE,
)
_PLAN_SENSITIVE_PROSE = re.compile(
    r"\b(?:supplier|wholesale|internal|legacy|negotiated|buy[-\s]?side)\s+costs?\b|"
    r"\b(?:gross\s+)?margins?\b|"
    r"\b(?:margin\s+floor|cogs|over[-\s]?pay(?:ment|ing)?s?)\b",
    re.IGNORECASE,
)
_SENSITIVE_COLUMN_NAMES = {
    "approvalfloorpct",
    "cogs",
    "correctsuppliercost",
    "costbasis",
    "grossmargin",
    "grossmarginpct",
    "legacycost",
    "legacysuppliercost",
    "legacywholesalecost",
    "margin",
    "marginfloor",
    "marginfloorpct",
    "marginpct",
    "negotiatedcost",
    "overpay",
    "overpayamount",
    "overpayment",
    "overpayperunit",
    "suppliercost",
    "unitcost",
}
_CONTROL_COLLECTIONS = (
    "pricing_controls",
    "approval_path",
    "business_impact",
    "quote_readiness",
    "line_insights",
    "requirements_coverage",
    "workflow_steps",
    "current_state_risks",
    "source_lineage",
    "intelligence_signals",
)


def normalize_view_role(view_role: str | None) -> str:
    role = (view_role or "").strip().lower()
    return role if role in PRIVILEGED_VIEW_ROLES or role == "seller" else "seller"


def _normalized_field(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _contains_sensitive_prose(value: object) -> bool:
    text = str(value or "")
    return bool(_SENSITIVE_PROSE.search(text) or _PERCENTAGE_PROSE.search(text))


def _safe_prose(value: object, *, replacement: str = "") -> str:
    """Remove complete sentences/lines that contain seller-restricted facts."""

    text = str(value or "").strip()
    if not text or not _contains_sensitive_prose(text):
        return text
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    retained = [
        part.strip()
        for part in parts
        if part.strip() and not _contains_sensitive_prose(part)
    ]
    return " ".join(retained).strip() or replacement


def _safe_plan_prose(value: object, *, replacement: str = "") -> str:
    """Keep customer-facing price/cost language while removing internal economics."""

    text = str(value or "").strip()
    if not text or not (
        _PLAN_SENSITIVE_PROSE.search(text) or _PERCENTAGE_PROSE.search(text)
    ):
        return text
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    retained = [
        part.strip()
        for part in parts
        if part.strip()
        and not _PLAN_SENSITIVE_PROSE.search(part)
        and not _PERCENTAGE_PROSE.search(part)
    ]
    return " ".join(retained).strip() or replacement


def _generic_status(value: object) -> str:
    """Keep operational meaning when a status itself contains a restricted fact."""

    text = str(value or "").casefold()
    if any(token in text for token in ("need", "required", "review", "below", "blocked")):
        return "Review"
    if "route" in text:
        return "Routed"
    if any(token in text for token in ("clear", "above", "pass", " ok")) or text == "ok":
        return "Clear"
    if "control" in text:
        return "Controlled"
    if "monitor" in text:
        return "Monitored"
    if "data" in text:
        return "Needs Data"
    return "Checked"


def _generic_label(value: object) -> str:
    text = str(value or "").casefold()
    return "Approval" if "approval" in text else "Pricing Check"


def _seller_prose_fallback(key: object, value: object) -> str:
    field = _normalized_field(key)
    if field == "approvalreason":
        return "Additional approval is required."
    if field == "status":
        return _generic_status(value)
    if field == "label":
        return _generic_label(value)
    if field in {"answer", "text"}:
        return "Governed guidance is available."
    if field in {"title", "source"}:
        return "Governed guidance"
    if field == "summary":
        return "Quote recommendation"
    if field in {"bundlerationale", "rationale", "whyitfits"}:
        return "Recommended for the selected account."
    if field in {"detail", "description", "reason", "snippet"}:
        return "Internal pricing checks are complete."
    if field in {"uri", "url", "sql", "query", "finalmessageexcerpt"}:
        return ""
    return "Restricted commercial details were withheld."


def _sanitize_seller_tree(value: object, *, key: object = "") -> object:
    """Last-mile safety sweep for prose-bearing recommendation extensions."""

    if isinstance(value, dict):
        sanitized: dict[object, object] = {}
        for child_key, child_value in value.items():
            normalized = _normalized_field(child_key)
            if normalized in _SENSITIVE_COLUMN_NAMES:
                if isinstance(child_value, bool):
                    sanitized[child_key] = False
                elif normalized.startswith("overpay") and isinstance(child_value, (int, float)):
                    sanitized[child_key] = 0.0
                else:
                    sanitized[child_key] = None
                continue
            sanitized[child_key] = _sanitize_seller_tree(child_value, key=child_key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_seller_tree(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_seller_tree(item, key=key) for item in value)
    if isinstance(value, str):
        return _safe_prose(value, replacement=_seller_prose_fallback(key, value))
    return value


def _sanitize_seller_plan_tree(value: object, *, key: object = "") -> object:
    if isinstance(value, dict):
        sanitized: dict[object, object] = {}
        for child_key, child_value in value.items():
            normalized = _normalized_field(child_key)
            if normalized in _SENSITIVE_COLUMN_NAMES:
                sanitized[child_key] = None
                continue
            sanitized[child_key] = _sanitize_seller_plan_tree(
                child_value,
                key=child_key,
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize_seller_plan_tree(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_seller_plan_tree(item, key=key) for item in value)
    if isinstance(value, str):
        return _safe_plan_prose(value, replacement="Restricted commercial details were withheld.")
    return value


def _sanitize_control(control: object) -> object:
    if not isinstance(control, dict):
        return control
    original_label = control.get("label", "")
    sensitive_label = _contains_sensitive_prose(original_label)
    control["label"] = _safe_prose(
        original_label,
        replacement=_generic_label(original_label),
    )
    original_status = control.get("status", "")
    control["status"] = (
        _generic_status(original_status)
        if sensitive_label
        else _safe_prose(original_status, replacement=_generic_status(original_status))
    )
    if "detail" in control:
        control["detail"] = _safe_prose(
            control.get("detail"),
            replacement=(
                "Additional approval review is required."
                if control["label"] == "Approval" and control["status"] in {"Review", "Routed"}
                else "Internal pricing checks are complete."
            ),
        )
    return control


def _redact_table(table: dict[str, Any]) -> None:
    columns = [str(column) for column in table.get("columns", [])]
    keep_indexes = [
        index
        for index, column in enumerate(columns)
        if _normalized_field(column) not in _SENSITIVE_COLUMN_NAMES
    ]
    table["columns"] = [columns[index] for index in keep_indexes]
    table["rows"] = [
        [row[index] for index in keep_indexes if index < len(row)]
        for row in table.get("rows", [])
        if isinstance(row, list)
    ]


def _redact_evidence(evidence: object) -> None:
    if not isinstance(evidence, dict):
        return

    evidence["answer"] = _safe_prose(
        evidence.get("answer"),
        replacement="Governed guidance is available.",
    )
    if "text" in evidence:
        evidence["text"] = evidence["answer"]
    fallback = evidence.get("knowledge_fallback")
    if isinstance(fallback, dict):
        fallback["answer"] = _safe_prose(
            fallback.get("answer"),
            replacement="Governed guidance is available.",
        )
    for citation in evidence.get("citations", []):
        if isinstance(citation, dict):
            citation["snippet"] = _safe_prose(
                citation.get("snippet"),
                replacement="Governed guidance is available.",
            )
    for attachment in evidence.get("sql_attachments", []):
        if not isinstance(attachment, dict):
            continue
        _redact_table(attachment)
        attachment["sql"] = ""
        attachment["description"] = ""

    # Keep the legacy first-query aliases consistent with the typed attachment.
    first = next(
        (item for item in evidence.get("sql_attachments", []) if isinstance(item, dict)),
        None,
    )
    if first is not None:
        evidence["sql"] = ""
        evidence["description"] = ""
        evidence["columns"] = list(first.get("columns", []))
        evidence["rows"] = list(first.get("rows", []))
    elif "columns" in evidence or "rows" in evidence:
        _redact_table(evidence)
        evidence["sql"] = ""
        evidence["description"] = ""


def redact_line_items_for_view(order_payload: dict[str, Any], view_role: str | None) -> dict[str, Any]:
    """Strip buy-side fields from a draft order's line_items for the seller view."""
    if normalize_view_role(view_role) != "seller":
        return order_payload
    redacted = copy.deepcopy(order_payload)
    for line in redacted.get("line_items", []):
        if not isinstance(line, dict):
            continue
        for field in SENSITIVE_LINE_FIELDS:
            if field in line:
                line[field] = None
        if "overpay_amount" in line:
            line["overpay_amount"] = 0.0
        line["approval_reason"] = _safe_prose(
            line.get("approval_reason"),
            replacement=(
                "Additional approval is required."
                if line.get("approval_required")
                else ""
            ),
        )
    return redacted


def redact_quote_payload_for_view(
    quote_payload: dict[str, Any],
    view_role: str | None,
) -> dict[str, Any]:
    """Strip buy-side fields from the nested customer-document payload."""

    if normalize_view_role(view_role) != "seller":
        return quote_payload
    redacted = copy.deepcopy(quote_payload)
    draft = redacted.get("quote_document")
    if not isinstance(draft, dict):
        # Compatibility for quote payloads created before the PDF workflow migration.
        draft = next(
            (
                value
                for key, value in redacted.items()
                if key.endswith("_quote_draft") and isinstance(value, dict)
            ),
            None,
        )
    if not isinstance(draft, dict):
        return redacted
    for line in draft.get("equipment_lines", []):
        if not isinstance(line, dict):
            continue
        line["supplier_cost"] = None
        line["gross_margin_pct"] = None
    return redacted


def redact_conversation_for_view(
    turns: list[dict[str, Any]],
    view_role: str | None,
) -> list[dict[str, Any]]:
    """Project stored free-text turns before reusing them as seller model context."""

    projected = copy.deepcopy(turns)
    if normalize_view_role(view_role) != "seller":
        return projected
    for turn in projected:
        if not isinstance(turn, dict):
            continue
        turn["content"] = _safe_prose(
            turn.get("content"),
            replacement="Internal commercial details were withheld.",
        )
    return projected


def redact_recommendation_for_view(payload: dict[str, Any], view_role: str | None) -> dict[str, Any]:
    """Return a view-appropriate copy of a recommendation.

    Managers/demo see everything. Sellers get supplier cost, margin, and the
    overpayment dollars stripped — the values a customer-facing or rep surface
    must not expose. The prevention itself still happened server-side (the PO
    uses the negotiated cost); we only hide the buy-side figures.
    """
    if normalize_view_role(view_role) != "seller":
        return payload

    redacted = copy.deepcopy(payload)
    redacted["goal"] = _safe_plan_prose(
        redacted.get("goal"),
        replacement="Prepare a quote for the selected account.",
    )
    redacted["error_message"] = _safe_plan_prose(
        redacted.get("error_message"),
        replacement="The quote plan could not be completed.",
    )
    redacted["created_by"] = ""
    redacted["overpay_prevented_total"] = 0.0

    for item in redacted.get("items", []):
        if not isinstance(item, dict):
            continue
        for field in SENSITIVE_LINE_FIELDS:
            if field in item:
                item[field] = None
        item["overpay_amount"] = 0.0
        item["overpay_prevented"] = False
        item["overpay_risk"] = "Internal pricing checks are complete."
        item["approval_reason"] = _safe_prose(
            item.get("approval_reason"),
            replacement=(
                "Additional approval is required."
                if item.get("approval_required")
                else ""
            ),
        )
        item["line_insights"] = [
            _sanitize_control(insight)
            for insight in item.get("line_insights", [])
            if isinstance(insight, dict)
        ]

    for evidence in redacted.get("evidence", []):
        _redact_evidence(evidence)

    # Retain safe operational state while replacing restricted labels, values,
    # and details throughout every control-shaped recommendation surface.
    for key in _CONTROL_COLLECTIONS:
        redacted[key] = [
            _sanitize_control(control)
            for control in redacted.get(key, [])
            if isinstance(control, dict)
        ]

    # This collection is manager-only by contract and commonly contains a
    # percentage-bearing score even when its label is otherwise innocuous.
    redacted["manager_insights"] = []

    redacted.setdefault("metadata", {})["view_role"] = "seller"
    sanitized = _sanitize_seller_tree(redacted)
    return sanitized if isinstance(sanitized, dict) else redacted


def redact_quote_plan_for_view(
    payload: dict[str, Any],
    view_role: str | None,
) -> dict[str, Any]:
    """Project persisted plan scenarios without weakening confirmation metadata."""

    if normalize_view_role(view_role) != "seller":
        return payload
    redacted = copy.deepcopy(payload)
    redacted["goal"] = _safe_plan_prose(
        redacted.get("goal"),
        replacement="Prepare a quote for the selected account.",
    )
    redacted["error_message"] = _safe_plan_prose(
        redacted.get("error_message"),
        replacement="The quote plan could not be completed.",
    )
    redacted["created_by"] = ""
    for scenario in redacted.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        recommendation = scenario.get("recommendation")
        if isinstance(recommendation, dict):
            scenario["recommendation"] = redact_recommendation_for_view(
                recommendation,
                "seller",
            )
        for field in ("title", "summary", "rationale"):
            if field in scenario:
                scenario[field] = _safe_plan_prose(
                    scenario.get(field),
                    replacement=(
                        "Quote option" if field == "title" else "Recommended for this account."
                    ),
                )
        metadata = scenario.get("metadata")
        if isinstance(metadata, dict):
            scenario["metadata"] = _sanitize_seller_plan_tree(metadata)
    metadata = redacted.get("metadata")
    if isinstance(metadata, dict):
        redacted["metadata"] = _sanitize_seller_plan_tree(metadata)
    for step in redacted.get("steps", []):
        if isinstance(step, dict) and "detail" in step:
            step["detail"] = _safe_plan_prose(
                step.get("detail"),
                replacement="Governed quote checks are complete.",
            )
    proposal = redacted.get("action_proposal")
    if isinstance(proposal, dict):
        proposal["summary"] = _safe_plan_prose(
            proposal.get("summary"),
            replacement="Confirm the selected quote action.",
        )
        proposal_payload = proposal.get("payload")
        if isinstance(proposal_payload, dict):
            proposal["payload"] = _sanitize_seller_plan_tree(proposal_payload)
    return redacted
