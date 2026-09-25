from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from server import genie
from server.models import EvidenceStatus, GenieEvidenceEnvelope, GenieSqlAttachment


def test_genie_ask_sends_clean_user_question(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeGenie:
        def start_conversation_and_wait(
            self,
            space_id: str,
            prompt: str,
            *,
            timeout: timedelta,
        ):
            captured["space_id"] = space_id
            captured["prompt"] = prompt
            captured["timeout"] = timeout
            return SimpleNamespace(
                conversation_id="conv-1",
                id="msg-1",
                attachments=[
                    SimpleNamespace(
                        text=SimpleNamespace(content="22%"),
                        query=None,
                        attachment_id="att-1",
                    )
                ],
            )

    class FakeWorkspaceClient:
        def __init__(self):
            self.genie = FakeGenie()

    monkeypatch.setattr(genie, "WorkspaceClient", FakeWorkspaceClient)

    settings = SimpleNamespace(genie_enabled=True, genie_space_id="space-1", genie_space_title="unused")
    result = genie.ask_genie(
        settings,
        question="what is margin floor A-dec 500 Operatory Package",
    )

    assert result.status == EvidenceStatus.SUCCESS
    assert result.answer == "22%"
    assert captured["space_id"] == "space-1"
    assert captured["prompt"] == "what is margin floor A-dec 500 Operatory Package"
    assert captured["timeout"] == timedelta(seconds=85)
    assert "Answer directly and concisely" not in captured["prompt"]


def test_genie_retains_all_sql_attachments_and_deduplicates_citations() -> None:
    class FakeGenie:
        def start_conversation_and_wait(self, *_args, **_kwargs):
            citation = {"id": "doc-1", "title": "Pricing guide", "uri": "https://example/doc"}
            return SimpleNamespace(
                conversation_id="conv-1",
                id="msg-1",
                status="COMPLETED",
                attachments=[
                    SimpleNamespace(
                        attachment_id="a1",
                        text=SimpleNamespace(content="Two results.", citations=[citation]),
                        query=SimpleNamespace(query="SELECT sku FROM products", description="Products"),
                        citations=[citation],
                    ),
                    SimpleNamespace(
                        attachment_id="a2",
                        text=None,
                        query=SimpleNamespace(query="SELECT sku FROM addons", description="Add-ons"),
                    ),
                ],
            )

        def get_message_attachment_query_result(self, _space, _conversation, _message, attachment):
            sku = "IMAG-CBCT-210" if attachment == "a1" else "SERV-ONBOARD-01"
            return SimpleNamespace(
                statement_response=SimpleNamespace(
                    manifest=SimpleNamespace(
                        total_row_count=1,
                        schema=SimpleNamespace(columns=[SimpleNamespace(name="sku")]),
                    ),
                    result=SimpleNamespace(data_array=[[sku]]),
                )
            )

    workspace = SimpleNamespace(genie=FakeGenie())
    settings = SimpleNamespace(genie_enabled=True, genie_space_id="space-1", genie_space_title="unused")

    result = genie.ask_genie(settings, question="Show both.", workspace=workspace)

    assert [attachment.attachment_id for attachment in result.sql_attachments] == ["a1", "a2"]
    assert len(result.citations) == 1
    assert genie.sku_values_from_evidence(result) == {"IMAG-CBCT-210", "SERV-ONBOARD-01"}


def test_seller_projection_withholds_sql_sensitive_rows_and_prose() -> None:
    evidence = GenieEvidenceEnvelope(
        status=EvidenceStatus.SUCCESS,
        answer="The SKU is available. Supplier cost is $12,580.",
        sql_attachments=[
            GenieSqlAttachment(
                sql="SELECT sku, supplier_cost FROM pricing",
                description="Internal margin query",
                columns=["sku", "supplier_cost", "recommended_price"],
                rows=[["IMAG-CBCT-210", 12580, 17575]],
            )
        ],
    )

    result = genie.project_evidence(evidence, "seller")

    assert result.answer == "The SKU is available."
    assert result.sql_attachments[0].sql == ""
    assert result.sql_attachments[0].description == ""
    assert result.sql_attachments[0].columns == ["sku", "recommended_price"]
    assert result.sql_attachments[0].rows == [["IMAG-CBCT-210", 17575]]
    assert evidence.sql_attachments[0].sql.startswith("SELECT")


def test_sku_grounding_uses_only_explicit_sku_result_cells() -> None:
    evidence = GenieEvidenceEnvelope(
        status=EvidenceStatus.SUCCESS,
        answer="Consider INVENTED-PROSE-1.",
        sql_attachments=[
            GenieSqlAttachment(
                sql="SELECT 'INVENTED-SQL-1'",
                columns=["description", "product_sku", "sku"],
                rows=[["INVENTED-ROW-1", "INVENTED-ALIAS-1", "IMAG-CBCT-210"]],
            )
        ],
    )

    assert genie.sku_values_from_evidence(evidence) == {"IMAG-CBCT-210"}


def test_genie_errors_are_sanitized() -> None:
    class BrokenGenie:
        def start_conversation_and_wait(self, *_args, **_kwargs):
            raise RuntimeError("secret token and SQL internals")

    settings = SimpleNamespace(genie_enabled=True, genie_space_id="space-1", genie_space_title="unused")
    result = genie.ask_genie(
        settings,
        question="Question",
        workspace=SimpleNamespace(genie=BrokenGenie()),
    )

    assert result.status == EvidenceStatus.ERROR
    assert result.error_code == "GENIE_REQUEST_FAILED"
    assert "secret" not in (result.error_message or "")


def test_agent_mode_retries_once_without_a_stale_conversation_id() -> None:
    calls: list[dict[str, object]] = []

    class StaleConversationError(RuntimeError):
        status_code = 404

    class FakeStream:
        def __aiter__(self):
            async def events():
                yield {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "out-fresh",
                        "content": [
                            {"type": "output_text", "text": "Fresh governed answer."}
                        ],
                    },
                }
                yield {
                    "type": "response.completed",
                    "response": {
                        "conversation_id": "agent-fresh",
                        "status": "completed",
                    },
                }

            return events()

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs.get("extra_body", {}))
            if kwargs.get("extra_body"):
                raise StaleConversationError("stale")
            return FakeStream()

    settings = SimpleNamespace(
        genie_enabled=True,
        genie_space_id="space-1",
        genie_space_title="unused",
    )
    result = asyncio.run(
        genie.ask_genie_agent(
            settings,
            question="Continue the governed request.",
            conversation_id="classic-id-from-another-api",
            workspace=object(),
            client=SimpleNamespace(responses=FakeResponses()),
        )
    )

    assert calls == [
        {"conversation_id": "classic-id-from-another-api"},
        {},
    ]
    assert result.status is EvidenceStatus.SUCCESS
    assert result.conversation_id == "agent-fresh"


