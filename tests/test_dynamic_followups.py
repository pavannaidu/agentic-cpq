from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agents import AgentOutputSchema
from fastapi.testclient import TestClient

from server import main
from server.models import DraftLineItem
from server.openai_agent import (
    AgentPromptSuggestions,
    OpenAIAgentClient,
    build_followup_input,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        agent_model="databricks-gpt-5-6-terra",
        followup_endpoint="databricks-gpt-5-6-luna",
        agent_timeout_seconds=30,
        followups_enabled=True,
    )


def _account() -> dict[str, object]:
    return {
        "account_id": "acct-context",
        "name": "Context Dental Group",
        "segment": "growth",
        "specialty": "pediatric dentistry",
        "growth_stage": "adding chairs",
        "region": "Central",
        "installed_base": [f"SKU-{index}" for index in range(12)],
        "chair_count": 3,
        "num_locations": 2,
        "annual_spend_usd": 125_000,
        "days_since_last_purchase": 18,
    }


def test_prompt_output_is_a_strict_bounded_sdk_schema() -> None:
    schema = AgentOutputSchema(AgentPromptSuggestions)
    suggestions = schema.json_schema()["properties"]["suggestions"]

    assert schema.is_strict_json_schema()
    assert suggestions["minItems"] == 3
    assert suggestions["maxItems"] == 4
    assert suggestions["items"]["maxLength"] == 80


def test_followup_snapshot_is_bounded_authoritative_and_seller_safe(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.openai_agent.account_lookup",
        lambda: {"acct-context": _account()},
    )
    line = DraftLineItem(
        sku="CHAIR-1",
        title="Treatment chair",
        category="equipment",
        quantity=2,
        unit_price=45_000,
        supplier_cost=20_000,
        gross_margin_pct=55.5,
        approval_required=True,
        overpay_amount=999,
    )
    conversation = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"turn {index}"}
        for index in range(10)
    ]
    conversation[-1]["content"] = (
        "Gross margin is 18.7% and supplier cost is $20,000. Approval is required."
    )
    payload = build_followup_input(
        account_id="acct-context",
        draft_order_id="draft-context",
        draft_status="draft",
        draft_version=7,
        current_order_lines=[line],
        conversation_history=conversation,
        last_recommendation={
            "summary": "Quote is ready. Gross margin is 18.7% at wholesale cost.",
            "items": [line.model_dump()],
        },
        approval_threshold=80_000,
    )
    serialized = json.dumps(payload)

    assert payload["active_account"]["name"] == "Context Dental Group"
    assert len(payload["active_account"]["installed_base"]) == 8
    assert payload["active_draft"] == {
        "draft_order_id": "draft-context",
        "status": "draft",
        "version": 7,
    }
    assert payload["current_quote"]["approval_required"] is True
    assert payload["current_quote"]["quote_total_approval_required"] is True
    assert len(payload["recent_conversation"]) == 6
    assert payload["latest_recommendation"]["summary"] == "Quote is ready."
    assert payload["recent_conversation"][-1]["content"] == "Approval is required."
    assert "supplier_cost" not in serialized
    assert "gross_margin_pct" not in serialized
    assert "overpay_amount" not in serialized
    assert "18.7%" not in serialized
    assert "wholesale cost" not in serialized


def test_followup_agent_uses_configured_luna_model_and_typed_output(monkeypatch) -> None:
    captured: dict[str, object] = {}
    model_token = object()
    agent_token = object()

    def fake_model(*, model, openai_client):
        captured["model_name"] = model
        captured["openai_client"] = openai_client
        return model_token

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return agent_token

    monkeypatch.setattr("server.openai_agent.OpenAIChatCompletionsModel", fake_model)
    monkeypatch.setattr("server.openai_agent.Agent", fake_agent)
    client = OpenAIAgentClient(_settings())
    client._agent = object()
    client._openai_client = object()

    result = asyncio.run(client._ensure_followup_agent())

    assert result is agent_token
    assert captured["model_name"] == "databricks-gpt-5-6-luna"
    assert captured["model"] is model_token
    assert captured["output_type"] is AgentPromptSuggestions
    model_settings = captured["model_settings"]
    assert model_settings.max_tokens == 320
    assert model_settings.reasoning.effort == "none"


