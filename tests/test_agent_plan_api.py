from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server import main
from server.agent_plans import (
    ConfirmationTokenError,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    QuotePlan,
    QuoteScenario,
)
from server.main import app
from server.models import CartRecommendation, DraftLineItem
from server.state import DraftOrderStore


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        plans_enabled=True,
        is_databricks_app=False,
        manager_email_allowlist=frozenset(),
        databricks_app_name="agentic-cpq-test",
        environment="test",
        default_account_id="acct-riverfront",
        quote_agent_name="Agentic CPQ",
        genie_space_title="Test Genie",
        use_mock_fallback=False,
    )


class FakePlanner:
    def __init__(self, *, needs_input: bool = False, quantity: int = 1) -> None:
        self.needs_input = needs_input
        self.quantity = quantity
        self.calls: list[dict] = []

    def should_create_plan(self, query: str, intent: str = "auto") -> bool:
        return bool(query.strip()) and intent != "research"

    async def plan_quote(self, **kwargs) -> QuotePlan:
        self.calls.append(kwargs)
        if self.needs_input:
            self.needs_input = False
            return QuotePlan(
                plan_id=kwargs["plan_id"],
                account_id=kwargs["account_id"],
                draft_order_id=kwargs["draft_order_id"],
                draft_version=kwargs["draft_version"],
                revision=kwargs["plan_revision"],
                goal=kwargs["goal"],
                status=PlanStatus.NEEDS_INPUT,
                steps=[
                    PlanStep(title="Goal", status=PlanStepStatus.COMPLETED),
                    PlanStep(
                        title="Build options",
                        status=PlanStepStatus.NEEDS_INPUT,
                        detail="How many operatories should this cover?",
                    ),
                ],
                metadata={
                    "summary": "One detail is needed.",
                    "clarifying_question": "How many operatories should this cover?",
                },
            )

        line = main.build_catalog_line(
            "SOFT-PRACTICE-12",
            quantity=self.quantity,
            account_id=kwargs["account_id"],
        )
        assert line is not None
        line["rationale"] = "Adds account-appropriate practice software."
        recommendation = CartRecommendation(
            mode="openai_agents_sdk",
            apply_mode="add",
            summary="Software quote option",
            bundle_rationale="Fits the selected account's workflow.",
            items=[line],
            recommendation_id=f"rec-{uuid4().hex}",
            revision=1,
            draft_version=kwargs["draft_version"],
        )
        scenario = QuoteScenario(
            scenario_id=f"scenario-{uuid4().hex}",
            title="Balanced",
            summary="Balanced upfront cost",
            recommendation=recommendation,
            is_recommended=True,
        )
        return QuotePlan(
            plan_id=kwargs["plan_id"],
            account_id=kwargs["account_id"],
            draft_order_id=kwargs["draft_order_id"],
            draft_version=kwargs["draft_version"],
            revision=kwargs["plan_revision"],
            goal=kwargs["goal"],
            status=PlanStatus.READY,
            steps=[
                PlanStep(title="Goal", status=PlanStepStatus.COMPLETED),
                PlanStep(title="Build options", status=PlanStepStatus.COMPLETED),
                PlanStep(
                    title="Review changes",
                    status=PlanStepStatus.IN_PROGRESS,
                    requires_confirmation=True,
                ),
            ],
            scenarios=[scenario],
            selected_scenario_id=scenario.scenario_id,
            metadata={"summary": "Prepared one grounded quote option."},
        )


@pytest.fixture
def plan_api(monkeypatch):
    memory_store = DraftOrderStore()
    planner = FakePlanner()
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _settings())
    monkeypatch.setattr(main, "agent_client", planner)
    return TestClient(app), planner, memory_store


def _create_draft(client: TestClient) -> dict:
    response = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    )
    assert response.status_code == 200
    return response.json()


