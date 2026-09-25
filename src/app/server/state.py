from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .agent_plans import (
    ACTIVE_PLAN_STATUSES,
    AgentActionRecord,
    PlanStatus,
    QuotePlan,
    apply_plan_changes,
)
from .models import CPQAdminSettings, ConversationTurn, DraftLineItem, DraftOrder


class DraftConflict(RuntimeError):
    """Raised when an optimistic draft/recommendation write is stale."""


class DraftOrderStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[str, DraftOrder] = {}
        self._conversation: dict[str, list[ConversationTurn]] = {}
        self._recommendations: dict[str, dict[str, Any]] = {}
        self._recommendation_drafts: dict[str, str] = {}
        self._latest_recommendation_id: dict[str, str] = {}
        self._applied_recommendations: dict[str, dict[str, Any]] = {}
        self._genie_conversation_ids: dict[str, str] = {}
        self._quotes: dict[str, dict[str, Any]] = {}
        self._updated_at: dict[str, datetime] = {}
        self._admin_settings = CPQAdminSettings()
        self._agent_plans: dict[str, QuotePlan] = {}
        self._active_plan_ids: dict[str, str] = {}
        self._agent_actions: dict[str, list[AgentActionRecord]] = {}
        self._plan_action_idempotency: dict[tuple[str, str], AgentActionRecord] = {}
        self._used_confirmation_tokens: dict[str, AgentActionRecord] = {}

    def _touch(self, draft_order_id: str) -> None:
        self._updated_at[draft_order_id] = datetime.now(timezone.utc)

    @staticmethod
    def _copy_order(order: DraftOrder) -> DraftOrder:
        return order.model_copy(deep=True)

    @staticmethod
    def _ensure_editable(order: DraftOrder) -> None:
        if order.status == "quote-created":
            raise DraftConflict(
                "Generated quotes are immutable. Create a revision before making changes."
            )

    def create(
        self,
        account_id: str,
        line_items: list[DraftLineItem] | None = None,
        owner_email: str = "",
    ) -> DraftOrder:
        draft_order_id = f"draft-{uuid.uuid4().hex[:12]}"
        order = DraftOrder(
            draft_order_id=draft_order_id,
            account_id=account_id,
            line_items=copy.deepcopy(line_items or []),
            owner_email=owner_email.strip().casefold(),
            version=0,
        )
        self._recalculate(order)
        with self._lock:
            self._orders[draft_order_id] = order
            self._conversation[draft_order_id] = []
            self._touch(draft_order_id)
            return self._copy_order(order)

    def create_revision(
        self,
        source_draft_order_id: str,
        owner_email: str = "",
    ) -> DraftOrder:
        with self._lock:
            source = self._orders[source_draft_order_id]
            if source.status != "quote-created" or not source.quote_id:
                raise DraftConflict("Only a sent quote can be revised.")
            draft_order_id = f"draft-{uuid.uuid4().hex[:12]}"
            order = DraftOrder(
                draft_order_id=draft_order_id,
                account_id=source.account_id,
                line_items=copy.deepcopy(source.line_items),
                owner_email=(owner_email or source.owner_email).strip().casefold(),
                revision_number=source.revision_number + 1,
                parent_draft_order_id=source.draft_order_id,
                source_quote_id=source.quote_id,
                version=0,
            )
            self._recalculate(order)
            self._orders[draft_order_id] = order
            self._conversation[draft_order_id] = []
            self._touch(draft_order_id)
            return self._copy_order(order)

    def get(self, draft_order_id: str) -> DraftOrder:
        with self._lock:
            return self._copy_order(self._orders[draft_order_id])

    def find_resumable(
        self,
        account_id: str,
        owner_email: str,
    ) -> DraftOrder | None:
        owner = owner_email.strip().casefold()
        with self._lock:
            candidates = [
                order
                for order in self._orders.values()
                if order.account_id == account_id
                and order.owner_email.casefold() == owner
                and order.status in {"draft", "saved"}
                and (order.status == "saved" or bool(order.line_items))
            ]
            if not candidates:
                return None
            latest = max(
                candidates,
                key=lambda order: self._updated_at.get(
                    order.draft_order_id,
                    datetime.min.replace(tzinfo=timezone.utc),
                ),
            )
            return self._copy_order(latest)

    def get_agent_snapshot(
        self,
        draft_order_id: str,
        expected_revision: int | None = None,
    ) -> tuple[DraftOrder, str | None]:
        """Atomically capture the draft and its server-owned Genie conversation."""

        with self._lock:
            order = self._orders[draft_order_id]
            if expected_revision is not None and order.version != expected_revision:
                raise DraftConflict(
                    f"Draft version {expected_revision} is stale; current version is {order.version}."
                )
            return (
                self._copy_order(order),
                self._genie_conversation_ids.get(draft_order_id),
            )

    def get_genie_conversation_id(self, draft_order_id: str) -> str | None:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            return self._genie_conversation_ids.get(draft_order_id)

    def set_genie_conversation_id(
        self,
        draft_order_id: str,
        conversation_id: str,
    ) -> str:
        trusted_id = conversation_id.strip()
        if not trusted_id:
            raise ValueError("Genie conversation ID cannot be empty.")
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            self._genie_conversation_ids[draft_order_id] = trusted_id
            self._touch(draft_order_id)
            return trusted_id

    def claim_owner(self, draft_order_id: str, owner_email: str) -> DraftOrder:
        owner = owner_email.strip().casefold()
        if not owner:
            raise ValueError("Draft owner is required.")
        with self._lock:
            order = self._orders[draft_order_id]
            if order.owner_email and order.owner_email.casefold() != owner:
                raise DraftConflict("Draft order already has a different owner.")
            if not order.owner_email:
                order.owner_email = owner
                self._touch(draft_order_id)
            return self._copy_order(order)

    def update_lines(
        self,
        draft_order_id: str,
        line_items: list[DraftLineItem],
        expected_version: int | None = None,
    ) -> DraftOrder:
        with self._lock:
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            if expected_version is not None and order.version != expected_version:
                raise DraftConflict(
                    f"Draft version {expected_version} is stale; current version is {order.version}."
                )
            order.line_items = copy.deepcopy(line_items)
            self._recalculate(order)
            order.version += 1
            self._touch(draft_order_id)
            return self._copy_order(order)

    def attach_quote(self, draft_order_id: str, quote_id: str) -> DraftOrder:
        with self._lock:
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            order.quote_id = quote_id
            order.status = "quote-created"
            self._touch(draft_order_id)
            return self._copy_order(order)

    def get_conversation(self, draft_order_id: str) -> list[ConversationTurn]:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            return copy.deepcopy(self._conversation.get(draft_order_id, []))

    def append_conversation_turns(
        self,
        draft_order_id: str,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            existing = self._conversation.setdefault(draft_order_id, [])
            existing.extend(copy.deepcopy(turn) for turn in turns if turn.content.strip())
            self._conversation[draft_order_id] = existing[-12:]
            return copy.deepcopy(self._conversation[draft_order_id])

    def set_latest_recommendation(
        self,
        draft_order_id: str,
        recommendation: dict[str, Any],
        draft_version: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            order = self._orders[draft_order_id]
            captured_draft_version = order.version if draft_version is None else draft_version
            if captured_draft_version < 0:
                raise ValueError("Draft version cannot be negative.")
            previous_id = self._latest_recommendation_id.get(draft_order_id)
            previous = self._recommendations.get(previous_id or "", {})
            payload = copy.deepcopy(recommendation)
            recommendation_id = str(payload.get("recommendation_id") or "").strip()
            if not recommendation_id:
                recommendation_id = f"rec-{uuid.uuid4().hex}"
            existing = self._recommendations.get(recommendation_id)
            if existing and existing != payload:
                raise DraftConflict("Recommendation ID is already in use.")
            payload.update(
                {
                    "recommendation_id": recommendation_id,
                    "revision": int(previous.get("revision") or 0) + 1,
                    "draft_version": captured_draft_version,
                }
            )
            self._recommendations[recommendation_id] = payload
            self._recommendation_drafts[recommendation_id] = draft_order_id
            self._latest_recommendation_id[draft_order_id] = recommendation_id
            self._touch(draft_order_id)
            return copy.deepcopy(payload)

    def get_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            payload = self._recommendations.get(recommendation_id)
            if payload is None:
                raise KeyError(recommendation_id)
            if self._recommendation_drafts.get(recommendation_id) != draft_order_id:
                raise KeyError(recommendation_id)
            return copy.deepcopy(payload)

    def _recommendations_for_draft(self, draft_order_id: str) -> list[str]:
        return [
            recommendation_id
            for recommendation_id, owning_draft_id in self._recommendation_drafts.items()
            if owning_draft_id == draft_order_id
        ]

    def get_latest_recommendation(self, draft_order_id: str) -> dict[str, Any]:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            recommendation_id = self._latest_recommendation_id.get(draft_order_id)
            if not recommendation_id:
                return {}
            return copy.deepcopy(self._recommendations[recommendation_id])

    def _applied_result_locked(
        self,
        draft_order_id: str,
        recommendation_id: str,
        expected_revision: int,
        mode: str,
    ) -> dict[str, Any] | None:
        applied = self._applied_recommendations.get(recommendation_id)
        if applied is None:
            return None
        if (
            applied["draft_order_id"] != draft_order_id
            or int(applied["revision"]) != expected_revision
            or applied["mode"] != mode
        ):
            raise DraftConflict(
                "Recommendation retry does not match the original application."
            )
        order = self._orders[draft_order_id]
        return {
            "order": self._copy_order(order).model_dump(),
            "recommendation_id": recommendation_id,
            "revision": expected_revision,
            "mode": mode,
            "already_applied": True,
        }

    def get_applied_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
        expected_revision: int,
        mode: str,
    ) -> dict[str, Any] | None:
        """Return an exact retry from live draft state, without replaying its merge."""

        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            if self._recommendation_drafts.get(recommendation_id) != draft_order_id:
                raise KeyError(recommendation_id)
            return self._applied_result_locked(
                draft_order_id,
                recommendation_id,
                expected_revision,
                mode,
            )

    def apply_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
        expected_revision: int,
        mode: str,
        line_items: list[DraftLineItem],
    ) -> dict[str, Any]:
        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            recommendation = self._recommendations.get(recommendation_id)
            if recommendation is None or self._recommendation_drafts.get(recommendation_id) != draft_order_id:
                raise KeyError(recommendation_id)
            already_applied = self._applied_result_locked(
                draft_order_id,
                recommendation_id,
                expected_revision,
                mode,
            )
            if already_applied is not None:
                return already_applied
            if int(recommendation.get("revision") or 0) != expected_revision:
                raise DraftConflict("Recommendation revision is stale.")
            recommendation_mode = str(recommendation.get("apply_mode") or "").strip()
            if recommendation_mode in {"add", "replace"} and recommendation_mode != mode:
                raise DraftConflict("Recommendation apply mode does not match.")
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            if int(recommendation.get("draft_version") or 0) != order.version:
                raise DraftConflict("Draft changed after this recommendation was generated.")

            order.line_items = copy.deepcopy(line_items)
            self._recalculate(order)
            order.version += 1
            self._touch(draft_order_id)
            result = {
                "order": self._copy_order(order).model_dump(),
                "recommendation_id": recommendation_id,
                "revision": expected_revision,
                "mode": mode,
                "already_applied": False,
            }
            self._applied_recommendations[recommendation_id] = {
                "draft_order_id": draft_order_id,
                "revision": expected_revision,
                "mode": mode,
            }
            return result

    # -- durable agent plans -------------------------------------------- #

    @staticmethod
    def _copy_plan(plan: QuotePlan) -> QuotePlan:
        return plan.model_copy(deep=True)

    def create_plan(self, plan: QuotePlan, actor_email: str) -> QuotePlan:
        actor = actor_email.strip().casefold()
        if not actor:
            raise ValueError("Plan creator is required.")
        candidate = QuotePlan.model_validate(plan.model_dump(mode="python"))
        now = datetime.now(timezone.utc)
        with self._lock:
            order = self._orders[candidate.draft_order_id]
            if candidate.account_id != order.account_id:
                raise DraftConflict("Plan account does not match its draft order.")
            if candidate.base_draft_version != order.version:
                raise DraftConflict(
                    f"Draft version {candidate.base_draft_version} is stale; "
                    f"current version is {order.version}."
                )
            if candidate.revision != 1:
                raise DraftConflict("A new plan must start at revision 1.")
            if candidate.status not in ACTIVE_PLAN_STATUSES:
                raise DraftConflict("A new plan must start in an active status.")
            if candidate.plan_id in self._agent_plans:
                raise DraftConflict(f"Plan {candidate.plan_id} already exists.")
            active_id = self._active_plan_ids.get(candidate.draft_order_id)
            if active_id:
                raise DraftConflict(
                    f"Draft already has active plan {active_id}; resume or cancel it first."
                )
            candidate.created_by = actor
            candidate.created_at = now
            candidate.updated_at = now
            self._agent_plans[candidate.plan_id] = candidate
            self._active_plan_ids[candidate.draft_order_id] = candidate.plan_id
            self._agent_actions[candidate.plan_id] = []
            self._append_plan_action_locked(
                candidate,
                action_type="plan_created",
                actor_email=actor,
                payload={"goal": candidate.goal},
            )
            return self._copy_plan(candidate)

    def get_plan(self, plan_id: str) -> QuotePlan:
        with self._lock:
            return self._copy_plan(self._agent_plans[plan_id])

    def get_active_plan(self, draft_order_id: str) -> QuotePlan | None:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            plan_id = self._active_plan_ids.get(draft_order_id)
            if not plan_id:
                return None
            plan = self._agent_plans[plan_id]
            if plan.status not in ACTIVE_PLAN_STATUSES:
                self._active_plan_ids.pop(draft_order_id, None)
                return None
            return self._copy_plan(plan)

    def update_plan(
        self,
        plan_id: str,
        expected_revision: int,
        **changes: Any,
    ) -> QuotePlan:
        with self._lock:
            current = self._agent_plans[plan_id]
            try:
                updated = apply_plan_changes(
                    current,
                    expected_revision=expected_revision,
                    **changes,
                )
            except ValueError as exc:
                raise DraftConflict(str(exc)) from exc
            self._agent_plans[plan_id] = updated
            if updated.status in ACTIVE_PLAN_STATUSES:
                self._active_plan_ids[updated.draft_order_id] = updated.plan_id
            else:
                self._active_plan_ids.pop(updated.draft_order_id, None)
            return self._copy_plan(updated)

    def append_plan_action(
        self,
        plan_id: str,
        action_type: str,
        actor_email: str,
        *,
        plan_revision: int | None = None,
        draft_version: int | None = None,
        idempotency_key: str | None = None,
        confirmation_token_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgentActionRecord:
        with self._lock:
            plan = self._agent_plans[plan_id]
            return self._append_plan_action_locked(
                plan,
                action_type=action_type,
                actor_email=actor_email,
                plan_revision=plan_revision,
                draft_version=draft_version,
                idempotency_key=idempotency_key,
                confirmation_token_id=confirmation_token_id,
                payload=payload,
            ).model_copy(deep=True)

    def apply_confirmed_plan_scenario(
        self,
        plan_id: str,
        *,
        expected_plan_revision: int,
        expected_draft_version: int,
        scenario_id: str,
        recommendation_id: str,
        recommendation_revision: int,
        mode: str,
        line_items: list[DraftLineItem],
        actor_email: str,
        idempotency_key: str,
        confirmation_token_id: str,
        confirmation_token: str,
        next_plan_changes: dict[str, Any],
        action_payload: dict[str, Any] | None = None,
    ) -> tuple[DraftOrder, QuotePlan, AgentActionRecord]:
        """Atomically validate a confirmed scenario, mutate its draft, audit, and advance."""

        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        actor = actor_email.strip().casefold()
        normalized_idempotency = idempotency_key.strip()
        normalized_token_id = confirmation_token_id.strip()
        if not actor or not normalized_idempotency or not normalized_token_id:
            raise ValueError("Confirmed plan action identity is required.")
        with self._lock:
            current = self._agent_plans[plan_id]
            previous = self._plan_action_idempotency.get(
                (plan_id, normalized_idempotency)
            )
            if previous is not None:
                if (
                    previous.action_type != "scenario_applied"
                    or previous.actor_email != actor
                    or previous.confirmation_token_id != normalized_token_id
                    or previous.draft_version != expected_draft_version
                ):
                    raise DraftConflict(
                        "Plan action retry does not match the original action."
                    )
                result_payload = previous.payload.get("result_order")
                if not isinstance(result_payload, dict):
                    raise DraftConflict(
                        "The original plan application result is unavailable."
                    )
                result_order = DraftOrder.model_validate(result_payload)
                return (
                    result_order,
                    self._copy_plan(current),
                    previous.model_copy(deep=True),
                )
            if normalized_token_id in self._used_confirmation_tokens:
                raise DraftConflict("Confirmation token has already been used.")
            if current.status != PlanStatus.READY:
                raise DraftConflict("Only a ready quote plan can be confirmed and applied.")
            if current.revision != expected_plan_revision:
                raise DraftConflict(
                    f"Plan revision {expected_plan_revision} is stale; "
                    f"current revision is {current.revision}."
                )
            if current.selected_scenario_id != scenario_id:
                raise DraftConflict("The selected quote scenario changed before confirmation.")
            scenario = next(
                (item for item in current.scenarios if item.scenario_id == scenario_id),
                None,
            )
            if (
                scenario is None
                or scenario.recommendation_id != recommendation_id
                or scenario.recommendation_revision != recommendation_revision
            ):
                raise DraftConflict("The selected recommendation changed before confirmation.")
            proposal = current.action_proposal
            if (
                proposal is None
                or proposal.action_type != "apply_scenario"
                or proposal.scenario_id != scenario_id
                or proposal.recommendation_id != recommendation_id
                or proposal.recommendation_revision != recommendation_revision
                or proposal.plan_revision != expected_plan_revision
                or proposal.draft_version != expected_draft_version
                or proposal.idempotency_key != normalized_idempotency
                or proposal.confirmation is None
                or proposal.confirmation.token_id != normalized_token_id
                or proposal.confirmation.token != confirmation_token.strip()
            ):
                raise DraftConflict("Confirmation no longer matches the selected quote scenario.")
            order = self._orders[current.draft_order_id]
            self._ensure_editable(order)
            if order.version != expected_draft_version:
                raise DraftConflict(
                    f"Draft version {expected_draft_version} is stale; "
                    f"current version is {order.version}."
                )
            recommendation = self._recommendations.get(recommendation_id)
            if (
                recommendation is None
                or self._recommendation_drafts.get(recommendation_id)
                != current.draft_order_id
                or int(recommendation.get("revision") or 0)
                != recommendation_revision
                or int(
                    recommendation.get("draft_version")
                    if recommendation.get("draft_version") is not None
                    else -1
                ) != expected_draft_version
                or str(recommendation.get("apply_mode") or "add") != mode
            ):
                raise DraftConflict("Stored plan recommendation is stale or does not match.")
            if recommendation_id in self._applied_recommendations:
                raise DraftConflict("The plan recommendation has already been applied.")
            try:
                updated_plan = apply_plan_changes(
                    current,
                    expected_revision=expected_plan_revision,
                    **next_plan_changes,
                )
            except ValueError as exc:
                raise DraftConflict(str(exc)) from exc

            order.line_items = copy.deepcopy(line_items)
            self._recalculate(order)
            order.version += 1
            self._touch(order.draft_order_id)
            result_order = self._copy_order(order)
            self._applied_recommendations[recommendation_id] = {
                "draft_order_id": order.draft_order_id,
                "revision": recommendation_revision,
                "mode": mode,
                "result_draft_version": result_order.version,
            }
            self._agent_plans[plan_id] = updated_plan
            payload = copy.deepcopy(action_payload or {})
            payload["result_order"] = result_order.model_dump(mode="json")
            action = self._append_plan_action_locked(
                updated_plan,
                action_type="scenario_applied",
                actor_email=actor,
                plan_revision=updated_plan.revision,
                draft_version=expected_draft_version,
                idempotency_key=normalized_idempotency,
                confirmation_token_id=normalized_token_id,
                payload=payload,
            )
            return (
                result_order,
                self._copy_plan(updated_plan),
                action.model_copy(deep=True),
            )

    def _append_plan_action_locked(
        self,
        plan: QuotePlan,
        action_type: str,
        actor_email: str,
        *,
        plan_revision: int | None = None,
        draft_version: int | None = None,
        idempotency_key: str | None = None,
        confirmation_token_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgentActionRecord:
        normalized_idempotency = str(idempotency_key or "").strip() or None
        normalized_token_id = str(confirmation_token_id or "").strip() or None
        if normalized_idempotency:
            previous = self._plan_action_idempotency.get(
                (plan.plan_id, normalized_idempotency)
            )
            if previous is not None:
                if (
                    previous.action_type != action_type.strip()
                    or previous.actor_email != actor_email.strip().casefold()
                    or previous.confirmation_token_id != normalized_token_id
                    or (
                        draft_version is not None
                        and previous.draft_version != draft_version
                    )
                ):
                    raise DraftConflict(
                        "Plan action retry does not match the original action."
                    )
                return previous
        if normalized_token_id and normalized_token_id in self._used_confirmation_tokens:
            raise DraftConflict("Confirmation token has already been used.")
        trusted_plan_revision = plan.revision if plan_revision is None else plan_revision
        if trusted_plan_revision != plan.revision:
            raise DraftConflict(
                f"Plan revision {trusted_plan_revision} is stale; current revision is {plan.revision}."
            )
        action = AgentActionRecord(
            plan_id=plan.plan_id,
            draft_order_id=plan.draft_order_id,
            account_id=plan.account_id,
            action_type=action_type,
            actor_email=actor_email,
            plan_revision=trusted_plan_revision,
            draft_version=(
                plan.base_draft_version if draft_version is None else draft_version
            ),
            idempotency_key=normalized_idempotency,
            confirmation_token_id=normalized_token_id,
            payload=copy.deepcopy(payload or {}),
        )
        self._agent_actions.setdefault(plan.plan_id, []).append(action)
        if normalized_idempotency:
            self._plan_action_idempotency[(plan.plan_id, normalized_idempotency)] = action
        if normalized_token_id:
            self._used_confirmation_tokens[normalized_token_id] = action
        return action

    def list_plan_actions(self, plan_id: str) -> list[AgentActionRecord]:
        with self._lock:
            if plan_id not in self._agent_plans:
                raise KeyError(plan_id)
            return [
                action.model_copy(deep=True)
                for action in self._agent_actions.get(plan_id, [])
            ]

    def cancel_plan(
        self,
        plan_id: str,
        expected_revision: int,
        actor_email: str,
        reason: str = "",
    ) -> QuotePlan:
        with self._lock:
            current = self._agent_plans[plan_id]
            if current.status == PlanStatus.CANCELLED:
                return self._copy_plan(current)
            metadata = copy.deepcopy(current.metadata)
            if reason.strip():
                metadata["cancellation_reason"] = reason.strip()
            try:
                updated = apply_plan_changes(
                    current,
                    expected_revision=expected_revision,
                    status=PlanStatus.CANCELLED,
                    metadata=metadata,
                )
            except ValueError as exc:
                raise DraftConflict(str(exc)) from exc
            self._agent_plans[plan_id] = updated
            self._active_plan_ids.pop(updated.draft_order_id, None)
            self._append_plan_action_locked(
                updated,
                action_type="plan_cancelled",
                actor_email=actor_email,
                payload={"reason": reason.strip()},
            )
            return self._copy_plan(updated)

    def save_quote(
        self,
        quote_id: str,
        draft_order_id: str,
        account_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            self._quotes[quote_id] = copy.deepcopy(payload)

    def commit_quote(
        self,
        draft_order_id: str,
        payload: dict[str, Any],
        *,
        expected_version: int,
        line_items: list[DraftLineItem],
    ) -> DraftOrder:
        """Persist canonical lines, version, and immutable quote under one lock."""

        quote_id = str(payload.get("quote_id") or "").strip()
        if not quote_id:
            raise ValueError("Quote payload is missing quote_id.")
        stored_payload = copy.deepcopy(payload)
        stored_lines = copy.deepcopy(line_items)
        with self._lock:
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            if order.version != expected_version:
                raise DraftConflict(
                    f"Draft version {expected_version} is stale; "
                    f"current version is {order.version}."
                )
            order.line_items = stored_lines
            self._recalculate(order)
            order.version += 1
            self._quotes[quote_id] = stored_payload
            order.quote_id = quote_id
            order.status = "quote-created"
            self._touch(draft_order_id)
            return self._copy_order(order)

    def get_quote(self, quote_id: str) -> dict[str, Any]:
        """Return an isolated copy of a generated quote's immutable payload."""

        with self._lock:
            return copy.deepcopy(self._quotes[quote_id])

    def get_admin_settings(self) -> CPQAdminSettings:
        with self._lock:
            return self._admin_settings.model_copy(deep=True)

    def save_admin_settings(
        self,
        settings: CPQAdminSettings,
        *,
        updated_by: str,
    ) -> CPQAdminSettings:
        del updated_by  # Lakebase records this audit field; memory mode is process-local.
        with self._lock:
            self._admin_settings = settings.model_copy(deep=True)
            return self._admin_settings.model_copy(deep=True)

    def mark_saved(self, draft_order_id: str) -> DraftOrder:
        with self._lock:
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            if order.status == "draft":
                order.status = "saved"
            self._touch(draft_order_id)
            return self._copy_order(order)

    def list_history(
        self,
        account_id: str,
        owner_email: str | None = None,
    ) -> list[dict[str, Any]]:
        owner = owner_email.strip().casefold() if owner_email else None
        with self._lock:
            rows = [
                {
                    "draft_order_id": order.draft_order_id,
                    "status": order.status,
                    "grand_total": order.grand_total,
                    "quote_id": order.quote_id,
                    "line_count": len(order.line_items),
                    "version": order.version,
                    "revision_number": order.revision_number,
                    "parent_draft_order_id": order.parent_draft_order_id,
                    "source_quote_id": order.source_quote_id,
                    "updated_at": (
                        self._updated_at.get(order.draft_order_id)
                        or datetime.now(timezone.utc)
                    ).isoformat(),
                }
                for order in self._orders.values()
                if order.account_id == account_id
                and order.status in ("saved", "quote-created")
                and (owner is None or order.owner_email.casefold() == owner)
            ]
            return sorted(rows, key=lambda row: row["updated_at"], reverse=True)

    def delete_draft(self, draft_order_id: str) -> None:
        with self._lock:
            if draft_order_id not in self._orders:
                raise KeyError(draft_order_id)
            order = self._orders[draft_order_id]
            self._ensure_editable(order)
            order = self._orders.pop(draft_order_id)
            self._conversation.pop(draft_order_id, None)
            self._genie_conversation_ids.pop(draft_order_id, None)
            recommendation_ids = self._recommendations_for_draft(draft_order_id)
            for recommendation_id in recommendation_ids:
                self._recommendations.pop(recommendation_id, None)
                self._recommendation_drafts.pop(recommendation_id, None)
                self._applied_recommendations.pop(recommendation_id, None)
            self._latest_recommendation_id.pop(draft_order_id, None)
            self._updated_at.pop(draft_order_id, None)
            plan_ids = [
                plan_id
                for plan_id, plan in self._agent_plans.items()
                if plan.draft_order_id == draft_order_id
            ]
            for plan_id in plan_ids:
                for action in self._agent_actions.pop(plan_id, []):
                    if action.idempotency_key:
                        self._plan_action_idempotency.pop(
                            (plan_id, action.idempotency_key), None
                        )
                    if action.confirmation_token_id:
                        self._used_confirmation_tokens.pop(
                            action.confirmation_token_id, None
                        )
                self._agent_plans.pop(plan_id, None)
            self._active_plan_ids.pop(draft_order_id, None)
            if order.quote_id:
                self._quotes.pop(order.quote_id, None)

    @staticmethod
    def _recalculate(order: DraftOrder) -> None:
        subtotal = round(sum((line.total_price or 0.0) for line in order.line_items), 2)
        order.subtotal = subtotal
        order.grand_total = subtotal
