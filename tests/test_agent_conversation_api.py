from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server.databricks_api import ConversationalAgentOutput  # noqa: E402
from server.main import app  # noqa: E402
from server.openai_agent import encode_genie_conversation_reference  # noqa: E402


def test_agent_stream_emits_conversation_event_for_non_json_output(monkeypatch) -> None:
    class FakeAgentClient:
        async def stream(self, **kwargs):
            if False:  # make this an async generator while exercising the exception path
                yield {}
            raise ConversationalAgentOutput(
                answer="Equipment Care uses SUPPORT-CARE-IMG at 12% for CBCT imaging.",
                query=kwargs["query"],
                endpoint_name="databricks-gpt-5-6-terra",
                agent_provider="openai_agents_sdk",
            )

    import server.main as main

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    client = TestClient(app)

    response = client.post(
        "/api/agent/stream",
        json={"query": "how is Equipment Care applied? what is the %?"},
    )

    assert response.status_code == 200
    assert "event: conversation" in response.text
    assert "SUPPORT-CARE-IMG at 12%" in response.text
    assert "event: error" not in response.text


def test_agent_query_does_not_expose_internal_errors(monkeypatch) -> None:
    class FakeAgentClient:
        async def query(self, **kwargs):
            raise ValueError("secret raw model output")

    import server.main as main

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    response = TestClient(app).post("/api/agent/query", json={"query": "Build a quote."})

    assert response.status_code == 502
    assert response.json()["detail"] == "Genie couldn't complete this request. Try again."
    assert "secret raw model output" not in response.text


def test_agent_stream_does_not_expose_internal_errors(monkeypatch) -> None:
    class FakeAgentClient:
        async def stream(self, **kwargs):
            if False:
                yield {}
            raise RuntimeError("secret workspace response")

    import server.main as main

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    response = TestClient(app).post("/api/agent/stream", json={"query": "Build a quote."})

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "Genie couldn't complete this request. Try again." in response.text
    assert "build agent" not in response.text.lower()
    assert "secret workspace response" not in response.text


def test_agent_stream_persists_conversational_answers(monkeypatch) -> None:
    class FakeAgentClient:
        async def stream(self, **kwargs):
            yield {
                "kind": "conversation",
                "payload": {
                    "mode": "agent-conversation",
                    "answer": "quote PDF handles the financing handoff.",
                },
            }

    import server.main as main

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()

    response = client.post(
        "/api/agent/stream",
        json={
            "query": "How does financing work?",
            "draft_order_id": created["draft_order_id"],
        },
    )

    assert response.status_code == 200
    history = main.store.get_conversation(created["draft_order_id"])
    assert [(turn.role, turn.content) for turn in history[-2:]] == [
        ("user", "How does financing work?"),
        ("assistant", "quote PDF handles the financing handoff."),
    ]


def test_agent_request_rejects_a_stale_expected_revision_before_calling_agent(
    monkeypatch,
) -> None:
    class FakeAgentClient:
        called = False

        async def query(self, **_kwargs):
            self.called = True
            raise AssertionError("stale request must not invoke the agent")

    import server.main as main

    fake = FakeAgentClient()
    monkeypatch.setattr(main, "agent_client", fake)
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()
    updated = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    )

    response = client.post(
        "/api/agent/query",
        json={
            "query": "Build a quote.",
            "draft_order_id": created["draft_order_id"],
            "expected_revision": 0,
        },
    )

    assert updated.status_code == 200
    assert response.status_code == 409
    assert fake.called is False


def test_agent_recommendation_keeps_request_start_draft_version(monkeypatch) -> None:
    import server.main as main

    class FakeAgentClient:
        async def query(self, **kwargs):
            main.store.update_lines(
                kwargs["draft_order_id"],
                [],
                expected_version=0,
            )
            line = main.build_catalog_line(
                "SOFT-PRACTICE-12",
                quantity=1,
                account_id=kwargs["account_id"],
            )
            assert line is not None
            line["rationale"] = "Adds practice-management software."
            return {
                "mode": "openai_agents_sdk",
                "apply_mode": "add",
                "summary": "Software recommendation",
                "items": [line],
            }

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()

    response = client.post(
        "/api/agent/query",
        json={
            "query": "Build a software quote.",
            "draft_order_id": created["draft_order_id"],
            "expected_revision": 0,
        },
    )

    assert response.status_code == 200
    recommendation = response.json()
    assert recommendation["draft_version"] == 0
    assert main.store.get(created["draft_order_id"]).version == 1
    apply_response = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json={
            "recommendation_id": recommendation["recommendation_id"],
            "expected_revision": recommendation["revision"],
            "mode": recommendation["apply_mode"],
        },
    )
    assert apply_response.status_code == 409


def test_client_supplied_genie_conversation_id_is_never_reused(monkeypatch) -> None:
    import server.main as main

    seen: list[tuple[str, str | None]] = []

    class FakeAgentClient:
        async def query(self, **kwargs):
            draft_order_id = kwargs["draft_order_id"]
            seen.append((draft_order_id, kwargs["genie_conversation_id"]))
            raise ConversationalAgentOutput(
                answer="Governed answer.",
                query=kwargs["query"],
                endpoint_name="databricks-gpt-5-6-terra",
                details={
                    "genie_conversation_id": f"server-{draft_order_id}",
                    "genie_conversation_source": "genie_agent_mode",
                    "evidence": [
                        {
                            "source": "genie_agent_mode",
                            "conversation_id": f"server-{draft_order_id}",
                        }
                    ],
                },
            )

    monkeypatch.setattr(main, "agent_client", FakeAgentClient())
    client = TestClient(app)
    first = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()
    second = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()
    first_reference = encode_genie_conversation_reference(
        "genie_agent_mode",
        "server-first",
    )
    assert first_reference is not None
    main.store.set_genie_conversation_id(first["draft_order_id"], first_reference)

    second_response = client.post(
        "/api/agent/query",
        json={
            "query": "Explain this quote.",
            "draft_order_id": second["draft_order_id"],
            "expected_revision": 0,
            "genie_conversation_id": "server-first",
        },
    )
    first_response = client.post(
        "/api/agent/query",
        json={
            "query": "Explain this quote.",
            "draft_order_id": first["draft_order_id"],
            "expected_revision": 0,
            "genie_conversation_id": f"server-{second['draft_order_id']}",
        },
    )

    assert second_response.status_code == 200
    assert first_response.status_code == 200
    assert seen == [
        (second["draft_order_id"], None),
        (first["draft_order_id"], first_reference),
    ]
    assert main.store.get_genie_conversation_id(second["draft_order_id"]) == (
        f"genie_agent_mode:server-{second['draft_order_id']}"
    )