def _stream_plan(client: TestClient, draft: dict) -> dict:
    response = client.post(
        "/api/agent/stream",
        json={
            "query": "Build a software quote for this account.",
            "draft_order_id": draft["draft_order_id"],
            "account_id": draft["account_id"],
            "expected_revision": draft["version"],
        },
    )
    assert response.status_code == 200
    assert response.text.count("event: plan") == 2
    active = client.get(
        f"/api/draft-orders/{draft['draft_order_id']}/agent-plan"
    )
    assert active.status_code == 200
    return active.json()


def test_stream_persists_redacted_confirmable_plan(plan_api) -> None:
    client, planner, memory_store = plan_api
    draft = _create_draft(client)

    plan = _stream_plan(client, draft)

    assert len(planner.calls) == 1
    assert plan["status"] == "ready"
    assert plan["scenarios"][0]["summary"] == "Balanced upfront cost"
    assert plan["scenarios"][0]["recommendation"]["items"][0]["supplier_cost"] is None
    assert plan["action_proposal"]["confirmation"]["token"]
    stored = memory_store.get_plan(plan["plan_id"])
    assert stored.scenarios[0].recommendation.items[0].supplier_cost is not None


def test_plan_apply_is_confirmed_idempotent_and_cannot_use_legacy_bypass(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    scenario = plan["scenarios"][0]

    bypass = client.post(
        f"/api/draft-orders/{draft['draft_order_id']}/recommendations/apply",
        json={
            "recommendation_id": scenario["recommendation_id"],
            "expected_revision": scenario["recommendation_revision"],
            "mode": "add",
        },
    )
    assert bypass.status_code == 409

    confirmation = plan["action_proposal"]["confirmation"]
    request = {
        "expected_plan_revision": plan["revision"],
        "expected_draft_version": draft["version"],
        "view_role": "seller",
        "confirmation_token": confirmation["token"],
        "idempotency_key": confirmation["idempotency_key"],
    }
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json=request,
    )
    repeated = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json=request,
    )

    assert applied.status_code == 200
    assert repeated.status_code == 200
    assert applied.json()["order"]["version"] == 1
    assert repeated.json()["order"]["version"] == 1
    assert applied.json()["plan"]["status"] == "ready_for_pdf"
    assert sum(
        action.action_type == "scenario_applied"
        for action in memory_store.list_plan_actions(plan["plan_id"])
    ) == 1


def test_confirm_pdf_completes_plan_and_is_idempotent(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]
    pdf_request = {
        "expected_plan_revision": applied["plan"]["revision"],
        "expected_draft_version": applied["order"]["version"],
        "confirmation_token": pdf_confirmation["token"],
        "idempotency_key": pdf_confirmation["idempotency_key"],
    }

    completed = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json=pdf_request,
    )
    repeated = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json=pdf_request,
    )

    assert completed.status_code == 200
    assert repeated.status_code == 200
    assert completed.json()["plan"]["status"] == "completed"
    assert completed.json()["order"]["status"] == "quote-created"
    assert sum(
        action.action_type == "pdf_generated"
        for action in memory_store.list_plan_actions(plan["plan_id"])
    ) == 1


def test_stale_active_plan_is_retired_before_replanning(plan_api) -> None:
    client, planner, memory_store = plan_api
    draft = _create_draft(client)
    first = _stream_plan(client, draft)
    changed = client.patch(
        f"/api/draft-orders/{draft['draft_order_id']}",
        json={"line_items": [], "expected_version": draft["version"]},
    )
    assert changed.status_code == 200

    stale = client.get(
        f"/api/draft-orders/{draft['draft_order_id']}/agent-plan"
    )
    assert stale.status_code == 200
    assert stale.json()["status"] == "stale"
    replacement = client.post(
        "/api/agent/stream",
        json={
            "query": "Build an updated software quote.",
            "draft_order_id": draft["draft_order_id"],
            "expected_revision": changed.json()["version"],
        },
    )
    assert replacement.status_code == 200
    assert "event: plan" in replacement.text
    active = memory_store.get_active_plan(draft["draft_order_id"])
    assert active is not None
    assert active.plan_id != first["plan_id"]
    assert len(planner.calls) == 2