def test_sdk_prompt_agent_generates_without_a_prior_recommendation(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.openai_agent.account_lookup",
        lambda: {"acct-context": _account()},
    )
    client = OpenAIAgentClient(_settings())
    client._followup_agent = object()
    captured: dict[str, object] = {}

    async def fake_run(agent, **kwargs):
        captured["agent"] = agent
        captured.update(kwargs)
        return SimpleNamespace(
            final_output=AgentPromptSuggestions(
                suggestions=[
                    "Build Context Dental's chair expansion quote",
                    "Compare options for three pediatric operatories",
                    "Review Context Dental's current installed base",
                ]
            )
        )

    monkeypatch.setattr("server.openai_agent.Runner.run", fake_run)
    suggestions = asyncio.run(
        client.suggest_followups(
            account_id="acct-context",
            draft_order_id="draft-empty",
            draft_status="draft",
            draft_version=0,
            current_order_lines=[],
            conversation_history=[],
            last_recommendation=None,
        )
    )

    assert suggestions == [
        "Build Context Dental's chair expansion quote",
        "Compare options for three pediatric operatories",
        "Review Context Dental's current installed base",
    ]
    assert captured["agent"] is client._followup_agent
    assert captured["max_turns"] == 2
    assert captured["run_config"].tracing_disabled is True
    model_input = json.loads(str(captured["input"]))
    assert model_input["active_account"]["growth_stage"] == "adding chairs"
    assert model_input["current_quote"]["product_line_count"] == 0
    assert model_input["latest_recommendation"] == {}


def test_followup_endpoint_uses_current_server_draft_without_recommendation(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAgentClient:
        async def suggest_followups(self, **kwargs):
            captured.update(kwargs)
            return [
                "Review the staged treatment chair",
                "Check this quote's approval status",
                "Prepare a customer-ready summary",
            ]

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    order = main.store.create(
        account_id="acct-riverfront",
        line_items=[
            DraftLineItem(
                sku="EQUIP-CHAIR-500",
                title="Treatment chair",
                category="equipment",
                quantity=1,
                unit_price=19_500,
                approval_required=True,
            )
        ],
    )

    response = TestClient(main.app).post(
        "/api/followups",
        json={
            "draft_order_id": order.draft_order_id,
            "account_id": "acct-riverfront",
            "view_role": "seller",
        },
    )

    assert response.status_code == 200
    assert captured["current_order_lines"][0].sku == "EQUIP-CHAIR-500"
    assert captured["last_recommendation"] == {}


def test_followup_endpoint_role_projects_server_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgentClient:
        async def suggest_followups(self, **kwargs):
            captured.update(kwargs)
            return [
                "Review approval for the staged treatment chair",
                "Add care coverage for the treatment chair",
                "Prepare Riverfront's customer quote PDF",
            ]

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    order = main.store.create(
        account_id="acct-riverfront",
        line_items=[
            DraftLineItem(
                sku="EQUIP-CHAIR-500",
                title="Treatment chair",
                category="equipment",
                quantity=1,
                unit_price=19_500,
                approval_required=True,
            )
        ],
    )
    main.store.append_conversation_turns(
        order.draft_order_id,
        [
            main.ConversationTurn(role="user", content="Focus on the chair refresh."),
            main.ConversationTurn(
                role="assistant",
                content=(
                    "Gross margin is 18.7% with $10,000 supplier cost. "
                    "The chair is staged."
                ),
            ),
        ],
    )
    main.store.set_latest_recommendation(
        order.draft_order_id,
        {
            "summary": "Quote is ready. Wholesale cost supports a 30% margin.",
            "items": [],
        },
    )

    response = TestClient(main.app).post(
        "/api/followups",
        json={
            "draft_order_id": order.draft_order_id,
            "account_id": "acct-riverfront",
            "view_role": "seller",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 3
    assert captured["account_id"] == order.account_id
    assert captured["draft_version"] == order.version
    assert captured["current_order_lines"][0].sku == "EQUIP-CHAIR-500"
    assert captured["last_recommendation"]["summary"] == "Quote is ready."
    assert captured["conversation_history"][-1]["content"] == "The chair is staged."
    projected_text = json.dumps(
        {
            "last_recommendation": captured["last_recommendation"],
            "conversation_history": captured["conversation_history"],
        }
    ).casefold()
    assert "margin" not in projected_text
    assert "supplier cost" not in projected_text


def test_followup_endpoint_has_no_static_fallback_when_generation_fails(
    monkeypatch,
) -> None:
    class FailingAgentClient:
        async def suggest_followups(self, **_kwargs):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(main, "agent_client", FailingAgentClient())
    order = main.store.create(account_id="acct-riverfront")

    response = TestClient(main.app).post(
        "/api/followups",
        json={"draft_order_id": order.draft_order_id},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestions": []}
