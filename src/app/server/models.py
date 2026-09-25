from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator


class EvidenceStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class GenieCitation(BaseModel):
    citation_id: str = ""
    title: str = ""
    uri: str = ""
    snippet: str = ""
    source: str = "genie"


class GenieSqlAttachment(BaseModel):
    attachment_id: str = ""
    sql: str = ""
    description: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    truncated: bool = False
    error_code: str | None = None


class EvidenceFreshness(BaseModel):
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "live"
    detail: str = "Returned by Genie for this request."


class TemporaryKnowledgeFallback(BaseModel):
    """Reviewed guidance used only when live Genie Agent document retrieval cannot finish."""

    used: bool = False
    source: str = "none"
    reason: str = ""
    answer: str = ""


class GenieEvidenceEnvelope(BaseModel):
    """Typed, role-projected evidence returned by the single intelligence tool."""

    status: EvidenceStatus
    answer: str = ""
    source: str = "genie"
    conversation_id: str | None = None
    message_id: str | None = None
    citations: list[GenieCitation] = Field(default_factory=list)
    sql_attachments: list[GenieSqlAttachment] = Field(default_factory=list)
    freshness: EvidenceFreshness = Field(default_factory=EvidenceFreshness)
    truncated: bool = False
    error_code: str | None = None
    error_message: str | None = None
    knowledge_fallback: TemporaryKnowledgeFallback = Field(
        default_factory=TemporaryKnowledgeFallback
    )

    def public_payload(self) -> dict[str, Any]:
        """Return the typed contract plus the legacy first-query aliases used by the UI."""

        payload = self.model_dump(mode="json")
        first = self.sql_attachments[0] if self.sql_attachments else None
        payload.update(
            {
                "text": self.answer,
                "sql": first.sql if first else "",
                "description": first.description if first else "",
                "columns": list(first.columns) if first else [],
                "rows": list(first.rows) if first else [],
                "error": self.status in {EvidenceStatus.ERROR, EvidenceStatus.UNAVAILABLE},
            }
        )
        return payload


class SourceEvidence(BaseModel):
    source: str
    title: str
    detail: str


class PricingControl(BaseModel):
    label: str
    status: str
    detail: str = ""


class RecommendedAddon(BaseModel):
    sku: str
    title: str
    reason: str
    status: str = "eligible"


class SourceFreshness(BaseModel):
    source: str
    status: str
    detail: str