def test_needs_input_plan_resumes_in_place(plan_api, monkeypatch) -> None:
    client, _, memory_store = plan_api
    planner = FakePlanner(needs_input=True)
    monkeypatch.setattr(main, "agent_client", planner)
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    assert plan["status"] == "needs_input"

    resumed = client.post(
        f"/api/agent/plans/{plan['plan_id']}/resume",
        json={
            "input": "Three operatories",
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
        },
    )

    assert resumed.status_code == 200
    payload = resumed.json()
    assert payload["plan_id"] == plan["plan_id"]
    assert payload["status"] == "ready"
    assert payload["revision"] == plan["revision"] + 2
    assert "clarifying_question" not in payload["metadata"]
    assert memory_store.get_active_plan(plan["draft_order_id"]).plan_id == plan["plan_id"]


def test_blocking_query_is_plan_aware_and_conflicts_with_current_active_plan(plan_api) -> None:
    client, planner, memory_store = plan_api
    draft = _create_draft(client)
    request = {
        "query": "Build a software quote.",
        "draft_order_id": draft["draft_order_id"],
        "expected_revision": draft["version"],
    }

    first = client.post("/api/agent/query", json=request)
    second = client.post("/api/agent/query", json=request)

    assert first.status_code == 200
    assert first.json()["status"] == "ready"
    assert memory_store.get_active_plan(draft["draft_order_id"]) is not None
    assert second.status_code == 409
    assert "resume or cancel" in second.json()["detail"]
    assert len(planner.calls) == 1


def test_stale_plan_is_auto_retired_without_prior_get(plan_api) -> None:
    client, planner, memory_store = plan_api
    draft = _create_draft(client)
    first = _stream_plan(client, draft)
    changed = client.patch(
        f"/api/draft-orders/{draft['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    ).json()

    replacement = client.post(
        "/api/agent/query",
        json={
            "query": "Build an updated software quote.",
            "draft_order_id": draft["draft_order_id"],
            "expected_revision": changed["version"],
        },
    )

    assert replacement.status_code == 200
    assert replacement.json()["plan_id"] != first["plan_id"]
    assert memory_store.get_plan(first["plan_id"]).status == PlanStatus.STALE
    assert len(planner.calls) == 2


def test_get_renews_confirmation_after_server_secret_rotation(plan_api, monkeypatch) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    old_token = plan["action_proposal"]["confirmation"]["token"]
    monkeypatch.setattr(main, "_plan_confirmation_secret", b"rotated-process-secret")

    renewed = client.get(
        f"/api/draft-orders/{draft['draft_order_id']}/agent-plan"
    )

    assert renewed.status_code == 200
    assert renewed.json()["revision"] == plan["revision"] + 1
    assert renewed.json()["action_proposal"]["confirmation"]["token"] != old_token
    assert memory_store.get_plan(plan["plan_id"]).revision == plan["revision"] + 1


def test_existing_pdf_route_completes_ready_for_pdf_plan(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    ).json()
    assert applied["plan"]["status"] == "ready_for_pdf"

    pdf = client.post(f"/api/draft-orders/{draft['draft_order_id']}/quote.pdf")

    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.COMPLETED
    assert memory_store.get_active_plan(draft["draft_order_id"]) is None


def test_approval_gate_blocks_pdf_and_post_apply_cancel(plan_api, monkeypatch) -> None:
    client, _, memory_store = plan_api
    planner = FakePlanner(quantity=20)
    monkeypatch.setattr(main, "agent_client", planner)
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    )

    assert applied.status_code == 200
    blocked = applied.json()["plan"]
    assert blocked["status"] == "awaiting_approval"
    assert blocked["action_proposal"] is None
    cancel = client.post(
        f"/api/agent/plans/{plan['plan_id']}/cancel",
        json={
            "expected_plan_revision": blocked["revision"],
            "expected_draft_version": applied.json()["order"]["version"],
        },
    )
    assert cancel.status_code == 409
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.AWAITING_APPROVAL


