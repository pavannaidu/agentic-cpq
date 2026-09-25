from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path


def _install_fake_common() -> None:
    fake = types.ModuleType("common")
    fake.call_api = lambda *args, **kwargs: {}
    fake.get_dbutils = lambda _spark: object()
    fake.get_spark = lambda: object()
    fake.guidance_volume_path = (
        lambda catalog, schema, volume: f"/Volumes/{catalog}/{schema}/{volume}"
    )
    fake.runtime_file_path = lambda _globals=None: (
        Path(__file__).resolve().parents[1] / "src" / "bootstrap" / "smoke_test_stack.py"
    )
    sys.modules["common"] = fake


class SmokeStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_fake_common()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bootstrap"))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))
        cls.module = importlib.import_module("smoke_test_stack")

    def test_non_actionable_guidance_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-actionable guidance"):
            self.module._assert_useful_guidance(
                "I don't have any search results available to provide documented guidance.",
                prompt="How should I position Equipment Care?",
            )

    def test_genie_permission_accepts_can_run(self) -> None:
        def fake_call_api(_spark, method, path, payload=None, query=None):
            self.assertEqual((method, path), ("GET", "/api/2.0/permissions/genie/genie-id"))
            return {
                "access_control_list": [
                    {
                        "service_principal_name": "app-client-id",
                        "all_permissions": [{"permission_level": "CAN_RUN"}],
                    }
                ]
            }

        self.module.call_api = fake_call_api
        self.assertTrue(
            self.module._assert_genie_permission(
                object(),
                space_id="genie-id",
                app_client_id="app-client-id",
            )
        )

    def test_guidance_volume_permission_accepts_read_volume(self) -> None:
        row = types.SimpleNamespace(
            asDict=lambda recursive=True: {
                "Principal": "app-client-id",
                "ActionType": "READ_VOLUME",
            }
        )
        result = types.SimpleNamespace(collect=lambda: [row])
        spark = types.SimpleNamespace(sql=lambda _statement: result)

        self.assertTrue(
            self.module._assert_guidance_volume_permission(
                spark,
                catalog="catalog",
                schema="schema",
                guidance_volume="cpq_guidance",
                app_client_id="app-client-id",
            )
        )

    def test_guidance_volume_contains_exact_reviewed_documents(self) -> None:
        entries = [
            types.SimpleNamespace(name=name)
            for name in self.module.GUIDANCE_DOCUMENT_NAMES
        ]
        dbutils = types.SimpleNamespace(fs=types.SimpleNamespace(ls=lambda _path: entries))
        self.module.get_dbutils = lambda _spark: dbutils

        self.assertEqual(
            self.module._assert_guidance_documents(
                object(),
                catalog="catalog",
                schema="schema",
                guidance_volume="cpq_guidance",
            ),
            sorted(self.module.GUIDANCE_DOCUMENT_NAMES),
        )

    def test_genie_conversation_smoke_accepts_query_attachment(self) -> None:
        query = types.SimpleNamespace(query="SELECT sku FROM products LIMIT 1")
        attachment = types.SimpleNamespace(text=None, query=query)
        message = types.SimpleNamespace(
            conversation_id="conversation-id",
            id="message-id",
            attachments=[attachment],
        )
        workspace = types.SimpleNamespace(
            genie=types.SimpleNamespace(
                start_conversation_and_wait=lambda space_id, prompt: message
            )
        )

        result = self.module._assert_genie_answers(
            workspace,
            space_id="genie-id",
            prompt="Name one quote product.",
        )

        self.assertEqual(result["conversation_id"], "conversation-id")
        self.assertEqual(result["message_id"], "message-id")

    def test_genie_agent_mode_requires_reviewed_volume_citation(self) -> None:
        answer = (
            "Keep the conversation focused on budget and hand off terms to quote PDF "
            "[1](https://dbc.example/explore/data/volumes/catalog/schema/cpq_guidance"
            "?filePreviewPath=financing-and-approval-guide.docx)"
        )
        message = types.SimpleNamespace(
            type="message",
            content=[types.SimpleNamespace(type="output_text", text=answer)],
        )
        response = types.SimpleNamespace(
            conversation_id="agent-conversation-id",
            status="completed",
            output=[message],
        )
        event = types.SimpleNamespace(type="response.completed", response=response)
        responses = types.SimpleNamespace(create=lambda **_kwargs: iter([event]))
        client = types.SimpleNamespace(responses=responses)

        result = self.module._assert_genie_agent_guidance(
            object(),
            space_id="genie-id",
            prompt="How should financing be positioned?",
            client=client,
        )

        self.assertEqual(result["conversation_id"], "agent-conversation-id")
        self.assertEqual(
            result["cited_documents"],
            ["financing-and-approval-guide.docx"],
        )


if __name__ == "__main__":
    unittest.main()
