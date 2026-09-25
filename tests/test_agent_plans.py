from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server import lakebase
from server.agent_plans import (
    ActionProposal,
    ConfirmationTokenError,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    QuotePlan,
    QuoteScenario,
    issue_confirmation_token,
    verify_confirmation_token,
)
from server.models import CartRecommendation
from server.state import DraftConflict, DraftOrderStore


def _plan(draft_order_id: str, *, account_id: str = "acct-riverfront", version: int = 0) -> QuotePlan:
    return QuotePlan(
        account_id=account_id,
        draft_order_id=draft_order_id,
        draft_version=version,
        goal="Build a complete imaging quote.",
        steps=[PlanStep(title="Build options", status=PlanStepStatus.IN_PROGRESS)],
    )


def test_plan_contract_carries_deterministic_scenario_and_is_json_safe() -> None:
    recommendation = CartRecommendation(
        mode="build",
        summary="Balanced imaging package",
        recommendation_id="rec-1",
        revision=3,
    )
    scenario = QuoteScenario(
        scenario_id="balanced",
        title="Balanced",
        recommendation=recommendation,
        estimated_total=77_759.0,
        is_recommended=True,
    )
    proposal = ActionProposal(
        summary="Apply the balanced package",
        scenario_id=scenario.scenario_id,
        recommendation_id=scenario.recommendation_id,
        recommendation_revision=scenario.recommendation_revision,
        draft_version=4,
        plan_revision=2,
    )
    plan = QuotePlan(
        account_id="acct-riverfront",
        draft_order_id="draft-1",
        draft_version=4,
        goal="Prepare the best-fit quote",
        scenarios=[scenario],
        selected_scenario_id="balanced",
        action_proposal=proposal,
    )

    assert plan.base_draft_version == 4
    assert plan.draft_version == 4
    assert scenario.recommendation_id == "rec-1"
    assert scenario.recommendation_revision == 3
    assert json.loads(json.dumps(plan.model_dump(mode="json")))["status"] == "planning"


def test_confirmation_token_is_signed_expiring_and_context_bound() -> None:
    now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    issued = issue_confirmation_token(
        secret="a-production-strength-confirmation-secret",
        actor_email="Seller@Example.com",
        account_id="acct-riverfront",
        draft_order_id="draft-1",
        draft_version=4,
        plan_id="plan-1",
        plan_revision=2,
        idempotency_key="apply-plan-1-r2",
        ttl_seconds=60,
        now=now,
    )

    claims = verify_confirmation_token(
        issued.token,
        secret="a-production-strength-confirmation-secret",
        actor_email="seller@example.com",
        account_id="acct-riverfront",
        draft_order_id="draft-1",
        draft_version=4,
        plan_id="plan-1",
        plan_revision=2,
        idempotency_key="apply-plan-1-r2",
        now=now + timedelta(seconds=30),
    )
    assert claims.token_id == issued.token_id
    assert claims.actor_email == "seller@example.com"

    with pytest.raises(ConfirmationTokenError, match="draft version"):
        verify_confirmation_token(
            issued.token,
            secret="a-production-strength-confirmation-secret",
            draft_version=5,
            now=now,
        )
    with pytest.raises(ConfirmationTokenError, match="expired"):
        verify_confirmation_token(
            issued.token,
            secret="a-production-strength-confirmation-secret",
            now=now + timedelta(seconds=60),
        )
    tampered = ("A" if issued.token[0] != "A" else "B") + issued.token[1:]
    with pytest.raises(ConfirmationTokenError):
        verify_confirmation_token(
            tampered,
            secret="a-production-strength-confirmation-secret",
            now=now,
        )


def test_memory_store_enforces_one_active_plan_revisioning_and_idempotent_cancel() -> None:
    store = DraftOrderStore()
    order = store.create("acct-riverfront", owner_email="seller@example.com")
    created = store.create_plan(_plan(order.draft_order_id), "Seller@Example.com")

    assert created.created_by == "seller@example.com"
    assert store.get_active_plan(order.draft_order_id) == created
    created.goal = "Mutated outside the store"
    assert store.get_plan(created.plan_id).goal == "Build a complete imaging quote."

    with pytest.raises(DraftConflict, match=created.plan_id):
        store.create_plan(_plan(order.draft_order_id), "seller@example.com")

    scenario = QuoteScenario(scenario_id="balanced", title="Balanced")
    ready = store.update_plan(
        created.plan_id,
        expected_revision=1,
        status=PlanStatus.READY,
        scenarios=[scenario],
        selected_scenario_id=scenario.scenario_id,
    )
    assert ready.revision == 2
    assert ready.status == PlanStatus.READY
    with pytest.raises(DraftConflict, match="stale"):
        store.update_plan(created.plan_id, expected_revision=1, goal="Old write")

    cancelled = store.cancel_plan(
        created.plan_id,
        expected_revision=2,
        actor_email="seller@example.com",
        reason="Customer paused",
    )
    repeated = store.cancel_plan(
        created.plan_id,
        expected_revision=2,
        actor_email="seller@example.com",
        reason="Ignored on exact retry",
    )
    assert cancelled.status == PlanStatus.CANCELLED
    assert cancelled.revision == 3
    assert repeated == cancelled
    assert store.get_active_plan(order.draft_order_id) is None
    with pytest.raises(DraftConflict, match="read-only"):
        store.update_plan(cancelled.plan_id, expected_revision=3, goal="Revive")

    replacement = store.create_plan(_plan(order.draft_order_id), "seller@example.com")
    assert store.get_active_plan(order.draft_order_id).plan_id == replacement.plan_id
    assert store.get_plan(cancelled.plan_id).status == PlanStatus.CANCELLED