def test_confirm_apply_recovers_write_completed_before_action_audit(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    scenario = memory_store.get_plan(plan["plan_id"]).scenarios[0]
    recommendation = memory_store.get_recommendation(
        draft["draft_order_id"],
        scenario.recommendation_id,
    )
    order = memory_store.get(draft["draft_order_id"])
    candidate = main._recommendation_apply_lines(
        order.line_items,
        recommendation,
        "add",
    )
    canonical = main._rehydrate_catalog_lines(
        candidate,
        account_id=order.account_id,
    )
    memory_store.apply_recommendation(
        order.draft_order_id,
        scenario.recommendation_id,
        scenario.recommendation_revision,
        "add",
        canonical,
    )
    confirmation = plan["action_proposal"]["confirmation"]

    recovered = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    )

    assert recovered.status_code == 200
    assert recovered.json()["order"]["version"] == 1
    assert recovered.json()["plan"]["status"] == "ready_for_pdf"
    action = next(
        action
        for action in memory_store.list_plan_actions(plan["plan_id"])
        if action.action_type == "scenario_applied"
    )
    assert action.payload["recovered"] is True


def test_confirm_pdf_recovers_committed_quote_before_plan_audit(
    plan_api,
    monkeypatch,
) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    monkeypatch.setattr(
        main,
        "_complete_plan_for_legacy_pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    committed = client.post(f"/api/draft-orders/{draft['draft_order_id']}/quote.pdf")
    assert committed.status_code == 200
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.READY_FOR_PDF
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]

    recovered = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json={
            "expected_plan_revision": applied["plan"]["revision"],
            "expected_draft_version": applied["order"]["version"],
            "confirmation_token": pdf_confirmation["token"],
            "idempotency_key": pdf_confirmation["idempotency_key"],
        },
    )

    assert recovered.status_code == 200
    assert recovered.json()["plan"]["status"] == "completed"
    assert recovered.json()["order"]["status"] == "quote-created"


def test_confirm_apply_rejects_recovery_after_intervening_draft_edit(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    scenario = memory_store.get_plan(plan["plan_id"]).scenarios[0]
    recommendation = memory_store.get_recommendation(
        draft["draft_order_id"],
        scenario.recommendation_id,
    )
    order = memory_store.get(draft["draft_order_id"])
    canonical = main._rehydrate_catalog_lines(
        main._recommendation_apply_lines(order.line_items, recommendation, "add"),
        account_id=order.account_id,
    )
    applied = memory_store.apply_recommendation(
        order.draft_order_id,
        scenario.recommendation_id,
        scenario.recommendation_revision,
        "add",
        canonical,
    )
    memory_store.update_lines(
        order.draft_order_id,
        [DraftLineItem.model_validate(line) for line in applied["order"]["line_items"]],
        expected_version=applied["order"]["version"],
    )
    confirmation = plan["action_proposal"]["confirmation"]

    recovered = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    )

    assert recovered.status_code == 409
    assert memory_store.get(draft["draft_order_id"]).version == draft["version"] + 2
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.STALE
    assert not any(
        action.action_type == "scenario_applied"
        for action in memory_store.list_plan_actions(plan["plan_id"])
    )


def test_confirm_apply_plan_revision_race_does_not_mutate_draft(
    plan_api,
    monkeypatch,
) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    confirmation = plan["action_proposal"]["confirmation"]
    original_apply = memory_store.apply_confirmed_plan_scenario

    def advance_plan_before_apply(plan_id: str, **kwargs):
        current = memory_store.get_plan(plan_id)
        metadata = dict(current.metadata)
        metadata["concurrent_change"] = True
        memory_store.update_plan(
            plan_id,
            expected_revision=current.revision,
            metadata=metadata,
        )
        return original_apply(plan_id, **kwargs)

    monkeypatch.setattr(
        memory_store,
        "apply_confirmed_plan_scenario",
        advance_plan_before_apply,
    )

    response = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    )

    assert response.status_code == 409
    unchanged = memory_store.get(draft["draft_order_id"])
    assert unchanged.version == draft["version"]
    assert unchanged.line_items == []