def test_conversation_api_restarts_when_its_saved_conversation_is_stale() -> None:
    calls: list[tuple[str, str | None]] = []

    class StaleConversationError(RuntimeError):
        status_code = 404

    class FakeGenie:
        def create_message_and_wait(
            self,
            _space_id: str,
            conversation_id: str,
            _question: str,
            **_kwargs,
        ):
            calls.append(("continue", conversation_id))
            raise StaleConversationError("stale")

        def start_conversation_and_wait(self, _space_id: str, _question: str, **_kwargs):
            calls.append(("start", None))
            return SimpleNamespace(
                conversation_id="classic-fresh",
                id="message-fresh",
                status="COMPLETED",
                attachments=[
                    SimpleNamespace(
                        text=SimpleNamespace(content="Fresh governed answer."),
                        query=None,
                    )
                ],
            )

    settings = SimpleNamespace(
        genie_enabled=True,
        genie_space_id="space-1",
        genie_space_title="unused",
    )
    result = genie.ask_genie(
        settings,
        question="Continue the governed request.",
        conversation_id="classic-stale",
        workspace=SimpleNamespace(genie=FakeGenie()),
    )

    assert calls == [("continue", "classic-stale"), ("start", None)]
    assert result.status is EvidenceStatus.SUCCESS
    assert result.conversation_id == "classic-fresh"


def test_agent_mode_extracts_only_final_messages_sql_rows_and_volume_citations() -> None:
    class FakeStream:
        def __aiter__(self):
            async def events():
                yield {
                    "type": "response.created",
                    "response": {"conversation_id": "conv-agent", "status": "in_progress"},
                }
                yield {
                    "type": "response.output_item.done",
                    "item": {"type": "reasoning", "content": "private chain of thought"},
                }
                yield {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call",
                        "call_id": "call-1",
                        "arguments": '{"title":"Products","sql":"SELECT sku, recommended_price FROM products"}',
                    },
                }
                yield {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "| sku | recommended_price |\n| --- | --- |\n| IMAG-CBCT-210 | 17575 |",
                    },
                }
                yield {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "out-1",
                        "metadata": {"message_id": "msg-agent"},
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    "Protect onboarding first [1](https://dbc.example/explore/data/volumes/"
                                    "catalog/schema/cpq_guidance?filePreviewPath=software-onboarding.docx)"
                                ),
                                "annotations": [],
                            }
                        ],
                    },
                }
                yield {
                    "type": "response.completed",
                    "response": {"conversation_id": "conv-agent", "status": "completed"},
                }

            return events()

    class FakeResponses:
        async def create(self, **_kwargs):
            return FakeStream()

    settings = SimpleNamespace(genie_enabled=True, genie_space_id="space-1", genie_space_title="unused")
    result = asyncio.run(
        genie.ask_genie_agent(
            settings,
            question="What should I prioritize?",
            workspace=object(),
            client=SimpleNamespace(responses=FakeResponses()),
        )
    )

    assert result.status == EvidenceStatus.SUCCESS
    assert result.conversation_id == "conv-agent"
    assert result.message_id == "msg-agent"
    assert "private chain" not in result.answer
    assert result.sql_attachments[0].columns == ["sku", "recommended_price"]
    assert result.sql_attachments[0].rows == [["IMAG-CBCT-210", "17575"]]
    assert result.citations[0].title == "software-onboarding.docx"