def test_memory_store_rejects_plan_for_wrong_account_or_stale_draft() -> None:
    store = DraftOrderStore()
    order = store.create("acct-riverfront")

    with pytest.raises(DraftConflict, match="account"):
        store.create_plan(
            _plan(order.draft_order_id, account_id="acct-other"),
            "seller@example.com",
        )
    store.update_lines(order.draft_order_id, [])
    with pytest.raises(DraftConflict, match="stale"):
        store.create_plan(_plan(order.draft_order_id, version=0), "seller@example.com")


def test_plan_actions_are_append_only_one_use_and_idempotently_retrievable() -> None:
    store = DraftOrderStore()
    order = store.create("acct-riverfront")
    plan = store.create_plan(_plan(order.draft_order_id), "seller@example.com")
    confirmed = store.append_plan_action(
        plan.plan_id,
        "scenario_applied",
        "seller@example.com",
        plan_revision=plan.revision,
        draft_version=order.version,
        idempotency_key="apply-once",
        confirmation_token_id="confirm-once",
        payload={"result": {"version": 1}},
    )
    updated = store.update_plan(
        plan.plan_id,
        expected_revision=plan.revision,
        status=PlanStatus.READY,
    )

    retry = store.append_plan_action(
        plan.plan_id,
        "scenario_applied",
        "seller@example.com",
        plan_revision=plan.revision,
        draft_version=order.version,
        idempotency_key="apply-once",
        confirmation_token_id="confirm-once",
    )
    assert updated.revision == 2
    assert retry.action_id == confirmed.action_id
    assert retry.payload == {"result": {"version": 1}}
    assert [action.action_type for action in store.list_plan_actions(plan.plan_id)] == [
        "plan_created",
        "scenario_applied",
    ]

    with pytest.raises(DraftConflict, match="does not match"):
        store.append_plan_action(
            plan.plan_id,
            "different_action",
            "seller@example.com",
            idempotency_key="apply-once",
            confirmation_token_id="confirm-once",
        )
    with pytest.raises(DraftConflict, match="already been used"):
        store.append_plan_action(
            plan.plan_id,
            "scenario_applied",
            "seller@example.com",
            plan_revision=updated.revision,
            idempotency_key="another-key",
            confirmation_token_id="confirm-once",
        )


def test_deleting_draft_cascades_memory_plan_state() -> None:
    store = DraftOrderStore()
    order = store.create("acct-riverfront")
    plan = store.create_plan(_plan(order.draft_order_id), "seller@example.com")

    store.delete_draft(order.draft_order_id)

    with pytest.raises(KeyError):
        store.get_plan(plan.plan_id)
    with pytest.raises(KeyError):
        store.list_plan_actions(plan.plan_id)


def test_lakebase_schema_and_row_rehydration_cover_plan_contract() -> None:
    assert "CREATE TABLE IF NOT EXISTS agent_plans" in lakebase._SCHEMA_SQL
    assert "agent_plans_one_active_per_draft" in lakebase._SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS agent_actions" in lakebase._SCHEMA_SQL
    assert "agent_actions_confirmation_once" in lakebase._SCHEMA_SQL

    plan = QuotePlan(
        plan_id="plan-1",
        account_id="acct-riverfront",
        draft_order_id="draft-1",
        draft_version=2,
        goal="Create a quote",
    )
    now = datetime.now(UTC)
    row = {
        "plan_id": plan.plan_id,
        "account_id": plan.account_id,
        "draft_order_id": plan.draft_order_id,
        "base_draft_version": 2,
        "revision": 4,
        "status": "ready",
        "created_by": "seller@example.com",
        "payload": plan.model_dump(mode="json"),
        "created_at": now,
        "updated_at": now,
    }

    loaded = lakebase._plan_from_row(row)

    assert loaded.revision == 4
    assert loaded.status == PlanStatus.READY
    assert loaded.created_by == "seller@example.com"
    json.dumps(loaded.model_dump(mode="json"))