def test_confirm_pdf_retry_repairs_plan_after_action_audit(
    plan_api,
    monkeypatch,
) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]
    pdf_request = {
        "expected_plan_revision": applied["plan"]["revision"],
        "expected_draft_version": applied["order"]["version"],
        "confirmation_token": pdf_confirmation["token"],
        "idempotency_key": pdf_confirmation["idempotency_key"],
    }
    original_finalize = main._finalize_pdf_plan
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated crash after PDF action audit")
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(main, "_finalize_pdf_plan", fail_once)

    with pytest.raises(RuntimeError, match="simulated crash"):
        client.post(
            f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
            json=pdf_request,
        )

    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.READY_FOR_PDF
    assert memory_store.get(draft["draft_order_id"]).status == "quote-created"
    repaired = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json=pdf_request,
    )

    assert repaired.status_code == 200
    assert repaired.json()["plan"]["status"] == "completed"
    assert calls == 2


def test_confirm_pdf_recovery_refuses_missing_stored_quote(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    live = memory_store.get(draft["draft_order_id"])
    memory_store.update_lines(
        live.draft_order_id,
        live.line_items,
        expected_version=live.version,
    )
    memory_store.attach_quote(live.draft_order_id, "Q-MISSING-PAYLOAD")
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]

    response = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json={
            "expected_plan_revision": applied["plan"]["revision"],
            "expected_draft_version": applied["order"]["version"],
            "confirmation_token": pdf_confirmation["token"],
            "idempotency_key": pdf_confirmation["idempotency_key"],
        },
    )

    assert response.status_code == 409
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.READY_FOR_PDF
    assert not any(
        action.action_type == "pdf_generated"
        for action in memory_store.list_plan_actions(plan["plan_id"])
    )


def test_plan_responses_disable_caching(plan_api) -> None:
    client, _, _ = plan_api
    draft = _create_draft(client)
    empty = client.get(f"/api/draft-orders/{draft['draft_order_id']}/agent-plan")
    assert empty.status_code == 204
    assert empty.headers["cache-control"] == "no-store"

    query_draft = _create_draft(client)
    query = client.post(
        "/api/agent/query",
        json={
            "query": "Build a software quote.",
            "draft_order_id": query_draft["draft_order_id"],
            "expected_revision": query_draft["version"],
        },
    )
    assert query.status_code == 200
    assert query.headers["cache-control"] == "no-store"

    stream = client.post(
        "/api/agent/stream",
        json={
            "query": "Build a software quote.",
            "draft_order_id": draft["draft_order_id"],
            "expected_revision": draft["version"],
        },
    )
    assert stream.status_code == 200
    assert stream.headers["cache-control"] == "no-store"
    active = client.get(f"/api/draft-orders/{draft['draft_order_id']}/agent-plan")
    assert active.headers["cache-control"] == "no-store"


def test_deployed_plan_app_requires_confirmation_secret() -> None:
    with pytest.raises(RuntimeError, match="AGENTIC_CPQ_PLAN_CONFIRMATION_SECRET"):
        main._resolve_plan_confirmation_secret(
            SimpleNamespace(
                plan_confirmation_secret="",
                plans_enabled=True,
                is_databricks_app=True,
            )
        )
    local = main._resolve_plan_confirmation_secret(
        SimpleNamespace(
            plan_confirmation_secret="",
            plans_enabled=True,
            is_databricks_app=False,
        )
    )
    assert isinstance(local, bytes)
    assert len(local) == 32


def test_seller_plan_redaction_covers_top_level_identity_and_economics(plan_api) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    payload = memory_store.get_plan(plan["plan_id"]).model_dump(mode="json")
    payload["goal"] = "Protect a 42% margin. Keep the balanced upfront cost option."
    payload["error_message"] = "Margin fell to 19 percent. Try again."
    payload["created_by"] = "seller@example.com"
    payload["action_proposal"]["summary"] = "Apply the 42% margin option."

    redacted = main.redact_quote_plan_for_view(payload, "seller")
    serialized = str(redacted).casefold()

    assert redacted["goal"] == "Keep the balanced upfront cost option."
    assert redacted["error_message"] == "Try again."
    assert redacted["created_by"] == ""
    assert redacted["scenarios"][0]["summary"] == "Balanced upfront cost"
    assert redacted["action_proposal"]["summary"] == "Confirm the selected quote action."
    assert "42%" not in serialized
    assert "19 percent" not in serialized
    assert "seller@example.com" not in serialized


