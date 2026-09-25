"""Durable domain contracts for goal-to-quote agent plans.

The planner may propose scenarios, but these models deliberately carry only
proposals and references to deterministic recommendation output.  Quote writes
remain the responsibility of the existing CPQ services after an authenticated,
version-bound confirmation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .models import CartRecommendation


class PlanStatus(StrEnum):
    PLANNING = "planning"
    NEEDS_INPUT = "needs_input"
    READY = "ready"
    APPLYING = "applying"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_FOR_PDF = "ready_for_pdf"
    COMPLETED = "completed"
    STALE = "stale"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


TERMINAL_PLAN_STATUSES = frozenset(
    {
        PlanStatus.COMPLETED,
        PlanStatus.STALE,
        PlanStatus.FAILED,
        PlanStatus.CANCELLED,
    }
)
ACTIVE_PLAN_STATUSES = frozenset(set(PlanStatus) - TERMINAL_PLAN_STATUSES)


_ALLOWED_STATUS_TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.PLANNING: frozenset(
        {PlanStatus.NEEDS_INPUT, PlanStatus.READY, PlanStatus.STALE, PlanStatus.FAILED, PlanStatus.CANCELLED}
    ),
    PlanStatus.NEEDS_INPUT: frozenset(
        {PlanStatus.PLANNING, PlanStatus.READY, PlanStatus.STALE, PlanStatus.FAILED, PlanStatus.CANCELLED}
    ),
    PlanStatus.READY: frozenset(
        {
            PlanStatus.PLANNING,
            PlanStatus.APPLYING,
            PlanStatus.AWAITING_APPROVAL,
            PlanStatus.READY_FOR_PDF,
            PlanStatus.STALE,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }
    ),
    PlanStatus.APPLYING: frozenset(
        {
            PlanStatus.AWAITING_APPROVAL,
            PlanStatus.READY_FOR_PDF,
            PlanStatus.COMPLETED,
            PlanStatus.STALE,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }
    ),
    PlanStatus.AWAITING_APPROVAL: frozenset(
        {
            PlanStatus.READY,
            PlanStatus.APPLYING,
            PlanStatus.READY_FOR_PDF,
            PlanStatus.COMPLETED,
            PlanStatus.STALE,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }
    ),
    PlanStatus.READY_FOR_PDF: frozenset(
        {PlanStatus.COMPLETED, PlanStatus.STALE, PlanStatus.FAILED, PlanStatus.CANCELLED}
    ),
    PlanStatus.COMPLETED: frozenset(),
    PlanStatus.STALE: frozenset(),
    PlanStatus.FAILED: frozenset(),
    PlanStatus.CANCELLED: frozenset(),
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _clean_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Value cannot be empty.")
    return cleaned


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(default_factory=lambda: _new_id("step"))
    title: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    detail: str = ""
    sequence: int = Field(default=0, ge=0)
    requires_confirmation: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None

    _clean_step_id = field_validator("step_id")(_clean_required)
    _clean_title = field_validator("title")(_clean_required)


class QuoteScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(default_factory=lambda: _new_id("scenario"))
    title: str
    summary: str = ""
    rationale: str = ""
    recommendation: CartRecommendation | None = None
    recommendation_id: str | None = None
    recommendation_revision: int | None = Field(default=None, ge=1)
    estimated_total: float | None = Field(default=None, ge=0)
    total_delta: float | None = None
    requires_approval: bool = False
    is_recommended: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    _clean_scenario_id = field_validator("scenario_id")(_clean_required)
    _clean_title = field_validator("title")(_clean_required)

    @model_validator(mode="after")
    def populate_recommendation_reference(self) -> "QuoteScenario":
        if self.recommendation is not None:
            if not self.recommendation_id and self.recommendation.recommendation_id:
                self.recommendation_id = self.recommendation.recommendation_id
            if self.recommendation_revision is None and self.recommendation.revision > 0:
                self.recommendation_revision = self.recommendation.revision
        return self


class ConfirmationTokenMetadata(BaseModel):
    """Public metadata accompanying a bearer confirmation token."""

    model_config = ConfigDict(extra="forbid")

    token: str
    token_id: str
    idempotency_key: str
    expires_at: datetime

    _clean_token = field_validator("token")(_clean_required)
    _clean_token_id = field_validator("token_id")(_clean_required)
    _clean_idempotency_key = field_validator("idempotency_key")(_clean_required)


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=lambda: _new_id("proposal"))
    action_type: str = "apply_scenario"
    summary: str
    scenario_id: str | None = None
    recommendation_id: str | None = None
    recommendation_revision: int | None = Field(default=None, ge=1)
    draft_version: int = Field(ge=0)
    plan_revision: int = Field(ge=1)
    idempotency_key: str = Field(default_factory=lambda: _new_id("idem"))
    confirmation: ConfirmationTokenMetadata | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    _clean_proposal_id = field_validator("proposal_id")(_clean_required)
    _clean_action_type = field_validator("action_type")(_clean_required)
    _clean_summary = field_validator("summary")(_clean_required)
    _clean_idempotency_key = field_validator("idempotency_key")(_clean_required)


class QuotePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    plan_id: str = Field(default_factory=lambda: _new_id("plan"))
    account_id: str
    draft_order_id: str
    base_draft_version: int = Field(
        ge=0,
        validation_alias=AliasChoices("base_draft_version", "draft_version"),
    )
    revision: int = Field(default=1, ge=1)
    goal: str
    status: PlanStatus = PlanStatus.PLANNING
    steps: list[PlanStep] = Field(default_factory=list)
    scenarios: list[QuoteScenario] = Field(default_factory=list)
    selected_scenario_id: str | None = None
    action_proposal: ActionProposal | None = None
    created_by: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    _clean_plan_id = field_validator("plan_id")(_clean_required)
    _clean_account_id = field_validator("account_id")(_clean_required)
    _clean_draft_order_id = field_validator("draft_order_id")(_clean_required)
    _clean_goal = field_validator("goal")(_clean_required)

    @field_validator("created_by")
    @classmethod
    def normalize_created_by(cls, value: str) -> str:
        return value.strip().casefold()

    @model_validator(mode="after")
    def validate_scenario_references(self) -> "QuotePlan":
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Scenario IDs must be unique within a plan.")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique within a plan.")
        if self.selected_scenario_id and self.selected_scenario_id not in scenario_ids:
            raise ValueError("Selected scenario is not part of this plan.")
        if (
            self.action_proposal is not None
            and self.action_proposal.scenario_id is not None
            and self.action_proposal.scenario_id not in scenario_ids
        ):
            raise ValueError("Action proposal scenario is not part of this plan.")
        return self

    @property
    def draft_version(self) -> int:
        """Compatibility name used by the planner; persisted as base_draft_version."""

        return self.base_draft_version

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_PLAN_STATUSES


class AgentActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: _new_id("action"))
    plan_id: str
    draft_order_id: str
    account_id: str
    action_type: str
    actor_email: str
    plan_revision: int = Field(ge=1)
    draft_version: int = Field(ge=0)
    idempotency_key: str | None = None
    confirmation_token_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    _clean_action_id = field_validator("action_id")(_clean_required)
    _clean_plan_id = field_validator("plan_id")(_clean_required)
    _clean_draft_order_id = field_validator("draft_order_id")(_clean_required)
    _clean_account_id = field_validator("account_id")(_clean_required)
    _clean_action_type = field_validator("action_type")(_clean_required)

    @field_validator("actor_email")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if not cleaned:
            raise ValueError("Actor email cannot be empty.")
        return cleaned

    @field_validator("idempotency_key", "confirmation_token_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


class ConfirmationTokenClaims(BaseModel):
    """Signed binding checked immediately before a proposed write."""

    model_config = ConfigDict(extra="forbid")

    token_id: str = Field(default_factory=lambda: _new_id("confirm"))
    actor_email: str
    account_id: str
    draft_order_id: str
    draft_version: int = Field(ge=0)
    plan_id: str
    plan_revision: int = Field(ge=1)
    idempotency_key: str
    action_type: str = "apply_scenario"
    issued_at: datetime
    expires_at: datetime

    _clean_token_id = field_validator("token_id")(_clean_required)
    _clean_account_id = field_validator("account_id")(_clean_required)
    _clean_draft_order_id = field_validator("draft_order_id")(_clean_required)
    _clean_plan_id = field_validator("plan_id")(_clean_required)
    _clean_idempotency_key = field_validator("idempotency_key")(_clean_required)
    _clean_action_type = field_validator("action_type")(_clean_required)

    @field_validator("actor_email")
    @classmethod
    def normalize_claim_actor(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if not cleaned:
            raise ValueError("Actor email cannot be empty.")
        return cleaned

    @model_validator(mode="after")
    def validate_lifetime(self) -> "ConfirmationTokenClaims":
        self.issued_at = _utc(self.issued_at)
        self.expires_at = _utc(self.expires_at)
        if self.expires_at <= self.issued_at:
            raise ValueError("Confirmation token expiry must be after issue time.")
        return self


class ConfirmationTokenError(ValueError):
    """Raised when a confirmation token is invalid or no longer usable."""


def issue_confirmation_token(
    *,
    secret: str | bytes,
    actor_email: str,
    account_id: str,
    draft_order_id: str,
    draft_version: int,
    plan_id: str,
    plan_revision: int,
    idempotency_key: str,
    action_type: str = "apply_scenario",
    ttl_seconds: int = 600,
    now: datetime | None = None,
) -> ConfirmationTokenMetadata:
    """Issue an HMAC-signed, short-lived confirmation bound to server state.

    Signature validation does not by itself make a token one-use.  On execution,
    callers append an action with ``confirmation_token_id``; both stores reject a
    second use of that token id and make idempotency-key retries deterministic.
    """

    if ttl_seconds < 1 or ttl_seconds > 3_600:
        raise ValueError("Confirmation token TTL must be between 1 and 3600 seconds.")
    issued_at = _utc(now or datetime.now(UTC))
    claims = ConfirmationTokenClaims(
        actor_email=actor_email,
        account_id=account_id,
        draft_order_id=draft_order_id,
        draft_version=draft_version,
        plan_id=plan_id,
        plan_revision=plan_revision,
        idempotency_key=idempotency_key,
        action_type=action_type,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )
    payload = claims.model_dump(mode="json")
    encoded_payload = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(_secret_bytes(secret), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    token = f"{encoded_payload}.{_b64encode(signature)}"
    return ConfirmationTokenMetadata(
        token=token,
        token_id=claims.token_id,
        idempotency_key=claims.idempotency_key,
        expires_at=claims.expires_at,
    )


def verify_confirmation_token(
    token: str,
    *,
    secret: str | bytes,
    actor_email: str | None = None,
    account_id: str | None = None,
    draft_order_id: str | None = None,
    draft_version: int | None = None,
    plan_id: str | None = None,
    plan_revision: int | None = None,
    idempotency_key: str | None = None,
    action_type: str | None = None,
    now: datetime | None = None,
    allow_expired: bool = False,
) -> ConfirmationTokenClaims:
    """Verify signature, expiry, and any supplied server-owned bindings."""

    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        supplied_signature = _b64decode(encoded_signature)
        expected_signature = hmac.new(
            _secret_bytes(secret), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ConfirmationTokenError("Confirmation token signature is invalid.")
        raw_payload = json.loads(_b64decode(encoded_payload))
        claims = ConfirmationTokenClaims.model_validate(raw_payload)
    except ConfirmationTokenError:
        raise
    except Exception as exc:
        raise ConfirmationTokenError("Confirmation token is malformed.") from exc

    checked_at = _utc(now or datetime.now(UTC))
    if not allow_expired and checked_at >= claims.expires_at:
        raise ConfirmationTokenError("Confirmation token has expired.")

    expected: dict[str, Any] = {
        "actor_email": actor_email.strip().casefold() if actor_email is not None else None,
        "account_id": account_id,
        "draft_order_id": draft_order_id,
        "draft_version": draft_version,
        "plan_id": plan_id,
        "plan_revision": plan_revision,
        "idempotency_key": idempotency_key,
        "action_type": action_type,
    }
    for field_name, value in expected.items():
        if value is not None and getattr(claims, field_name) != value:
            raise ConfirmationTokenError(
                f"Confirmation token does not match {field_name.replace('_', ' ')}."
            )
    return claims


def apply_plan_changes(
    plan: QuotePlan,
    *,
    expected_revision: int,
    now: datetime | None = None,
    **changes: Any,
) -> QuotePlan:
    """Return a validated next revision without mutating the supplied plan."""

    if plan.status in TERMINAL_PLAN_STATUSES:
        raise ValueError(f"Plan {plan.plan_id} is {plan.status.value} and is read-only.")
    if plan.revision != expected_revision:
        raise ValueError(
            f"Plan revision {expected_revision} is stale; current revision is {plan.revision}."
        )
    mutable = {
        "goal",
        "status",
        "steps",
        "scenarios",
        "selected_scenario_id",
        "action_proposal",
        "error_message",
        "metadata",
    }
    unknown = set(changes) - mutable
    if unknown:
        raise ValueError(f"Plan fields are immutable or unknown: {', '.join(sorted(unknown))}.")
    if not changes:
        raise ValueError("At least one plan field must be updated.")

    next_status = PlanStatus(changes.get("status", plan.status))
    if next_status != plan.status and next_status not in _ALLOWED_STATUS_TRANSITIONS[plan.status]:
        raise ValueError(
            f"Plan cannot transition from {plan.status.value} to {next_status.value}."
        )
    payload = plan.model_dump(mode="python")
    payload.update(changes)
    payload.update(
        {
            "status": next_status,
            "revision": plan.revision + 1,
            "updated_at": _utc(now or datetime.now(UTC)),
        }
    )
    return QuotePlan.model_validate(payload)


def _secret_bytes(secret: str | bytes) -> bytes:
    value = secret.encode("utf-8") if isinstance(secret, str) else secret
    if not value:
        raise ValueError("Confirmation token secret cannot be empty.")
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
