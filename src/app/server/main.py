from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

SHARED_ROOT = Path(__file__).resolve().parents[2] / "shared"
if SHARED_ROOT.exists() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from agentic_cpq_demo.cpq import attach_default_care_plans, build_quote_payload, care_plan_line_for
from .agent_plans import (
    ActionProposal,
    ConfirmationTokenError,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    QuotePlan,
    QuoteScenario,
    TERMINAL_PLAN_STATUSES,
    issue_confirmation_token,
    verify_confirmation_token,
)
from .auth import ActorContext, actor_from_request
from .config import get_settings
from .databricks_api import (
    ConversationalAgentOutput,
    build_catalog_line,
    reprice_catalog_line,
    warranty_rules_by_sku,
)
from .openai_agent import OpenAIAgentClient, encode_genie_conversation_reference
from .models import (
    AddLineRequest,
    ApplyRecommendationRequest,
    CartRecommendation,
    CPQAdminSettings,
    ConversationTurn,
    CreateDraftOrderRequest,
    CreateRevisionRequest,
    DraftLineItem,
    DraftOrder,
    FollowupRequest,
    FollowupResponse,
    PlanConfirmRequest,
    PlanMutationRequest,
    PlanResumeRequest,
    QuotePdfSettings,
    QuoteDraftRequest,
    RecommendationViewRequest,
    SellerQueryRequest,
    SetPriceRequest,
    UpdateDraftOrderRequest,
)
from . import lakebase
from .redaction import (
    redact_conversation_for_view,
    redact_line_items_for_view,
    redact_quote_payload_for_view,
    redact_quote_plan_for_view,
    redact_recommendation_for_view,
)
from .quote_pdf import build_quote_pdf
from .state import DraftConflict, DraftOrderStore

logger = logging.getLogger("agentic_cpq")
settings = get_settings()
static_root = Path(__file__).resolve().parents[1] / "static"

# Use Lakebase (durable Postgres) when the App injected PG* env vars; otherwise
# fall back to the in-memory store so local dev and tests work with no database.
_lakebase_active = lakebase.lakebase_configured()
store = lakebase.LakebaseDraftOrderStore() if _lakebase_active else DraftOrderStore()
agent_client = OpenAIAgentClient(settings)
QUOTE_APPROVAL_THRESHOLD = 80_000.0


def _resolve_plan_confirmation_secret(app_settings) -> str | bytes:
    """Require a stable injected secret in deployed plan-enabled apps."""

    configured = str(getattr(app_settings, "plan_confirmation_secret", "") or "").strip()
    if configured:
        return configured
    if bool(getattr(app_settings, "plans_enabled", False)) and bool(
        getattr(app_settings, "is_databricks_app", False)
    ):
        raise RuntimeError(
            "AGENTIC_CPQ_PLAN_CONFIRMATION_SECRET is required when quote plans are enabled "
            "in a deployed Databricks App."
        )
    # Local development and tests use an unguessable process-private key. Tokens
    # intentionally become invalid after a local process restart.
    return secrets.token_bytes(32)


# This value is never returned directly or supplied to an agent/tool.
_plan_confirmation_secret: str | bytes = _resolve_plan_confirmation_secret(settings)


def _actor(http_request: Request) -> ActorContext:
    return actor_from_request(http_request, settings)


def _admin_actor(http_request: Request) -> ActorContext:
    actor = _actor(http_request)
    if not actor.can_manage:
        raise HTTPException(
            status_code=403,
            detail="Manager access is required to configure CPQ settings.",
        )
    return actor


def _current_admin_settings() -> CPQAdminSettings:
    return store.get_admin_settings()