class RecommendedLineItem(BaseModel):
    sku: str
    title: str
    category: str
    quantity: int = 1
    unit_price: float
    list_price: float | None = None
    recommended_price: float | None = None
    supplier_cost: float | None = None
    gross_margin_pct: float | None = None
    approval_required: bool = False
    approval_reason: str = ""
    warranty_eligible: bool = False
    total_price: float | None = None
    financing_eligible: bool = False
    supplier_cost_checked: bool = False
    overpay_prevented: bool = False
    overpay_amount: float = 0.0
    legacy_supplier_cost: float | None = None
    correct_supplier_cost: float | None = None
    overpay_risk: str = ""
    pricing_guardrail: str = ""
    attach_recommendation: str = ""
    is_addon: bool = False
    covers_sku: str | None = None
    rationale: str
    confidence: str = "medium"
    line_insights: list[PricingControl] = Field(default_factory=list)
    insights: list[SourceEvidence] = Field(default_factory=list)
    citations: list[SourceEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_total_price(self) -> "RecommendedLineItem":
        if self.list_price is None:
            self.list_price = self.unit_price
        if self.recommended_price is None:
            self.recommended_price = self.unit_price
        if self.total_price is None:
            self.total_price = round(self.unit_price * self.quantity, 2)
        return self


class CartRecommendation(BaseModel):
    mode: str
    apply_mode: Literal["add", "replace"] = "add"
    summary: str
    bundle_rationale: str = ""
    items: list[RecommendedLineItem] = Field(default_factory=list)
    pricing_controls: list[PricingControl] = Field(default_factory=list)
    approval_path: list[PricingControl] = Field(default_factory=list)
    recommended_addons: list[RecommendedAddon] = Field(default_factory=list)
    business_impact: list[PricingControl] = Field(default_factory=list)
    quote_readiness: list[PricingControl] = Field(default_factory=list)
    line_insights: list[PricingControl] = Field(default_factory=list)
    requirements_coverage: list[PricingControl] = Field(default_factory=list)
    workflow_steps: list[PricingControl] = Field(default_factory=list)
    current_state_risks: list[PricingControl] = Field(default_factory=list)
    source_lineage: list[PricingControl] = Field(default_factory=list)
    source_freshness: list[SourceFreshness] = Field(default_factory=list)
    intelligence_signals: list[PricingControl] = Field(default_factory=list)
    manager_insights: list[PricingControl] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    agent_path: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    win_probability: float | None = None
    follow_up_action: str = ""
    conversion_risk: str = ""
    equipment_care_prompt: str = ""
    pdf_ready: bool = True
    salesforce_order_link_ready: bool = True
    overpay_prevented_total: float = 0.0
    recommendation_id: str = ""
    revision: int = 0
    draft_version: int | None = None
    evidence: list[GenieEvidenceEnvelope] = Field(default_factory=list)


class DraftLineItem(BaseModel):
    sku: str
    title: str
    category: str
    quantity: int = 1
    unit_price: float
    list_price: float | None = None
    recommended_price: float | None = None
    supplier_cost: float | None = None
    gross_margin_pct: float | None = None
    approval_required: bool = False
    approval_reason: str = ""
    warranty_eligible: bool = False
    total_price: float | None = None
    overpay_amount: float = 0.0
    legacy_supplier_cost: float | None = None
    correct_supplier_cost: float | None = None
    is_addon: bool = False
    covers_sku: str | None = None

    @model_validator(mode="after")
    def ensure_total_price(self) -> "DraftLineItem":
        if self.list_price is None:
            self.list_price = self.unit_price
        if self.recommended_price is None:
            self.recommended_price = self.unit_price
        if self.total_price is None:
            self.total_price = round(self.unit_price * self.quantity, 2)
        return self


class DraftOrder(BaseModel):
    draft_order_id: str
    account_id: str
    status: str = "draft"
    line_items: list[DraftLineItem] = Field(default_factory=list)
    subtotal: float = 0.0
    grand_total: float = 0.0
    quote_id: str | None = None
    owner_email: str = ""
    version: int = 0
    revision_number: int = Field(default=1, ge=1)
    parent_draft_order_id: str | None = None
    source_quote_id: str | None = None


class QuotePdfSettings(BaseModel):
    """Customer-document controls managed by CPQ administrators."""

    layout: Literal["classic", "compact"] = "classic"
    show_list_prices: bool = True
    show_savings: bool = True
    brand_name: str = Field(default="QUOTE WORKSPACE", min_length=1, max_length=80)
    document_title: str = Field(default="Customer quote", min_length=1, max_length=100)
    accent_color: str = Field(default="#FF3621", pattern=r"^#[0-9A-Fa-f]{6}$")
    footer_text: str = Field(
        default="Powered by Databricks",
        min_length=1,
        max_length=180,
    )
    terms_text: str = Field(
        default=(
            "Pricing is valid for 30 days and is subject to final availability, "
            "applicable taxes, shipping, and mutually agreed implementation timing. "
            "This quote supersedes all earlier drafts."
        ),
        min_length=1,
        max_length=4_000,
    )
    validity_days: int = Field(default=30, ge=1, le=365)


class CPQBehaviorSettings(BaseModel):
    """Application-owned commercial controls exposed by the lite admin pane."""

    approval_threshold: float = Field(default=80_000.0, gt=0, le=100_000_000)
    # A 100% default preserves the pre-admin behavior, where margin/category rules
    # governed line approval but there was no independent seller-discount cap.
    max_seller_discount_pct: float = Field(default=100.0, ge=0, le=100)
    allow_seller_price_edits: bool = True
    auto_attach_care_plan: bool = True


class CPQAdminSettings(BaseModel):
    """Persisted, singleton CPQ configuration returned by the admin API."""

    pdf: QuotePdfSettings = Field(default_factory=QuotePdfSettings)
    behavior: CPQBehaviorSettings = Field(default_factory=CPQBehaviorSettings)


class ConversationTurn(BaseModel):
    role: str
    content: str


class SellerQueryRequest(BaseModel):
    query: str
    account_id: str | None = None
    view_role: str = "seller"
    intent: Literal["auto", "research", "build"] = "auto"
    genie_conversation_id: str | None = None
    draft_order_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    current_order_lines: list[DraftLineItem] = Field(default_factory=list)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    recommendation_context: dict[str, Any] = Field(default_factory=dict)


class PlanMutationRequest(BaseModel):
    expected_plan_revision: int = Field(ge=1)
    expected_draft_version: int = Field(ge=0)
    view_role: str = "seller"


class PlanResumeRequest(PlanMutationRequest):
    input: str = Field(min_length=1, max_length=4_000)


class PlanConfirmRequest(PlanMutationRequest):
    confirmation_token: str = Field(min_length=1, max_length=8_000)
    idempotency_key: str = Field(min_length=1, max_length=240)


class RecommendationViewRequest(BaseModel):
    draft_order_id: str
    view_role: str = "seller"


class FollowupRequest(BaseModel):
    draft_order_id: str
    account_id: str | None = None
    view_role: str = "seller"


FollowupSuggestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]


class FollowupResponse(BaseModel):
    suggestions: list[FollowupSuggestion] = Field(default_factory=list, max_length=4)


class GenieAskRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class GenieFollowupRequest(BaseModel):
    question: str
    answer: str = ""
    columns: list[str] = Field(default_factory=list)


class AddLineRequest(BaseModel):
    draft_order_id: str
    sku: str
    quantity: int = 1
    account_id: str | None = None
    view_role: str = "seller"
    expected_version: int | None = Field(default=None, ge=0)


class SetPriceRequest(BaseModel):
    draft_order_id: str
    sku: str
    unit_price: float
    account_id: str | None = None
    view_role: str = "seller"
    expected_version: int | None = Field(default=None, ge=0)


class CreateDraftOrderRequest(BaseModel):
    account_id: str
    line_items: list[DraftLineItem] = Field(default_factory=list)
    view_role: str = "seller"


class UpdateDraftOrderRequest(BaseModel):
    line_items: list[DraftLineItem] = Field(default_factory=list)
    expected_version: int | None = Field(default=None, ge=0)
    view_role: str = "seller"


class CreateRevisionRequest(BaseModel):
    view_role: str = "seller"


class ApplyRecommendationRequest(BaseModel):
    recommendation_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    mode: Literal["add", "replace"] = "add"
    view_role: str = "seller"


class QuoteDraftRequest(BaseModel):
    draft_order_id: str
    seller_id: str = "seller-demo"
    view_role: str = "seller"