def test_pdf_render_failure_leaves_draft_and_plan_retryable(
    plan_api,
    monkeypatch,
) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": confirmation["token"],
            "idempotency_key": confirmation["idempotency_key"],
        },
    ).json()
    monkeypatch.setattr(main, "build_quote_pdf", lambda **_kwargs: b"")

    with pytest.raises(RuntimeError, match="returned no content"):
        client.post(f"/api/draft-orders/{draft['draft_order_id']}/quote.pdf")

    live = memory_store.get(draft["draft_order_id"])
    assert live.version == applied["order"]["version"]
    assert live.status != "quote-created"
    assert live.quote_id is None
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.READY_FOR_PDF


def test_expired_pdf_confirmation_recovers_only_an_already_committed_quote(
    plan_api,
    monkeypatch,
) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    monkeypatch.setattr(main, "_complete_plan_for_legacy_pdf", lambda *_args: None)
    committed = client.post(f"/api/draft-orders/{draft['draft_order_id']}/quote.pdf")
    assert committed.status_code == 200
    assert memory_store.get_plan(plan["plan_id"]).status == PlanStatus.READY_FOR_PDF
    reloaded = client.get(f"/api/draft-orders/{draft['draft_order_id']}/agent-plan")
    assert reloaded.status_code == 200
    assert reloaded.json()["status"] == "ready_for_pdf"
    assert reloaded.json()["revision"] == applied["plan"]["revision"]

    actual_verify = main.verify_confirmation_token

    def expired_verify(token: str, *, allow_expired: bool = False, **kwargs):
        if not allow_expired:
            raise ConfirmationTokenError("Confirmation token has expired.")
        return actual_verify(token, allow_expired=True, **kwargs)

    monkeypatch.setattr(main, "verify_confirmation_token", expired_verify)
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]
    recovered = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json={
            "expected_plan_revision": applied["plan"]["revision"],
            "expected_draft_version": applied["order"]["version"],
            "confirmation_token": pdf_confirmation["token"],
            "idempotency_key": pdf_confirmation["idempotency_key"],
        },
    )

    assert recovered.status_code == 200
    assert recovered.json()["plan"]["status"] == "completed"


def test_unused_expired_pdf_confirmation_is_rejected(plan_api, monkeypatch) -> None:
    client, _, memory_store = plan_api
    draft = _create_draft(client)
    plan = _stream_plan(client, draft)
    apply_confirmation = plan["action_proposal"]["confirmation"]
    applied = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-apply",
        json={
            "expected_plan_revision": plan["revision"],
            "expected_draft_version": draft["version"],
            "confirmation_token": apply_confirmation["token"],
            "idempotency_key": apply_confirmation["idempotency_key"],
        },
    ).json()
    actual_verify = main.verify_confirmation_token

    def expired_verify(token: str, *, allow_expired: bool = False, **kwargs):
        if not allow_expired:
            raise ConfirmationTokenError("Confirmation token has expired.")
        return actual_verify(token, allow_expired=True, **kwargs)

    monkeypatch.setattr(main, "verify_confirmation_token", expired_verify)
    pdf_confirmation = applied["plan"]["action_proposal"]["confirmation"]
    response = client.post(
        f"/api/agent/plans/{plan['plan_id']}/confirm-pdf",
        json={
            "expected_plan_revision": applied["plan"]["revision"],
            "expected_draft_version": applied["order"]["version"],
            "confirmation_token": pdf_confirmation["token"],
            "idempotency_key": pdf_confirmation["idempotency_key"],
        },
    )

    assert response.status_code == 400
    assert "expired" in response.json()["detail"].casefold()
    assert memory_store.get(draft["draft_order_id"]).status != "quote-created"