def _owned_order(draft_order_id: str, actor: ActorContext):
    try:
        order = store.get(draft_order_id)
        if not order.owner_email:
            order = store.claim_owner(draft_order_id, actor.email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    except DraftConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if order.owner_email.casefold() != actor.email.casefold() and not actor.can_manage:
        raise HTTPException(
            status_code=403,
            detail="The signed-in user cannot access this draft order.",
        )
    return order


def _conflict(exc: DraftConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _plan_payload(plan: QuotePlan, view_role: str) -> dict[str, object]:
    return redact_quote_plan_for_view(plan.model_dump(mode="json"), view_role)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _load_plan(plan_id: str, actor: ActorContext) -> tuple[QuotePlan, DraftOrder]:
    try:
        plan = store.get_plan(plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Quote plan not found") from exc
    order = _owned_order(plan.draft_order_id, actor)
    if plan.account_id != order.account_id:
        raise HTTPException(status_code=409, detail="Quote plan account no longer matches its draft.")
    return plan, order


def _plan_bound_draft_version(plan: QuotePlan) -> int:
    applied = plan.metadata.get("applied_draft_version")
    if isinstance(applied, int) and plan.status in {
        PlanStatus.AWAITING_APPROVAL,
        PlanStatus.READY_FOR_PDF,
        PlanStatus.COMPLETED,
    }:
        return applied
    return plan.base_draft_version


def _mark_plan_stale(
    plan: QuotePlan,
    *,
    current_draft_version: int,
    actor_email: str,
) -> QuotePlan:
    if plan.status in TERMINAL_PLAN_STATUSES:
        return plan
    metadata = copy.deepcopy(plan.metadata)
    metadata["stale_expected_draft_version"] = _plan_bound_draft_version(plan)
    metadata["stale_current_draft_version"] = current_draft_version
    try:
        stale = store.update_plan(
            plan.plan_id,
            expected_revision=plan.revision,
            status=PlanStatus.STALE,
            action_proposal=None,
            error_message="The quote changed after this plan was prepared.",
            metadata=metadata,
        )
        store.append_plan_action(
            stale.plan_id,
            "plan_stale",
            actor_email,
            plan_revision=stale.revision,
            draft_version=current_draft_version,
            payload={
                "expected_draft_version": metadata["stale_expected_draft_version"],
                "current_draft_version": current_draft_version,
            },
        )
        return stale
    except (DraftConflict, KeyError):
        try:
            return store.get_plan(plan.plan_id)
        except KeyError:
            return plan


def _validate_plan_mutation(
    plan: QuotePlan,
    order: DraftOrder,
    *,
    expected_plan_revision: int,
    expected_draft_version: int,
    actor_email: str,
) -> None:
    bound_version = _plan_bound_draft_version(plan)
    if order.version != bound_version:
        _mark_plan_stale(
            plan,
            current_draft_version=order.version,
            actor_email=actor_email,
        )
        raise DraftConflict(
            f"Draft changed after this plan was prepared; current version is {order.version}."
        )
    if plan.status in TERMINAL_PLAN_STATUSES:
        raise DraftConflict(f"Plan {plan.plan_id} is {plan.status.value} and is read-only.")
    if plan.revision != expected_plan_revision:
        raise DraftConflict(
            f"Plan revision {expected_plan_revision} is stale; current revision is {plan.revision}."
        )
    if order.version != expected_draft_version:
        raise DraftConflict(
            f"Draft version {expected_draft_version} is stale; current version is {order.version}."
        )


def _selected_scenario(plan: QuotePlan) -> QuoteScenario:
    scenario = next(
        (
            item
            for item in plan.scenarios
            if item.scenario_id == plan.selected_scenario_id
        ),
        None,
    )
    if scenario is None:
        raise DraftConflict("Select a quote scenario before confirming this plan.")
    if scenario.recommendation is None or not scenario.recommendation_id:
        raise DraftConflict("The selected scenario has no stored recommendation to apply.")
    return scenario


def _confirmation_proposal(
    *,
    plan_id: str,
    scenario: QuoteScenario,
    actor_email: str,
    account_id: str,
    draft_order_id: str,
    draft_version: int,
    plan_revision: int,
    action_type: str = "apply_scenario",
) -> ActionProposal:
    if action_type == "generate_pdf":
        summary = "Generate the confirmed quote PDF"
        payload: dict[str, object] = {"quote_status": "ready_for_pdf"}
    else:
        summary = f"Apply {scenario.title}"
        payload = {
            "apply_mode": scenario.recommendation.apply_mode if scenario.recommendation else "add",
            "recommendation_id": scenario.recommendation_id,
            "recommendation_revision": scenario.recommendation_revision,
        }
    idempotency_key = (
        f"{action_type}:{plan_id}:{scenario.scenario_id}:r{plan_revision}"
    )
    confirmation = issue_confirmation_token(
        secret=_plan_confirmation_secret,
        actor_email=actor_email,
        account_id=account_id,
        draft_order_id=draft_order_id,
        draft_version=draft_version,
        plan_id=plan_id,
        plan_revision=plan_revision,
        idempotency_key=idempotency_key,
        action_type=action_type,
    )
    return ActionProposal(
        action_type=action_type,
        summary=summary,
        scenario_id=scenario.scenario_id,
        recommendation_id=scenario.recommendation_id,
        recommendation_revision=scenario.recommendation_revision,
        draft_version=draft_version,
        plan_revision=plan_revision,
        idempotency_key=idempotency_key,
        confirmation=confirmation,
        payload=payload,
    )


def _canonicalize_plan_scenarios(
    plan: QuotePlan,
    *,
    persisted_plan_id: str,
    draft_version: int,
) -> tuple[list[QuoteScenario], str | None]:
    """Persist full deterministic recommendations before exposing plan references."""

    selected_id = plan.selected_scenario_id
    if not selected_id and plan.scenarios:
        selected_id = next(
            (item.scenario_id for item in plan.scenarios if item.is_recommended),
            plan.scenarios[0].scenario_id,
        )
    ordered = sorted(
        enumerate(plan.scenarios),
        key=lambda pair: pair[1].scenario_id == selected_id,
    )
    canonical_by_index: dict[int, QuoteScenario] = {}
    for index, scenario in ordered:
        recommendation = scenario.recommendation
        if recommendation is None:
            canonical_by_index[index] = scenario.model_copy(deep=True)
            continue
        recommendation_payload = recommendation.model_dump(mode="json")
        recommendation_payload.setdefault("metadata", {})
        recommendation_payload["metadata"].update(
            {
                "plan_id": persisted_plan_id,
                "scenario_id": scenario.scenario_id,
            }
        )
        stored_payload = store.set_latest_recommendation(
            plan.draft_order_id,
            recommendation_payload,
            draft_version=draft_version,
        )
        stored_recommendation = CartRecommendation.model_validate(stored_payload)
        canonical_by_index[index] = scenario.model_copy(
            update={
                "recommendation": stored_recommendation,
                "recommendation_id": stored_recommendation.recommendation_id,
                "recommendation_revision": stored_recommendation.revision,
            },
            deep=True,
        )
    return [canonical_by_index[index] for index in range(len(plan.scenarios))], selected_id


def _persist_planner_result(
    current: QuotePlan,
    planned: QuotePlan,
    *,
    actor_email: str,
) -> QuotePlan:
    if (
        planned.plan_id != current.plan_id
        or planned.draft_order_id != current.draft_order_id
        or planned.account_id != current.account_id
        or planned.base_draft_version != current.base_draft_version
    ):
        raise RuntimeError("Planner returned a plan for different server-owned context.")
    if planned.status not in {PlanStatus.NEEDS_INPUT, PlanStatus.READY}:
        raise RuntimeError("Planner returned an unsupported initial plan status.")
    latest_order = store.get(current.draft_order_id)
    if latest_order.version != current.base_draft_version:
        _mark_plan_stale(
            current,
            current_draft_version=latest_order.version,
            actor_email=actor_email,
        )
        raise DraftConflict("Draft changed while the quote plan was being prepared.")

    scenarios, selected_id = _canonicalize_plan_scenarios(
        planned,
        persisted_plan_id=current.plan_id,
        draft_version=current.base_draft_version,
    )
    latest_order = store.get(current.draft_order_id)
    if latest_order.version != current.base_draft_version:
        _mark_plan_stale(
            current,
            current_draft_version=latest_order.version,
            actor_email=actor_email,
        )
        raise DraftConflict("Draft changed while the quote plan was being prepared.")

    next_revision = current.revision + 1
    selected = next(
        (scenario for scenario in scenarios if scenario.scenario_id == selected_id),
        None,
    )
    action_proposal = (
        _confirmation_proposal(
            plan_id=current.plan_id,
            scenario=selected,
            actor_email=actor_email,
            account_id=current.account_id,
            draft_order_id=current.draft_order_id,
            draft_version=current.base_draft_version,
            plan_revision=next_revision,
        )
        if planned.status == PlanStatus.READY and selected is not None
        else None
    )
    merged_metadata = copy.deepcopy(current.metadata)
    merged_metadata.update(planned.metadata)
    updated = store.update_plan(
        current.plan_id,
        expected_revision=current.revision,
        goal=current.goal,
        status=planned.status,
        steps=planned.steps,
        scenarios=scenarios,
        selected_scenario_id=selected_id,
        action_proposal=action_proposal,
        error_message="",
        metadata=merged_metadata,
    )
    store.append_plan_action(
        updated.plan_id,
        "plan_prepared",
        actor_email,
        plan_revision=updated.revision,
        draft_version=updated.base_draft_version,
        payload={"status": updated.status.value, "scenario_count": len(updated.scenarios)},
    )
    return updated


def _new_plan_skeleton(
    request: SellerQueryRequest,
    actor: ActorContext,
    *,
    account_id: str,
    draft_version: int,
) -> QuotePlan:
    if not request.draft_order_id:
        raise HTTPException(
            status_code=400,
            detail="A persisted draft is required for goal-to-quote planning.",
        )
    order = _owned_order(request.draft_order_id, actor)
    if order.status == "quote-created":
        raise HTTPException(
            status_code=409,
            detail="Create a revision before planning changes to a generated quote.",
        )
    try:
        active = store.get_active_plan(order.draft_order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    if active is not None and order.version != _plan_bound_draft_version(active):
        _mark_plan_stale(
            active,
            current_draft_version=order.version,
            actor_email=actor.email,
        )
    skeleton = QuotePlan(
        account_id=account_id,
        draft_order_id=request.draft_order_id,
        draft_version=draft_version,
        goal=request.query.strip(),
        status=PlanStatus.PLANNING,
        steps=[
            PlanStep(
                title="Goal",
                status=PlanStepStatus.COMPLETED,
                detail=request.query.strip()[:240],
                sequence=0,
            ),
            PlanStep(
                title="Check account & catalog",
                status=PlanStepStatus.IN_PROGRESS,
                detail="Checking the account, staged quote, and governed catalog.",
                sequence=1,
            ),
            PlanStep(title="Build options", sequence=2),
            PlanStep(
                title="Review changes",
                sequence=3,
                requires_confirmation=True,
            ),
        ],
        created_by=actor.email,
        metadata={"agent_framework": "openai-agents", "write_policy": "confirm_before_write"},
    )
    try:
        return store.create_plan(skeleton, actor.email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc


async def _complete_new_plan(
    skeleton: QuotePlan,
    request: SellerQueryRequest,
    actor: ActorContext,
    *,
    account_id: str,
    current_lines: list[DraftLineItem],
    conversation_history: list[ConversationTurn],
    last_recommendation: dict[str, object],
    genie_conversation_id: str | None,
) -> QuotePlan:
    admin_settings = _current_admin_settings()
    try:
        planned = await agent_client.plan_quote(
            goal=request.query,
            account_id=account_id,
            draft_order_id=skeleton.draft_order_id,
            draft_version=skeleton.base_draft_version,
            current_order_lines=current_lines,
            conversation_history=[turn.model_dump() for turn in conversation_history],
            last_recommendation=last_recommendation,
            plan_id=skeleton.plan_id,
            plan_revision=skeleton.revision + 1,
            seller_email=actor.email,
            view_role=actor.authorize_view(request.view_role),
            genie_conversation_id=genie_conversation_id,
            execution_identity=actor.execution_identity,
            approval_threshold=admin_settings.behavior.approval_threshold,
            auto_attach_care_plan=admin_settings.behavior.auto_attach_care_plan,
            max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
        )
        result = await asyncio.to_thread(
            _persist_planner_result,
            skeleton,
            planned,
            actor_email=actor.email,
        )
        await asyncio.to_thread(_remember_plan_turn, request, result)
        return result
    except Exception as exc:
        await asyncio.to_thread(_fail_plan, skeleton.plan_id, actor.email)
        raise exc


def _fail_plan(plan_id: str, actor_email: str) -> QuotePlan | None:
    try:
        current = store.get_plan(plan_id)
        if current.status in TERMINAL_PLAN_STATUSES:
            return current
        failed = store.update_plan(
            plan_id,
            expected_revision=current.revision,
            status=PlanStatus.FAILED,
            action_proposal=None,
            error_message="Genie couldn't complete this quote plan. Try again.",
        )
        store.append_plan_action(
            failed.plan_id,
            "plan_failed",
            actor_email,
            plan_revision=failed.revision,
            payload={"public_error": failed.error_message},
        )
        return failed
    except (DraftConflict, KeyError):
        return None


def _remember_plan_turn(request: SellerQueryRequest, plan: QuotePlan) -> None:
    if not request.draft_order_id:
        return
    response = str(
        plan.metadata.get("clarifying_question")
        or plan.metadata.get("summary")
        or (
            f"Prepared {len(plan.scenarios)} grounded quote option(s)."
            if plan.scenarios
            else "Quote plan prepared."
        )
    ).strip()
    try:
        store.append_conversation_turns(
            request.draft_order_id,
            [
                ConversationTurn(role="user", content=request.query),
                ConversationTurn(role="assistant", content=response),
            ],
        )
    except KeyError:
        return


def _request_uses_plan(request: SellerQueryRequest) -> bool:
    if not getattr(settings, "plans_enabled", False):
        return False
    predicate = getattr(agent_client, "should_create_plan", None)
    return bool(callable(predicate) and predicate(request.query, request.intent))


def _verify_confirmation(
    plan: QuotePlan,
    request: PlanConfirmRequest,
    actor: ActorContext,
    *,
    action_type: str,
):
    kwargs = {
        "secret": _plan_confirmation_secret,
        "actor_email": actor.email,
        "account_id": plan.account_id,
        "draft_order_id": plan.draft_order_id,
        "draft_version": request.expected_draft_version,
        "plan_id": plan.plan_id,
        "plan_revision": request.expected_plan_revision,
        "idempotency_key": request.idempotency_key.strip(),
        "action_type": action_type,
    }
    try:
        return (
            verify_confirmation_token(
                request.confirmation_token.strip(),
                **kwargs,
            ),
            False,
        )
    except ConfirmationTokenError as exc:
        if "expired" in str(exc).casefold():
            try:
                return (
                    verify_confirmation_token(
                        request.confirmation_token.strip(),
                        allow_expired=True,
                        **kwargs,
                    ),
                    True,
                )
            except ConfirmationTokenError:
                pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _existing_confirmed_action(
    plan: QuotePlan,
    request: PlanConfirmRequest,
    actor: ActorContext,
    *,
    action_type: str,
    confirmation_token_id: str,
):
    try:
        actions = store.list_plan_actions(plan.plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Quote plan not found") from exc
    for action in actions:
        if action.idempotency_key != request.idempotency_key.strip():
            continue
        if (
            action.action_type != action_type
            or action.actor_email != actor.email.casefold()
            or action.confirmation_token_id != confirmation_token_id
            or action.draft_version != request.expected_draft_version
        ):
            raise HTTPException(
                status_code=409,
                detail="Plan action retry does not match the original action.",
            )
        return action
    return None


def _recorded_apply_order(action) -> DraftOrder:
    payload = action.payload.get("result_order")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=409,
            detail="The original confirmed application result is unavailable.",
        )
    try:
        order = DraftOrder.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="The recorded confirmed application result is invalid.",
        ) from exc
    expected_fingerprint = str(action.payload.get("result_line_fingerprint") or "")
    if (
        order.draft_order_id != action.draft_order_id
        or order.account_id != action.account_id
        or order.version != action.draft_version + 1
        or (
            expected_fingerprint
            and _draft_lines_fingerprint(order.line_items) != expected_fingerprint
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="The recorded confirmed application result is invalid.",
        )
    return order


def _recorded_pdf_order(action) -> DraftOrder:
    payload = action.payload.get("result_order")
    if not isinstance(payload, dict):
        raise DraftConflict(
            "The original confirmed PDF result is unavailable."
        )
    try:
        order = DraftOrder.model_validate(payload)
    except ValueError as exc:
        raise DraftConflict("The recorded confirmed PDF result is invalid.") from exc
    payload_quote_id = str(action.payload.get("quote_id") or "").strip()
    if (
        order.draft_order_id != action.draft_order_id
        or order.account_id != action.account_id
        or order.version != action.draft_version + 1
        or order.status != "quote-created"
        or not order.quote_id
        or (payload_quote_id and payload_quote_id != order.quote_id)
    ):
        raise DraftConflict("The recorded confirmed PDF result is invalid.")
    return order


def _refresh_plan_confirmation(
    plan: QuotePlan,
    order: DraftOrder,
    actor: ActorContext,
) -> QuotePlan:
    action_type = (
        "apply_scenario"
        if plan.status == PlanStatus.READY
        else "generate_pdf"
        if plan.status == PlanStatus.READY_FOR_PDF
        else ""
    )
    if not action_type:
        return plan
    try:
        scenario = _selected_scenario(plan)
    except DraftConflict:
        return plan
    proposal = plan.action_proposal
    confirmation = proposal.confirmation if proposal else None
    if proposal and confirmation and proposal.action_type == action_type:
        try:
            verify_confirmation_token(
                confirmation.token,
                secret=_plan_confirmation_secret,
                actor_email=actor.email,
                account_id=plan.account_id,
                draft_order_id=plan.draft_order_id,
                draft_version=order.version,
                plan_id=plan.plan_id,
                plan_revision=plan.revision,
                idempotency_key=proposal.idempotency_key,
                action_type=action_type,
            )
            return plan
        except ConfirmationTokenError:
            pass
    next_revision = plan.revision + 1
    refreshed_proposal = _confirmation_proposal(
        plan_id=plan.plan_id,
        scenario=scenario,
        actor_email=actor.email,
        account_id=plan.account_id,
        draft_order_id=plan.draft_order_id,
        draft_version=order.version,
        plan_revision=next_revision,
        action_type=action_type,
    )
    refreshed = store.update_plan(
        plan.plan_id,
        expected_revision=plan.revision,
        action_proposal=refreshed_proposal,
    )
    store.append_plan_action(
        refreshed.plan_id,
        "confirmation_refreshed",
        actor.email,
        plan_revision=refreshed.revision,
        draft_version=order.version,
        payload={"action_type": action_type},
    )
    return refreshed


def _approval_required(order: DraftOrder) -> bool:
    threshold = _current_admin_settings().behavior.approval_threshold
    return bool(
        order.grand_total > threshold
        or any(line.approval_required for line in order.line_items)
    )


def _draft_lines_fingerprint(lines: list[DraftLineItem]) -> str:
    payload = [
        line.model_dump(mode="json", exclude_none=False)
        for line in lines
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _steps_after_apply(plan: QuotePlan, *, approval_required: bool) -> list[PlanStep]:
    steps = [step.model_copy(deep=True) for step in plan.steps]
    for step in steps:
        if step.requires_confirmation or step.title.casefold() == "review changes":
            step.status = PlanStepStatus.COMPLETED
            step.detail = "Confirmed changes were applied to the quote."
    pdf_status = PlanStepStatus.BLOCKED if approval_required else PlanStepStatus.IN_PROGRESS
    pdf_detail = (
        "Approval must be completed before generating the PDF."
        if approval_required
        else "The confirmed quote is ready for PDF generation."
    )
    existing = next(
        (step for step in steps if step.title.casefold() == "generate quote pdf"),
        None,
    )
    if existing:
        existing.status = pdf_status
        existing.detail = pdf_detail
        existing.requires_confirmation = not approval_required
    else:
        steps.append(
            PlanStep(
                title="Generate quote PDF",
                status=pdf_status,
                detail=pdf_detail,
                sequence=max((step.sequence for step in steps), default=-1) + 1,
                requires_confirmation=not approval_required,
            )
        )
    return steps


def _finalize_applied_plan(
    plan: QuotePlan,
    order: DraftOrder,
    *,
    expected_plan_revision: int,
    actor_email: str,
) -> QuotePlan:
    current = store.get_plan(plan.plan_id)
    if current.revision != expected_plan_revision:
        return current
    changes = _plan_changes_after_apply(current, order, actor_email=actor_email)
    return store.update_plan(
        current.plan_id,
        expected_revision=current.revision,
        **changes,
    )


def _plan_changes_after_apply(
    current: QuotePlan,
    order: DraftOrder,
    *,
    actor_email: str,
) -> dict[str, object]:
    approval_required = _approval_required(order)
    status = (
        PlanStatus.AWAITING_APPROVAL
        if approval_required
        else PlanStatus.READY_FOR_PDF
    )
    next_revision = current.revision + 1
    scenario = _selected_scenario(current)
    proposal = (
        None
        if approval_required
        else _confirmation_proposal(
            plan_id=current.plan_id,
            scenario=scenario,
            actor_email=actor_email,
            account_id=current.account_id,
            draft_order_id=current.draft_order_id,
            draft_version=order.version,
            plan_revision=next_revision,
            action_type="generate_pdf",
        )
    )
    metadata = copy.deepcopy(current.metadata)
    metadata.update(
        {
            "applied_draft_version": order.version,
            "approval_required": approval_required,
            "summary": "The confirmed changes are now in the quote.",
        }
    )
    return {
        "status": status,
        "steps": _steps_after_apply(current, approval_required=approval_required),
        "action_proposal": proposal,
        "metadata": metadata,
    }


def _finalize_pdf_plan(
    plan: QuotePlan,
    order: DraftOrder,
    *,
    expected_plan_revision: int,
) -> QuotePlan:
    current = store.get_plan(plan.plan_id)
    if current.revision != expected_plan_revision:
        return current
    steps = [step.model_copy(deep=True) for step in current.steps]
    for step in steps:
        if step.title.casefold() == "generate quote pdf":
            step.status = PlanStepStatus.COMPLETED
            step.detail = "Quote PDF generated."
    metadata = copy.deepcopy(current.metadata)
    metadata.update(
        {
            "completed_draft_version": order.version,
            "quote_id": order.quote_id,
            "summary": "The quote PDF is ready.",
        }
    )
    return store.update_plan(
        current.plan_id,
        expected_revision=current.revision,
        status=PlanStatus.COMPLETED,
        steps=steps,
        action_proposal=None,
        metadata=metadata,
    )


def _verified_stored_quote(order: DraftOrder) -> dict[str, object]:
    if order.status != "quote-created" or not order.quote_id:
        raise DraftConflict("The quote PDF has not been committed.")
    try:
        payload = store.get_quote(order.quote_id)
    except KeyError as exc:
        raise DraftConflict("The committed quote document could not be found.") from exc
    document = payload.get("quote_document")
    header = document.get("quote_header") if isinstance(document, dict) else None
    if (
        str(payload.get("quote_id") or "") != order.quote_id
        or not isinstance(header, dict)
        or str(header.get("account_id") or "") != order.account_id
    ):
        raise DraftConflict("The stored quote document does not match this draft.")
    return payload


def _complete_plan_for_legacy_pdf(
    draft_order_id: str,
    order: DraftOrder,
    actor_email: str,
) -> QuotePlan | None:
    """Keep the existing PDF button compatible with an already-applied plan."""

    try:
        plan = store.get_active_plan(draft_order_id)
    except KeyError:
        return None
    if plan is None or plan.status != PlanStatus.READY_FOR_PDF:
        return None
    bound_version = _plan_bound_draft_version(plan)
    # The atomic quote commit canonicalizes the immutable document snapshot,
    # advances the draft exactly once, and attaches the generated quote.
    if order.version != bound_version + 1 or not order.quote_id:
        return None
    _verified_stored_quote(order)
    store.append_plan_action(
        plan.plan_id,
        "pdf_generated",
        actor_email,
        plan_revision=plan.revision,
        draft_version=bound_version,
        idempotency_key=f"legacy_pdf:{plan.plan_id}:r{plan.revision}",
        payload={
            "quote_id": order.quote_id,
            "source": "quote_pdf_endpoint",
            "result_order": order.model_dump(mode="json"),
        },
    )
    return _finalize_pdf_plan(
        plan,
        order,
        expected_plan_revision=plan.revision,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if _lakebase_active:
        try:
            lakebase.init_schema()
            logger.info("Lakebase store active: transactional schema ready; reference data from cpq_ref.")
        except Exception:
            logger.exception("Lakebase initialization failed.")
    else:
        logger.info("Lakebase not configured; using in-memory store.")
    try:
        yield
    finally:
        await agent_client.close()


app = FastAPI(title="Agentic CPQ", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_root), name="static")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(static_root / "index.html")


@app.get("/info", include_in_schema=False)
def info() -> FileResponse:
    return FileResponse(static_root / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me")
def current_user(http_request: Request) -> dict[str, object]:
    actor = _actor(http_request)
    return {
        "email": actor.email,
        "username": actor.username,
        "authenticated": actor.authenticated,
        "allowed_views": list(actor.allowed_views),
        "can_manage": actor.can_manage,
        "default_view": "seller",
        "execution_identity": actor.execution_identity,
    }


@app.get("/api/admin/settings", response_model=CPQAdminSettings)
def get_admin_settings(http_request: Request) -> CPQAdminSettings:
    _admin_actor(http_request)
    return _current_admin_settings()


@app.put("/api/admin/settings", response_model=CPQAdminSettings)
def update_admin_settings(
    request: CPQAdminSettings,
    http_request: Request,
) -> CPQAdminSettings:
    actor = _admin_actor(http_request)
    return store.save_admin_settings(request, updated_by=actor.email)


@app.post("/api/admin/settings/pdf-preview")
def preview_admin_quote_pdf(
    request: QuotePdfSettings,
    http_request: Request,
) -> StreamingResponse:
    """Render unsaved document settings against a stable representative quote."""

    actor = _admin_actor(http_request)
    pdf = build_quote_pdf(
        quote_id="SAMPLE-QUOTE",
        order_id="sample-order",
        revision_number=1,
        account={
            "name": "Riverfront Dental Group",
            "segment": "mid-market",
            "region": "Northeast",
        },
        seller_email=actor.email,
        line_items=[
            {
                "sku": "IMAG-CBCT-210",
                "title": "Vatech CBCT Imaging Starter",
                "category": "imaging",
                "quantity": 1,
                "list_price": 19_500.0,
                "unit_price": 18_500.0,
                "total_price": 18_500.0,
            },
            {
                "sku": "SUPPORT-CARE-IMG",
                "title": "Equipment Care · Imaging Care",
                "category": "services",
                "quantity": 1,
                "list_price": 2_100.0,
                "unit_price": 2_100.0,
                "total_price": 2_100.0,
                "is_addon": True,
                "covers_sku": "IMAG-CBCT-210",
            },
        ],
        pdf_settings=request,
    )
    return _quote_pdf_response(
        pdf,
        quote_id="SAMPLE-QUOTE",
        revision_number=1,
        download=False,
    )


@app.get("/api/bootstrap-state")
def bootstrap_state(
    http_request: Request,
    view_role: str = "seller",
) -> dict[str, object]:
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    admin_settings = _current_admin_settings()
    products = lakebase.get_products()
    if effective_view == "seller":
        products = [
            {key: value for key, value in product.items() if key != "doc_source"}
            for product in products
        ]
    return {
        "app_name": settings.databricks_app_name,
        "environment": settings.environment,
        "default_account_id": settings.default_account_id,
        "accounts": lakebase.get_accounts(),
        "source_freshness": lakebase.get_source_freshness(),
        "product_snapshot": products,
        "agent_names": {
            "quote_agent": settings.quote_agent_name,
            "genie": settings.genie_space_title,
        },
        "quote_policy": admin_settings.behavior.model_dump(mode="json"),
        "use_mock_fallback": settings.use_mock_fallback,
    }


@app.get("/api/products/search")
async def products_search(
    http_request: Request,
    q: str = "",
    category: str = "",
    view_role: str = "seller",
) -> dict[str, object]:
    """Rank a bounded governed catalog snapshot and return authoritative rows."""
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    query = q.strip()
    cat = category.strip() or None
    candidates = lakebase.get_products()
    if cat:
        candidates = [
            product
            for product in candidates
            if str(product.get("category") or "").casefold() == cat.casefold()
        ]
    ranked = await agent_client.search_governed_candidates(
        kind="products",
        query=query,
        candidates=candidates,
        limit=24,
    )
    results = ranked["results"]
    if effective_view == "seller":
        results = [
            {key: value for key, value in product.items() if key != "doc_source"}
            for product in results
        ]
    return {
        "results": results,
        "source": "lakebase",
        "metadata": {
            "mode": ranked["mode"],
            "fallback_used": ranked["fallback_used"],
        },
    }


@app.get("/api/accounts/search")
async def accounts_search(
    http_request: Request,
    q: str = "",
) -> dict[str, object]:
    """Rank the governed account directory without creating external customer claims."""
    _actor(http_request)
    ranked = await agent_client.search_governed_candidates(
        kind="accounts",
        query=q.strip(),
        candidates=lakebase.get_accounts(),
        limit=20,
    )
    return {
        "results": ranked["results"],
        "source": "lakebase",
        "metadata": {
            "mode": ranked["mode"],
            "fallback_used": ranked["fallback_used"],
        },
    }


@app.get("/api/intelligence/overpay-runrate")
def overpay_runrate(
    http_request: Request,
    view_role: str = "seller",
) -> dict[str, object]:
    """Annualized supplier-overpayment prevention, computed from the UC-synced
    supplier price book (per-unit overpay x annual order velocity)."""
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    if effective_view == "seller":
        return {
            "verified": True,
            "basis": "Supplier cost is verified before PO handoff.",
            "is_projection": True,
            "by_sku": [],
        }
    return lakebase.overpay_runrate()


@app.post("/api/draft-orders")
def create_draft_order(
    request: CreateDraftOrderRequest,
    http_request: Request,
) -> dict[str, object]:
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    try:
        line_items = _rehydrate_catalog_lines(request.line_items, account_id=request.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    order = store.create(
        account_id=request.account_id,
        line_items=line_items,
        owner_email=actor.email,
    )
    return redact_line_items_for_view(order.model_dump(), view_role)


@app.get("/api/draft-orders/resume")
def resume_draft_order(
    http_request: Request,
    account_id: str = "",
    view_role: str = "seller",
) -> dict[str, object | None]:
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    account = account_id or settings.default_account_id
    order = store.find_resumable(account, actor.email)
    return {
        "draft": (
            redact_line_items_for_view(order.model_dump(), effective_view)
            if order is not None
            else None
        )
    }


@app.get("/api/draft-orders/{draft_order_id}")
def get_draft_order(
    draft_order_id: str,
    http_request: Request,
    view_role: str = "seller",
) -> dict[str, object]:
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    order = _owned_order(draft_order_id, actor)
    return redact_line_items_for_view(order.model_dump(), effective_view)


@app.post("/api/draft-orders/{draft_order_id}/revisions")
def create_draft_revision(
    draft_order_id: str,
    request: CreateRevisionRequest,
    http_request: Request,
) -> dict[str, object]:
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    _owned_order(draft_order_id, actor)
    try:
        revision = store.create_revision(draft_order_id, owner_email=actor.email)
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return redact_line_items_for_view(revision.model_dump(), view_role)


@app.patch("/api/draft-orders/{draft_order_id}")
def update_draft_order(
    draft_order_id: str,
    request: UpdateDraftOrderRequest,
    http_request: Request,
) -> dict[str, object]:
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    order = _owned_order(draft_order_id, actor)
    admin_settings = _current_admin_settings()
    if view_role == "seller" and not admin_settings.behavior.allow_seller_price_edits:
        _enforce_seller_patch_price_policy(order, request.line_items)
    try:
        lines = _rehydrate_catalog_lines(request.line_items, account_id=order.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        updated = store.update_lines(
            draft_order_id,
            lines,
            expected_version=request.expected_version,
        )
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return redact_line_items_for_view(updated.model_dump(), view_role)


def _enforce_seller_patch_price_policy(
    order: DraftOrder,
    requested_lines: list[DraftLineItem],
) -> None:
    """Keep PATCH available for quantities/removals without opening a pricing bypass."""

    existing_prices = {
        line.sku: line.unit_price for line in order.line_items if not line.is_addon
    }
    for line in requested_lines:
        if line.sku in existing_prices:
            if line.unit_price != existing_prices[line.sku]:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Seller price edits are disabled by Workspace Settings; "
                        f"keep the existing unit price for {line.sku}."
                    ),
                )
            continue
        if not line.is_addon:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Seller catalog additions must use the dedicated add-line flow "
                    "when price edits are disabled."
                ),
            )


def _rehydrate_catalog_lines(lines: list[DraftLineItem], *, account_id: str) -> list[DraftLineItem]:
    """Rebuild every mutable quote line from governed catalog and care-plan data."""
    account = lakebase.get_account(account_id)
    if account is None:
        raise ValueError(f"Unknown account {account_id}")

    admin_settings = _current_admin_settings()
    rules = warranty_rules_by_sku()
    warranty_skus = {
        str(rule.get("warranty_sku"))
        for rule in rules.values()
        if rule.get("warranty_sku")
    }
    base_lines: dict[str, DraftLineItem] = {}
    base_order: list[str] = []
    requested_addons: dict[str, DraftLineItem] = {}

    for line in lines:
        if line.is_addon:
            covers_sku = str(line.covers_sku or "").strip()
            if not covers_sku:
                raise ValueError(f"Care-plan line {line.sku} must identify covers_sku")
            if covers_sku in requested_addons:
                raise ValueError(f"Duplicate care-plan coverage for {covers_sku}")
            requested_addons[covers_sku] = line
            continue
        if line.sku in warranty_skus:
            raise ValueError(f"Care-plan SKU {line.sku} must be attached to eligible equipment")
        if line.sku in base_lines:
            raise ValueError(f"Duplicate quote SKU {line.sku}")
        catalog_line = reprice_catalog_line(
            line.sku,
            unit_price=line.unit_price,
            quantity=line.quantity,
            account_id=account_id,
            max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
        )
        if catalog_line is None:
            raise ValueError(f"Unknown SKU {line.sku}")
        base_lines[line.sku] = DraftLineItem.model_validate(catalog_line)
        base_order.append(line.sku)

    hydrated: list[DraftLineItem] = []
    for sku in base_order:
        equipment_line = base_lines[sku]
        hydrated.append(equipment_line)
        addon = requested_addons.pop(sku, None)
        if addon is None:
            continue
        rule = rules.get(sku) or {}
        if not rule.get("eligible"):
            raise ValueError(f"SKU {sku} is not eligible for a care plan")
        expected = care_plan_line_for(equipment_line.model_dump(), account, rule)
        if addon.sku != expected["sku"]:
            raise ValueError(f"Care-plan SKU {addon.sku} does not cover {sku}")
        hydrated.append(DraftLineItem.model_validate(expected))

    if requested_addons:
        orphan = next(iter(requested_addons.values()))
        raise ValueError(f"Care-plan line {orphan.sku} does not cover a quote equipment line")
    return hydrated


def _enforce_order_account(requested_account_id: str | None, order_account_id: str) -> str:
    if requested_account_id and requested_account_id != order_account_id:
        raise HTTPException(status_code=400, detail="Request account does not match the draft order")
    return order_account_id


def _agent_order_context(
    request: SellerQueryRequest,
    actor: ActorContext,
) -> tuple[str, list[DraftLineItem], int | None, str | None]:
    if not request.draft_order_id:
        account_id = request.account_id or settings.default_account_id
        try:
            current_lines = _rehydrate_catalog_lines(
                request.current_order_lines,
                account_id=account_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return account_id, current_lines, None, None
    _owned_order(request.draft_order_id, actor)
    try:
        order, genie_conversation_id = store.get_agent_snapshot(
            request.draft_order_id,
            expected_revision=request.expected_revision,
        )
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return (
        _enforce_order_account(request.account_id, order.account_id),
        order.line_items,
        order.version,
        genie_conversation_id,
    )


def _agent_request_context(
    request: SellerQueryRequest,
    actor: ActorContext,
) -> tuple[
    str,
    list[DraftLineItem],
    list[ConversationTurn],
    dict[str, object],
    int | None,
    str | None,
]:
    """Load all synchronous order/conversation state off the async request loop."""
    account_id, current_lines, draft_version, genie_conversation_id = (
        _agent_order_context(request, actor)
    )
    return (
        account_id,
        current_lines,
        _conversation_history_for_request(request),
        _last_recommendation_for_request(request),
        draft_version,
        genie_conversation_id,
    )


@app.post("/api/agent/query")
async def agent_query(
    request: SellerQueryRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    (
        account_id,
        current_lines,
        conversation_history,
        last_recommendation,
        draft_version,
        genie_conversation_id,
    ) = await asyncio.to_thread(_agent_request_context, request, actor)

    if _request_uses_plan(request):
        _no_store(http_response)
        if draft_version is None:
            raise HTTPException(
                status_code=400,
                detail="A persisted draft is required for goal-to-quote planning.",
            )
        skeleton = await asyncio.to_thread(
            _new_plan_skeleton,
            request,
            actor,
            account_id=account_id,
            draft_version=draft_version,
        )
        try:
            planned = await _complete_new_plan(
                skeleton,
                request,
                actor,
                account_id=account_id,
                current_lines=current_lines,
                conversation_history=conversation_history,
                last_recommendation=last_recommendation,
                genie_conversation_id=genie_conversation_id,
            )
        except DraftConflict as exc:
            raise _conflict(exc) from exc
        except Exception as exc:
            logger.exception("Goal-to-quote planning failed.")
            raise HTTPException(status_code=502, detail=_public_agent_error(exc)) from exc
        return _plan_payload(planned, view_role)

    # No mock/static fallback: recommendations come only from the live agent.
    # If it fails, surface an explicit error so nothing is fabricated.
    try:
        admin_settings = _current_admin_settings()
        recommendation_payload = await agent_client.query(
            query=request.query,
            account_id=account_id,
            draft_order_id=request.draft_order_id,
            conversation_history=[turn.model_dump() for turn in conversation_history],
            current_order_lines=current_lines,
            last_recommendation=last_recommendation,
            seller_email=actor.email,
            view_role=view_role,
            intent=request.intent,
            genie_conversation_id=genie_conversation_id,
            execution_identity=actor.execution_identity,
            approval_threshold=admin_settings.behavior.approval_threshold,
            auto_attach_care_plan=admin_settings.behavior.auto_attach_care_plan,
            max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
        )
    except ConversationalAgentOutput as exc:
        payload = exc.payload()
        await asyncio.to_thread(_remember_conversation_answer, request, payload)
        return payload
    except Exception as exc:
        logger.exception("Build agent query failed.")
        raise HTTPException(status_code=502, detail=_public_agent_error(exc)) from exc

    if not recommendation_payload:
        raise HTTPException(status_code=502, detail="Genie returned no usable result. Try again.")

    recommendation = CartRecommendation.model_validate(recommendation_payload)
    stored = await asyncio.to_thread(
        _remember_turn,
        request,
        recommendation,
        draft_version,
    )
    # Store the full recommendation (above) but return a view-appropriate copy:
    # sellers never receive supplier cost / margin / overpayment dollars.
    return redact_recommendation_for_view(stored, view_role)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _public_agent_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "Genie timed out before completing this request. Try again."
    return "Genie couldn't complete this request. Try again."


@app.post("/api/agent/stream")
async def agent_stream(request: SellerQueryRequest, http_request: Request) -> StreamingResponse:
    """Stream agent progress and a final conversation, recommendation, or plan."""
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    (
        account_id,
        current_lines,
        conversation_history,
        last_recommendation,
        draft_version,
        genie_conversation_id,
    ) = await asyncio.to_thread(_agent_request_context, request, actor)

    skeleton: QuotePlan | None = None
    if _request_uses_plan(request):
        if draft_version is None:
            raise HTTPException(
                status_code=400,
                detail="A persisted draft is required for goal-to-quote planning.",
            )
        skeleton = await asyncio.to_thread(
            _new_plan_skeleton,
            request,
            actor,
            account_id=account_id,
            draft_version=draft_version,
        )

    async def gen():
        if skeleton is not None:
            yield _sse("plan", _plan_payload(skeleton, view_role))
            try:
                planned = await _complete_new_plan(
                    skeleton,
                    request,
                    actor,
                    account_id=account_id,
                    current_lines=current_lines,
                    conversation_history=conversation_history,
                    last_recommendation=last_recommendation,
                    genie_conversation_id=genie_conversation_id,
                )
                yield _sse("plan", _plan_payload(planned, view_role))
                yield _sse("done", {})
            except Exception as exc:  # noqa: BLE001 - return only a public failure
                logger.exception("Goal-to-quote stream failed.")
                try:
                    final_plan = await asyncio.to_thread(store.get_plan, skeleton.plan_id)
                    yield _sse("plan", _plan_payload(final_plan, view_role))
                except KeyError:
                    pass
                yield _sse("error", {"detail": _public_agent_error(exc)})
            return
        try:
            admin_settings = _current_admin_settings()
            async for evt in agent_client.stream(
                query=request.query,
                account_id=account_id,
                draft_order_id=request.draft_order_id,
                conversation_history=[turn.model_dump() for turn in conversation_history],
                current_order_lines=current_lines,
                last_recommendation=last_recommendation,
                seller_email=actor.email,
                view_role=view_role,
                intent=request.intent,
                genie_conversation_id=genie_conversation_id,
                execution_identity=actor.execution_identity,
                approval_threshold=admin_settings.behavior.approval_threshold,
                auto_attach_care_plan=admin_settings.behavior.auto_attach_care_plan,
                max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
            ):
                if evt.get("kind") == "stage":
                    yield _sse("stage", {k: v for k, v in evt.items() if k != "kind"})
                elif evt.get("kind") == "recommendation":
                    recommendation = CartRecommendation.model_validate(evt["payload"])
                    stored = await asyncio.to_thread(
                        _remember_turn,
                        request,
                        recommendation,
                        draft_version,
                    )
                    yield _sse("recommendation", redact_recommendation_for_view(stored, view_role))
                elif evt.get("kind") == "conversation":
                    payload = evt["payload"]
                    await asyncio.to_thread(_remember_conversation_answer, request, payload)
                    yield _sse("conversation", payload)
            yield _sse("done", {})
        except ConversationalAgentOutput as exc:
            payload = exc.payload()
            await asyncio.to_thread(_remember_conversation_answer, request, payload)
            yield _sse("conversation", payload)
        except Exception as exc:  # noqa: BLE001 - surface as an SSE error; client falls back
            logger.exception("Agent stream failed.")
            yield _sse("error", {"detail": _public_agent_error(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/draft-orders/{draft_order_id}/agent-plan")
def get_active_agent_plan(
    draft_order_id: str,
    http_request: Request,
    http_response: Response,
    view_role: str = "seller",
):
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    order = _owned_order(draft_order_id, actor)
    try:
        plan = store.get_active_plan(draft_order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    if plan is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    if plan.account_id != order.account_id:
        raise HTTPException(status_code=409, detail="Quote plan account no longer matches its draft.")
    bound_version = _plan_bound_draft_version(plan)
    pending_pdf_recovery = (
        plan.status == PlanStatus.READY_FOR_PDF
        and order.status == "quote-created"
        and bool(order.quote_id)
        and order.version == bound_version + 1
    )
    if pending_pdf_recovery:
        try:
            _verified_stored_quote(order)
        except DraftConflict:
            pass
        else:
            # Preserve the original signed proposal. Confirm-PDF can use it to
            # audit/finalize a quote committed just before a process failure,
            # including an expired-but-valid exact recovery token.
            return _plan_payload(plan, effective_view)
    if order.version != bound_version:
        stale = _mark_plan_stale(
            plan,
            current_draft_version=order.version,
            actor_email=actor.email,
        )
        return _plan_payload(stale, effective_view)
    try:
        plan = _refresh_plan_confirmation(plan, order, actor)
    except DraftConflict as exc:
        # A concurrent GET may already have renewed the same proposal. Return the
        # canonical winner rather than turning a harmless reload into an error.
        try:
            plan = store.get_plan(plan.plan_id)
        except KeyError:
            raise _conflict(exc) from exc
    return _plan_payload(plan, effective_view)


@app.post("/api/agent/plans/{plan_id}/resume")
async def resume_agent_plan(
    plan_id: str,
    request: PlanResumeRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(request.view_role)
    plan, order = await asyncio.to_thread(_load_plan, plan_id, actor)
    try:
        _validate_plan_mutation(
            plan,
            order,
            expected_plan_revision=request.expected_plan_revision,
            expected_draft_version=request.expected_draft_version,
            actor_email=actor.email,
        )
        if plan.status != PlanStatus.NEEDS_INPUT:
            raise DraftConflict("Only a plan awaiting input can be resumed.")
        clarification = request.input.strip()
        metadata = copy.deepcopy(plan.metadata)
        metadata.pop("clarifying_question", None)
        clarifications = list(metadata.get("clarifications") or [])
        clarifications.append(clarification)
        metadata["clarifications"] = clarifications[-8:]
        steps = [step.model_copy(deep=True) for step in plan.steps]
        for step in steps:
            if step.status == PlanStepStatus.NEEDS_INPUT:
                step.status = PlanStepStatus.IN_PROGRESS
                step.detail = "Updating quote options with the provided detail."
        planning = await asyncio.to_thread(
            store.update_plan,
            plan.plan_id,
            plan.revision,
            status=PlanStatus.PLANNING,
            steps=steps,
            action_proposal=None,
            metadata=metadata,
        )
        await asyncio.to_thread(
            store.append_plan_action,
            planning.plan_id,
            "plan_resumed",
            actor.email,
            plan_revision=planning.revision,
            draft_version=order.version,
            payload={"input": clarification},
        )

        conversation = await asyncio.to_thread(
            store.get_conversation,
            plan.draft_order_id,
        )
        conversation_payload = redact_conversation_for_view(
            [turn.model_dump() for turn in conversation],
            effective_view,
        )
        conversation_payload.append({"role": "user", "content": clarification})
        last_recommendation = await asyncio.to_thread(
            store.get_latest_recommendation,
            plan.draft_order_id,
        )
        _, genie_conversation_id = await asyncio.to_thread(
            store.get_agent_snapshot,
            plan.draft_order_id,
            expected_revision=order.version,
        )
        admin_settings = _current_admin_settings()
        planned = await agent_client.plan_quote(
            goal=plan.goal,
            account_id=plan.account_id,
            draft_order_id=plan.draft_order_id,
            draft_version=order.version,
            current_order_lines=order.line_items,
            conversation_history=conversation_payload,
            last_recommendation=last_recommendation,
            plan_id=plan.plan_id,
            plan_revision=planning.revision + 1,
            seller_email=actor.email,
            view_role=effective_view,
            genie_conversation_id=genie_conversation_id,
            execution_identity=actor.execution_identity,
            approval_threshold=admin_settings.behavior.approval_threshold,
            auto_attach_care_plan=admin_settings.behavior.auto_attach_care_plan,
            max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
        )
        updated = await asyncio.to_thread(
            _persist_planner_result,
            planning,
            planned,
            actor_email=actor.email,
        )
        await asyncio.to_thread(
            store.append_conversation_turns,
            plan.draft_order_id,
            [
                ConversationTurn(role="user", content=clarification),
                ConversationTurn(
                    role="assistant",
                    content=str(
                        updated.metadata.get("clarifying_question")
                        or updated.metadata.get("summary")
                        or "Quote plan updated."
                    ),
                ),
            ],
        )
        return _plan_payload(updated, effective_view)
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        await asyncio.to_thread(_fail_plan, plan.plan_id, actor.email)
        logger.exception("Quote plan resume failed.")
        raise HTTPException(status_code=502, detail=_public_agent_error(exc)) from exc


@app.post("/api/agent/plans/{plan_id}/scenarios/{scenario_id}/select")
def select_agent_plan_scenario(
    plan_id: str,
    scenario_id: str,
    request: PlanMutationRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(request.view_role)
    plan, order = _load_plan(plan_id, actor)
    try:
        _validate_plan_mutation(
            plan,
            order,
            expected_plan_revision=request.expected_plan_revision,
            expected_draft_version=request.expected_draft_version,
            actor_email=actor.email,
        )
        if plan.status != PlanStatus.READY:
            raise DraftConflict("Quote scenarios can be selected only while a plan is ready for review.")
        scenario = next(
            (item for item in plan.scenarios if item.scenario_id == scenario_id),
            None,
        )
        if scenario is None:
            raise HTTPException(status_code=404, detail="Quote scenario not found")
        if scenario.recommendation is None:
            raise DraftConflict("The selected scenario has no stored recommendation.")
        next_revision = plan.revision + 1
        proposal = _confirmation_proposal(
            plan_id=plan.plan_id,
            scenario=scenario,
            actor_email=actor.email,
            account_id=plan.account_id,
            draft_order_id=plan.draft_order_id,
            draft_version=order.version,
            plan_revision=next_revision,
        )
        updated = store.update_plan(
            plan.plan_id,
            expected_revision=plan.revision,
            selected_scenario_id=scenario.scenario_id,
            action_proposal=proposal,
        )
        store.append_plan_action(
            updated.plan_id,
            "scenario_selected",
            actor.email,
            plan_revision=updated.revision,
            draft_version=order.version,
            payload={"scenario_id": scenario.scenario_id},
        )
        return _plan_payload(updated, effective_view)
    except DraftConflict as exc:
        raise _conflict(exc) from exc


@app.post("/api/agent/plans/{plan_id}/cancel")
def cancel_agent_plan(
    plan_id: str,
    request: PlanMutationRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(request.view_role)
    plan, order = _load_plan(plan_id, actor)
    if plan.status == PlanStatus.CANCELLED:
        return _plan_payload(plan, effective_view)
    try:
        _validate_plan_mutation(
            plan,
            order,
            expected_plan_revision=request.expected_plan_revision,
            expected_draft_version=request.expected_draft_version,
            actor_email=actor.email,
        )
        if plan.status not in {
            PlanStatus.PLANNING,
            PlanStatus.NEEDS_INPUT,
            PlanStatus.READY,
        }:
            raise DraftConflict("An applied quote plan cannot be cancelled or rolled back.")
        cancelled = store.cancel_plan(
            plan.plan_id,
            expected_revision=plan.revision,
            actor_email=actor.email,
            reason="Cancelled by the signed-in user.",
        )
        return _plan_payload(cancelled, effective_view)
    except DraftConflict as exc:
        raise _conflict(exc) from exc


@app.post("/api/agent/plans/{plan_id}/confirm-apply")
def confirm_agent_plan_apply(
    plan_id: str,
    request: PlanConfirmRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(request.view_role)
    plan, order = _load_plan(plan_id, actor)
    claims, confirmation_expired = _verify_confirmation(
        plan,
        request,
        actor,
        action_type="apply_scenario",
    )
    repeated = _existing_confirmed_action(
        plan,
        request,
        actor,
        action_type="scenario_applied",
        confirmation_token_id=claims.token_id,
    )
    if repeated is not None:
        current_plan = store.get_plan(plan.plan_id)
        result_order = _recorded_apply_order(repeated)
        if current_plan.revision == request.expected_plan_revision:
            current_plan = _finalize_applied_plan(
                current_plan,
                result_order,
                expected_plan_revision=request.expected_plan_revision,
                actor_email=actor.email,
            )
        return {
            "plan": _plan_payload(current_plan, effective_view),
            "order": redact_line_items_for_view(result_order.model_dump(), effective_view),
        }
    if confirmation_expired:
        raise HTTPException(status_code=400, detail="Confirmation token has expired.")
    try:
        if plan.status != PlanStatus.READY:
            raise DraftConflict("Only a ready quote plan can be confirmed and applied.")
        scenario = _selected_scenario(plan)
        proposal = plan.action_proposal
        if (
            proposal is None
            or proposal.action_type != "apply_scenario"
            or proposal.scenario_id != scenario.scenario_id
            or proposal.idempotency_key != request.idempotency_key.strip()
            or proposal.confirmation is None
            or proposal.confirmation.token != request.confirmation_token.strip()
        ):
            raise DraftConflict("Confirmation does not match the current selected scenario.")
        recommendation = store.get_recommendation(
            plan.draft_order_id,
            scenario.recommendation_id or "",
        )
        mode = str(recommendation.get("apply_mode") or "add")
        recovered = store.get_applied_recommendation(
            plan.draft_order_id,
            scenario.recommendation_id or "",
            scenario.recommendation_revision or 0,
            mode,
        )
        if recovered is not None:
            applied_order = DraftOrder.model_validate(recovered["order"])
            if applied_order.version != request.expected_draft_version + 1:
                _mark_plan_stale(
                    plan,
                    current_draft_version=applied_order.version,
                    actor_email=actor.email,
                )
                raise DraftConflict(
                    "The draft changed after the original scenario application."
                )
            recovered_candidate = _recommendation_apply_lines(
                applied_order.line_items,
                recommendation,
                mode,
            )
            recovered_canonical = _rehydrate_catalog_lines(
                recovered_candidate,
                account_id=applied_order.account_id,
            )
            result_fingerprint = _draft_lines_fingerprint(applied_order.line_items)
            if _draft_lines_fingerprint(recovered_canonical) != result_fingerprint:
                _mark_plan_stale(
                    plan,
                    current_draft_version=applied_order.version,
                    actor_email=actor.email,
                )
                raise DraftConflict(
                    "The draft no longer matches the original scenario application."
                )
            store.append_plan_action(
                plan.plan_id,
                "scenario_applied",
                actor.email,
                plan_revision=plan.revision,
                draft_version=request.expected_draft_version,
                idempotency_key=request.idempotency_key.strip(),
                confirmation_token_id=claims.token_id,
                payload={
                    "scenario_id": scenario.scenario_id,
                    "recommendation_id": scenario.recommendation_id,
                    "result_draft_version": applied_order.version,
                    "result_line_fingerprint": result_fingerprint,
                    "result_order": applied_order.model_dump(mode="json"),
                    "recovered": True,
                },
            )
            updated_plan = _finalize_applied_plan(
                plan,
                applied_order,
                expected_plan_revision=plan.revision,
                actor_email=actor.email,
            )
            return {
                "plan": _plan_payload(updated_plan, effective_view),
                "order": redact_line_items_for_view(
                    applied_order.model_dump(),
                    effective_view,
                ),
            }
        _validate_plan_mutation(
            plan,
            order,
            expected_plan_revision=request.expected_plan_revision,
            expected_draft_version=request.expected_draft_version,
            actor_email=actor.email,
        )
        candidate_lines = _recommendation_apply_lines(
            order.line_items,
            recommendation,
            mode,
        )
        canonical_lines = _rehydrate_catalog_lines(
            candidate_lines,
            account_id=order.account_id,
        )
        projected_total = round(
            sum((line.total_price or 0.0) for line in canonical_lines),
            2,
        )
        projected_order = order.model_copy(
            update={
                "line_items": canonical_lines,
                "subtotal": projected_total,
                "grand_total": projected_total,
                "version": order.version + 1,
            },
            deep=True,
        )
        result_fingerprint = _draft_lines_fingerprint(canonical_lines)
        next_plan_changes = _plan_changes_after_apply(
            plan,
            projected_order,
            actor_email=actor.email,
        )
        applied_order, updated_plan, _ = store.apply_confirmed_plan_scenario(
            plan.plan_id,
            expected_plan_revision=plan.revision,
            expected_draft_version=request.expected_draft_version,
            scenario_id=scenario.scenario_id,
            recommendation_id=scenario.recommendation_id or "",
            recommendation_revision=scenario.recommendation_revision or 0,
            mode=mode,
            line_items=canonical_lines,
            actor_email=actor.email,
            idempotency_key=request.idempotency_key.strip(),
            confirmation_token_id=claims.token_id,
            confirmation_token=request.confirmation_token.strip(),
            next_plan_changes=next_plan_changes,
            action_payload={
                "scenario_id": scenario.scenario_id,
                "recommendation_id": scenario.recommendation_id,
                "result_draft_version": projected_order.version,
                "result_line_fingerprint": result_fingerprint,
            },
        )
        return {
            "plan": _plan_payload(updated_plan, effective_view),
            "order": redact_line_items_for_view(applied_order.model_dump(), effective_view),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Stored plan recommendation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc


@app.post("/api/agent/plans/{plan_id}/confirm-pdf")
def confirm_agent_plan_pdf(
    plan_id: str,
    request: PlanConfirmRequest,
    http_request: Request,
    http_response: Response,
) -> dict[str, object]:
    _no_store(http_response)
    actor = _actor(http_request)
    effective_view = actor.authorize_view(request.view_role)
    plan, order = _load_plan(plan_id, actor)
    claims, confirmation_expired = _verify_confirmation(
        plan,
        request,
        actor,
        action_type="generate_pdf",
    )
    repeated = _existing_confirmed_action(
        plan,
        request,
        actor,
        action_type="pdf_generated",
        confirmation_token_id=claims.token_id,
    )
    if repeated is not None:
        try:
            result_order = _recorded_pdf_order(repeated)
            _verified_stored_quote(result_order)
            current_plan = store.get_plan(plan.plan_id)
            if (
                current_plan.status == PlanStatus.READY_FOR_PDF
                and current_plan.revision == request.expected_plan_revision
            ):
                current_plan = _finalize_pdf_plan(
                    current_plan,
                    result_order,
                    expected_plan_revision=request.expected_plan_revision,
                )
        except DraftConflict as exc:
            raise _conflict(exc) from exc
        return {
            "plan": _plan_payload(current_plan, effective_view),
            "order": redact_line_items_for_view(
                result_order.model_dump(),
                effective_view,
            ),
        }
    try:
        if plan.status != PlanStatus.READY_FOR_PDF:
            raise DraftConflict("This plan is not ready for PDF generation.")
        proposal = plan.action_proposal
        if (
            proposal is None
            or proposal.action_type != "generate_pdf"
            or proposal.idempotency_key != request.idempotency_key.strip()
            or proposal.confirmation is None
            or proposal.confirmation.token != request.confirmation_token.strip()
        ):
            raise DraftConflict("Confirmation does not match the current PDF action.")
        committed_quote = (
            order.status == "quote-created"
            and bool(order.quote_id)
            and order.version == request.expected_draft_version + 1
        )
        if confirmation_expired and not committed_quote:
            raise HTTPException(status_code=400, detail="Confirmation token has expired.")
        if committed_quote:
            _verified_stored_quote(order)
            store.append_plan_action(
                plan.plan_id,
                "pdf_generated",
                actor.email,
                plan_revision=plan.revision,
                draft_version=request.expected_draft_version,
                idempotency_key=request.idempotency_key.strip(),
                confirmation_token_id=claims.token_id,
                payload={
                    "quote_id": order.quote_id,
                    "recovered": True,
                    "result_order": order.model_dump(mode="json"),
                },
            )
            completed_plan = _finalize_pdf_plan(
                plan,
                order,
                expected_plan_revision=plan.revision,
            )
            return {
                "plan": _plan_payload(completed_plan, effective_view),
                "order": redact_line_items_for_view(order.model_dump(), effective_view),
            }
        _validate_plan_mutation(
            plan,
            order,
            expected_plan_revision=request.expected_plan_revision,
            expected_draft_version=request.expected_draft_version,
            actor_email=actor.email,
        )
        prepared_order, payload = _prepare_quote_payload(
            plan.draft_order_id,
            actor,
            effective_view,
            expected_version=request.expected_draft_version,
        )
        pdf = build_quote_pdf(
            quote_id=str(payload["quote_id"]),
            order_id=prepared_order.draft_order_id,
            revision_number=prepared_order.revision_number,
            account=lakebase.get_account(prepared_order.account_id),
            seller_email=actor.email,
            line_items=[line.model_dump() for line in prepared_order.line_items],
            generated_at=_quote_generated_at(payload),
            pdf_settings=_quote_pdf_settings(payload),
        )
        if not pdf:
            raise RuntimeError("Quote PDF rendering returned no content.")
        completed_order = _commit_quote(prepared_order, payload)
        _verified_stored_quote(completed_order)
        store.append_plan_action(
            plan.plan_id,
            "pdf_generated",
            actor.email,
            plan_revision=plan.revision,
            draft_version=request.expected_draft_version,
            idempotency_key=request.idempotency_key.strip(),
            confirmation_token_id=claims.token_id,
            payload={
                "quote_id": completed_order.quote_id,
                "result_order": completed_order.model_dump(mode="json"),
            },
        )
        completed_plan = _finalize_pdf_plan(
            plan,
            completed_order,
            expected_plan_revision=plan.revision,
        )
        return {
            "plan": _plan_payload(completed_plan, effective_view),
            "order": redact_line_items_for_view(completed_order.model_dump(), effective_view),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc


@app.post("/api/recommendation/view")
def recommendation_view(
    request: RecommendationViewRequest,
    http_request: Request,
) -> dict[str, object]:
    """Re-render the latest recommendation for a different viewer role (instant
    'View as' toggle) without re-invoking the agent. Redaction is applied
    server-side from the stored full recommendation."""
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    _owned_order(request.draft_order_id, actor)
    latest = store.get_latest_recommendation(request.draft_order_id)
    if not latest:
        return {}
    return redact_recommendation_for_view(latest, view_role)


@app.post("/api/followups", response_model=FollowupResponse)
async def followups(request: FollowupRequest, http_request: Request) -> FollowupResponse:
    """Suggest 3-4 contextual prompts from authoritative server-owned deal state."""

    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    order = _owned_order(request.draft_order_id, actor)
    account_id = _enforce_order_account(request.account_id, order.account_id)
    stored_recommendation = store.get_latest_recommendation(request.draft_order_id)
    latest = (
        redact_recommendation_for_view(stored_recommendation, view_role)
        if stored_recommendation
        else {}
    )
    conversation = redact_conversation_for_view(
        [
            turn.model_dump()
            for turn in store.get_conversation(request.draft_order_id)
        ],
        view_role,
    )
    try:
        suggestions = await agent_client.suggest_followups(
            account_id=account_id,
            draft_order_id=order.draft_order_id,
            draft_status=order.status,
            draft_version=order.version,
            current_order_lines=order.line_items,
            conversation_history=conversation,
            last_recommendation=latest,
            view_role=view_role,
            approval_threshold=_current_admin_settings().behavior.approval_threshold,
        )
    except Exception as exc:  # noqa: BLE001 - prompt chips are non-critical UI assistance
        logger.warning("Contextual prompt endpoint failed (%s).", type(exc).__name__)
        suggestions = []
    return FollowupResponse(suggestions=suggestions)


def _line_identity(line: DraftLineItem | dict[str, object]) -> str:
    raw = line.model_dump() if isinstance(line, DraftLineItem) else line
    if raw.get("is_addon"):
        return f"addon:{raw.get('covers_sku') or raw.get('sku')}"
    return f"sku:{raw.get('sku')}"


def _recommendation_apply_lines(
    order_lines: list[DraftLineItem],
    recommendation: dict[str, object],
    mode: str,
) -> list[DraftLineItem]:
    raw_items = recommendation.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=400, detail="Recommendation has no quote lines to apply.")
    try:
        proposed = [
            DraftLineItem.model_validate(item)
            for item in raw_items
            if isinstance(item, dict)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Recommendation contains invalid quote lines.") from exc
    if not proposed:
        raise HTTPException(status_code=400, detail="Recommendation has no quote lines to apply.")
    if mode == "replace":
        return proposed

    merged = [line.model_copy(deep=True) for line in order_lines]
    positions = {_line_identity(line): index for index, line in enumerate(merged)}
    for line in proposed:
        key = _line_identity(line)
        if key in positions:
            merged[positions[key]] = line
        else:
            positions[key] = len(merged)
            merged.append(line)
    return merged


@app.post("/api/draft-orders/{draft_order_id}/recommendations/apply")
def apply_recommendation(
    draft_order_id: str,
    request: ApplyRecommendationRequest,
    http_request: Request,
) -> dict[str, object]:
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    order = _owned_order(draft_order_id, actor)
    try:
        recommendation = store.get_recommendation(
            draft_order_id,
            request.recommendation_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recommendation not found") from exc
    recommendation_metadata = recommendation.get("metadata")
    if isinstance(recommendation_metadata, dict) and recommendation_metadata.get("plan_id"):
        raise HTTPException(
            status_code=409,
            detail="Plan recommendations must be applied through their signed confirmation action.",
        )

    try:
        repeated = store.get_applied_recommendation(
            draft_order_id,
            request.recommendation_id,
            request.expected_revision,
            request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    if repeated is not None:
        repeated["order"] = redact_line_items_for_view(repeated["order"], view_role)
        return repeated

    candidate_lines = _recommendation_apply_lines(
        order.line_items,
        recommendation,
        request.mode,
    )
    try:
        canonical_lines = _rehydrate_catalog_lines(
            candidate_lines,
            account_id=order.account_id,
        )
        result = store.apply_recommendation(
            draft_order_id,
            request.recommendation_id,
            request.expected_revision,
            request.mode,
            canonical_lines,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    result["order"] = redact_line_items_for_view(result["order"], view_role)
    return result


@app.post("/api/quote/add-line")
def add_line(request: AddLineRequest, http_request: Request) -> dict[str, object]:
    """Manually add a catalog product to the quote, priced server-side."""
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    order = _owned_order(request.draft_order_id, actor)
    account_id = _enforce_order_account(request.account_id, order.account_id)
    line = build_catalog_line(
        request.sku,
        quantity=request.quantity,
        account_id=account_id,
        max_seller_discount_pct=(
            _current_admin_settings().behavior.max_seller_discount_pct
        ),
    )
    if line is None:
        raise HTTPException(status_code=400, detail=f"Unknown SKU {request.sku}")
    next_lines = [item.model_dump() for item in order.line_items]
    existing = next((item for item in next_lines if item["sku"] == line["sku"]), None)
    if existing:
        per_unit_overpay = (line["overpay_amount"] / line["quantity"]) if line["quantity"] else 0.0
        existing["quantity"] += line["quantity"]
        existing["total_price"] = round(existing["quantity"] * existing["unit_price"], 2)
        existing["overpay_amount"] = round(per_unit_overpay * existing["quantity"], 2)
    else:
        # Equipment Care is opt-out: manually adding eligible equipment auto-attaches
        # its scaled care plan too, matching the agent-built path. Scoped to just
        # the new line so a plan the seller removed elsewhere is not resurrected.
        admin_settings = _current_admin_settings()
        if admin_settings.behavior.auto_attach_care_plan:
            account = lakebase.get_account(account_id)
            next_lines.extend(
                attach_default_care_plans([line], account, rules=warranty_rules_by_sku())
            )
        else:
            next_lines.append(line)
    try:
        canonical_lines = _rehydrate_catalog_lines(
            [DraftLineItem.model_validate(item) for item in next_lines],
            account_id=account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        updated = store.update_lines(
            request.draft_order_id,
            canonical_lines,
            expected_version=request.expected_version,
        )
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return redact_line_items_for_view(updated.model_dump(), view_role)


@app.post("/api/quote/set-price")
def set_price(request: SetPriceRequest, http_request: Request) -> dict[str, object]:
    """Reprice a line at a rep-entered net price; margin + approval recompute server-side."""
    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    admin_settings = _current_admin_settings()
    if view_role == "seller" and not admin_settings.behavior.allow_seller_price_edits:
        raise HTTPException(
            status_code=403,
            detail=(
                "Seller price edits are disabled by Workspace Settings; "
                "an authorized manager must edit the price."
            ),
        )
    order = _owned_order(request.draft_order_id, actor)
    account_id = _enforce_order_account(request.account_id, order.account_id)
    existing = next((item for item in order.line_items if item.sku == request.sku), None)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"{request.sku} not in quote")
    if existing.is_addon:
        raise HTTPException(status_code=400, detail="Care-plan prices are derived from covered equipment")
    line = reprice_catalog_line(
        request.sku,
        unit_price=request.unit_price,
        quantity=existing.quantity,
        account_id=account_id,
        max_seller_discount_pct=admin_settings.behavior.max_seller_discount_pct,
    )
    if line is None:
        raise HTTPException(status_code=400, detail=f"Unknown SKU {request.sku}")
    next_lines = [line if item.sku == request.sku else item.model_dump() for item in order.line_items]
    try:
        canonical_lines = _rehydrate_catalog_lines(
            [DraftLineItem.model_validate(item) for item in next_lines],
            account_id=account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        updated = store.update_lines(
            request.draft_order_id,
            canonical_lines,
            expected_version=request.expected_version,
        )
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return redact_line_items_for_view(updated.model_dump(), view_role)


def _prepare_quote_payload(
    draft_order_id: str,
    actor: ActorContext,
    view_role: str,
    expected_version: int | None = None,
) -> tuple[DraftOrder, dict[str, object]]:
    order = _owned_order(draft_order_id, actor)
    if expected_version is not None and order.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Draft version {expected_version} is stale; current version is {order.version}."
            ),
        )
    try:
        canonical_lines = _rehydrate_catalog_lines(order.line_items, account_id=order.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not canonical_lines:
        raise HTTPException(
            status_code=400,
            detail="Add at least one product before generating this quote.",
        )
    approval_lines = [line for line in canonical_lines if line.approval_required]
    if approval_lines:
        first_reason = approval_lines[0].approval_reason.strip()
        raise HTTPException(
            status_code=409,
            detail=(
                first_reason
                if view_role == "manager" and first_reason
                else "Pricing approval is required before this quote can be generated."
            ),
        )
    quote_total = round(sum((line.total_price or 0.0) for line in canonical_lines), 2)
    admin_settings = _current_admin_settings()
    approval_threshold = admin_settings.behavior.approval_threshold
    if quote_total > approval_threshold:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Regional VP approval is required for quotes above "
                f"${approval_threshold:,.0f}."
            ),
        )
    prepared_order = order.model_copy(
        update={
            "line_items": canonical_lines,
            "subtotal": quote_total,
            "grand_total": quote_total,
            "version": order.version + 1,
        },
        deep=True,
    )
    payload = build_quote_payload(
        order_id=prepared_order.draft_order_id,
        account_id=prepared_order.account_id,
        seller_id=actor.email,
        environment=settings.environment,
        line_items=[line.model_dump() for line in prepared_order.line_items],
        account=lakebase.get_account(prepared_order.account_id),
        approval_threshold=approval_threshold,
    )
    # Freeze the document design with the immutable quote payload so viewing a
    # previously generated quote does not silently restyle it after an admin edit.
    payload["pdf_settings"] = admin_settings.pdf.model_dump(mode="json")
    return prepared_order, payload


def _commit_quote(order: DraftOrder, payload: dict[str, object]) -> DraftOrder:
    if order.version < 1:
        raise ValueError("Prepared quote version is invalid.")
    try:
        return store.commit_quote(
            order.draft_order_id,
            payload,
            expected_version=order.version - 1,
            line_items=order.line_items,
        )
    except DraftConflict as exc:
        raise _conflict(exc) from exc


def _quote_generated_at(payload: dict[str, object]) -> datetime | None:
    value = payload.get("created_at")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _quote_pdf_settings(payload: dict[str, object]) -> QuotePdfSettings:
    snapshot = payload.get("pdf_settings")
    if isinstance(snapshot, dict):
        return QuotePdfSettings.model_validate(snapshot)
    # Compatibility for quotes generated before PDF settings were persisted.
    return _current_admin_settings().pdf


def _quote_pdf_response(
    pdf: bytes,
    *,
    quote_id: str,
    revision_number: int,
    download: bool,
) -> StreamingResponse:
    filename = f"quote-{quote_id}-r{revision_number}.pdf"
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/cpq/quote-drafts")
def create_quote_draft(
    request: QuoteDraftRequest,
    http_request: Request,
) -> dict[str, object]:
    """Compatibility JSON endpoint retained for existing API clients."""

    actor = _actor(http_request)
    view_role = actor.authorize_view(request.view_role)
    order, payload = _prepare_quote_payload(request.draft_order_id, actor, view_role)
    completed_order = _commit_quote(order, payload)
    try:
        _complete_plan_for_legacy_pdf(order.draft_order_id, completed_order, actor.email)
    except Exception:  # noqa: BLE001 - quote commit already succeeded
        logger.exception("Could not reconcile the completed quote plan after quote creation.")
    return redact_quote_payload_for_view(payload, view_role)


@app.post("/api/draft-orders/{draft_order_id}/quote.pdf")
def generate_quote_pdf(
    draft_order_id: str,
    http_request: Request,
    view_role: str = "seller",
) -> StreamingResponse:
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    order, payload = _prepare_quote_payload(draft_order_id, actor, effective_view)
    account = lakebase.get_account(order.account_id)
    pdf = build_quote_pdf(
        quote_id=str(payload["quote_id"]),
        order_id=order.draft_order_id,
        revision_number=order.revision_number,
        account=account,
        seller_email=actor.email,
        line_items=[line.model_dump() for line in order.line_items],
        generated_at=_quote_generated_at(payload),
        pdf_settings=_quote_pdf_settings(payload),
    )
    if not pdf:
        raise RuntimeError("Quote PDF rendering returned no content.")
    completed_order = _commit_quote(order, payload)
    try:
        _complete_plan_for_legacy_pdf(order.draft_order_id, completed_order, actor.email)
    except Exception:  # noqa: BLE001 - PDF/quote commit already succeeded
        logger.exception("Could not reconcile the completed quote plan after PDF generation.")
    return _quote_pdf_response(
        pdf,
        quote_id=str(payload["quote_id"]),
        revision_number=order.revision_number,
        download=True,
    )


@app.get("/api/draft-orders/{draft_order_id}/quote.pdf")
def get_quote_pdf(
    draft_order_id: str,
    http_request: Request,
    view_role: str = "seller",
    download: bool = False,
) -> StreamingResponse:
    """Render an existing immutable quote for browser viewing or download."""

    actor = _actor(http_request)
    actor.authorize_view(view_role)
    order = _owned_order(draft_order_id, actor)
    if order.status != "quote-created" or not order.quote_id:
        raise HTTPException(
            status_code=409,
            detail="Generate this quote before viewing its PDF.",
        )
    try:
        payload = store.get_quote(order.quote_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="The generated quote document could not be found.",
        ) from exc

    pdf = build_quote_pdf(
        quote_id=order.quote_id,
        order_id=order.draft_order_id,
        revision_number=order.revision_number,
        account=lakebase.get_account(order.account_id),
        seller_email=order.owner_email or actor.email,
        line_items=[line.model_dump() for line in order.line_items],
        generated_at=_quote_generated_at(payload),
        pdf_settings=_quote_pdf_settings(payload),
    )
    return _quote_pdf_response(
        pdf,
        quote_id=order.quote_id,
        revision_number=order.revision_number,
        download=download,
    )


@app.post("/api/draft-orders/{draft_order_id}/save")
def save_draft(
    draft_order_id: str,
    http_request: Request,
    view_role: str = "seller",
) -> dict[str, object]:
    """Explicitly persist the current draft so it appears in history and can be
    reloaded later. Draft lines are already written on every edit; this promotes
    a scratch draft to 'saved' status."""
    actor = _actor(http_request)
    effective_view = actor.authorize_view(view_role)
    _owned_order(draft_order_id, actor)
    try:
        saved = store.mark_saved(draft_order_id)
        return redact_line_items_for_view(saved.model_dump(), effective_view)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc


@app.get("/api/history")
def history(
    http_request: Request,
    account_id: str = "",
    view_role: str = "seller",
) -> dict[str, object]:
    """Unified history: one row per cart (saved or quoted), newest first."""
    actor = _actor(http_request)
    actor.authorize_view(view_role)
    acct = account_id or settings.default_account_id
    owner_email = None if actor.can_manage else actor.email
    return {"items": store.list_history(acct, owner_email=owner_email)}


@app.delete("/api/draft-orders/{draft_order_id}")
def delete_draft_order(draft_order_id: str, http_request: Request) -> dict[str, object]:
    """Delete an editable saved draft; sent quote records remain immutable."""
    actor = _actor(http_request)
    _owned_order(draft_order_id, actor)
    try:
        store.delete_draft(draft_order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft order not found") from exc
    except DraftConflict as exc:
        raise _conflict(exc) from exc
    return {"deleted": True}


def _conversation_history_for_request(request: SellerQueryRequest) -> list[ConversationTurn]:
    if request.draft_order_id:
        try:
            stored_history = store.get_conversation(request.draft_order_id)
            if stored_history:
                return stored_history
        except KeyError:
            pass
    history = [turn for turn in request.conversation_history if turn.content.strip()]
    if history and history[-1].role == "user" and history[-1].content.strip() == request.query.strip():
        history = history[:-1]
    return history[-8:]


def _last_recommendation_for_request(request: SellerQueryRequest) -> dict[str, object]:
    if request.draft_order_id:
        try:
            stored_recommendation = store.get_latest_recommendation(request.draft_order_id)
            if stored_recommendation:
                return stored_recommendation
        except KeyError:
            pass
    return request.recommendation_context


def _remember_turn(
    request: SellerQueryRequest,
    recommendation: CartRecommendation,
    draft_version: int | None = None,
) -> dict[str, object]:
    payload = recommendation.model_dump(mode="json")
    if not request.draft_order_id:
        return payload
    try:
        store.append_conversation_turns(
            request.draft_order_id,
            [
                ConversationTurn(role="user", content=request.query),
                ConversationTurn(role="assistant", content=_summarize_recommendation_for_memory(payload)),
            ],
        )
        stored = store.set_latest_recommendation(
            request.draft_order_id,
            payload,
            draft_version=draft_version,
        )
        _remember_genie_conversation_id(request.draft_order_id, payload)
        return stored
    except KeyError:
        return payload


def _remember_conversation_answer(request: SellerQueryRequest, payload: dict[str, object]) -> None:
    if not request.draft_order_id:
        return
    _remember_genie_conversation_id(request.draft_order_id, payload)
    answer = str(payload.get("answer") or "").strip()
    if not answer:
        return
    try:
        store.append_conversation_turns(
            request.draft_order_id,
            [
                ConversationTurn(role="user", content=request.query),
                ConversationTurn(role="assistant", content=answer),
            ],
        )
    except KeyError:
        return


def _remember_genie_conversation_id(
    draft_order_id: str,
    payload: dict[str, object],
) -> None:
    """Persist only source-typed IDs returned by the trusted tool boundary."""

    candidates: list[tuple[object, object]] = []
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        candidates.extend(
            (item.get("source"), item.get("conversation_id"))
            for item in reversed(evidence)
            if isinstance(item, dict)
        )
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(
            (
                metadata.get("genie_conversation_source"),
                metadata.get("genie_conversation_id"),
            )
        )
    candidates.append(
        (payload.get("genie_conversation_source"), payload.get("genie_conversation_id"))
    )
    conversation_reference = next(
        (
            reference
            for source, conversation_id in candidates
            if (
                reference := encode_genie_conversation_reference(
                    str(source or "").strip() or None,
                    str(conversation_id or "").strip() or None,
                )
            )
        ),
        "",
    )
    if not conversation_reference:
        return
    try:
        store.set_genie_conversation_id(draft_order_id, conversation_reference)
    except KeyError:
        return


def _summarize_recommendation_for_memory(recommendation: dict[str, object]) -> str:
    items = recommendation.get("items", [])
    if not isinstance(items, list):
        items = []
    skus = [str(item.get("sku")) for item in items[:4] if isinstance(item, dict) and item.get("sku")]
    readiness = recommendation.get("quote_readiness", [])
    approval = _signal_status(readiness, "Approval")
    protect = _signal_status(readiness, "Equipment Care")
    sku_text = ", ".join(skus) if skus else "no new cart-ready SKUs"
    return f"{len(items)} recommendation{'s' if len(items) != 1 else ''}: {sku_text}. Approval: {approval}. Equipment Care: {protect}."


def _signal_status(signals: object, label: str) -> str:
    if not isinstance(signals, list):
        return "Checked"
    for signal in signals:
        if isinstance(signal, dict) and signal.get("label") == label:
            return str(signal.get("status") or "Checked")
    return "Checked"
