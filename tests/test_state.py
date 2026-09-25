from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "app"))

from server import lakebase
from server.models import CPQAdminSettings, ConversationTurn, DraftLineItem
from server.state import DraftConflict, DraftOrderStore


def _line(sku: str = "IMAG-CBCT-210") -> DraftLineItem:
    return DraftLineItem(
        sku=sku,
        title="Product",
        category="imaging",
        unit_price=100,
    )


class DraftOrderStoreTests(unittest.TestCase):
    def test_admin_settings_reads_are_deep_copy_safe(self) -> None:
        store = DraftOrderStore()
        configured = CPQAdminSettings()
        configured.pdf.brand_name = "Northstar"
        store.save_admin_settings(configured, updated_by="manager@example.com")

        first = store.get_admin_settings()
        first.pdf.brand_name = "Mutated"

        self.assertEqual(store.get_admin_settings().pdf.brand_name, "Northstar")

    def test_conversation_memory_is_scoped_to_draft_order(self) -> None:
        store = DraftOrderStore()
        first = store.create("acct-riverfront")
        second = store.create("acct-lakeside")

        store.append_conversation_turns(
            first.draft_order_id,
            [
                ConversationTurn(role="user", content="Build an operatory quote."),
                ConversationTurn(role="assistant", content="3 recommendations ready."),
            ],
        )
        store.set_latest_recommendation(first.draft_order_id, {"summary": "Operatory quote"})

        self.assertEqual(len(store.get_conversation(first.draft_order_id)), 2)
        self.assertEqual(store.get_conversation(second.draft_order_id), [])
        self.assertEqual(store.get_latest_recommendation(first.draft_order_id)["summary"], "Operatory quote")
        self.assertEqual(store.get_latest_recommendation(second.draft_order_id), {})

        store.set_genie_conversation_id(first.draft_order_id, "genie-first")
        self.assertEqual(
            store.get_agent_snapshot(first.draft_order_id)[1],
            "genie-first",
        )
        self.assertIsNone(store.get_agent_snapshot(second.draft_order_id)[1])

    def test_owner_claim_and_version_conflict(self) -> None:
        store = DraftOrderStore()
        order = store.create("acct-riverfront")

        claimed = store.claim_owner(order.draft_order_id, "Seller@Example.com")
        self.assertEqual(claimed.owner_email, "seller@example.com")
        with self.assertRaises(DraftConflict):
            store.claim_owner(order.draft_order_id, "someone-else@example.com")

        updated = store.update_lines(order.draft_order_id, [_line()], expected_version=0)
        self.assertEqual(updated.version, 1)
        with self.assertRaises(DraftConflict):
            store.update_lines(order.draft_order_id, [], expected_version=0)

    def test_recommendations_are_revisioned_and_apply_is_idempotent(self) -> None:
        store = DraftOrderStore()
        order = store.create("acct-riverfront", owner_email="seller@example.com")
        first = store.set_latest_recommendation(
            order.draft_order_id,
            {
                "summary": "First",
                "items": [_line().model_dump()],
                "evidence": [{"status": "success", "answer": "governed"}],
                "apply_mode": "replace",
            },
        )
        second = store.set_latest_recommendation(
            order.draft_order_id,
            {"summary": "Second", "items": [_line().model_dump()]},
        )

        self.assertTrue(first["recommendation_id"].startswith("rec-"))
        self.assertEqual(first["revision"], 1)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(first["draft_version"], 0)
        self.assertEqual(
            store.get_recommendation(order.draft_order_id, first["recommendation_id"])["evidence"][0]["answer"],
            "governed",
        )

        applied = store.apply_recommendation(
            order.draft_order_id,
            first["recommendation_id"],
            first["revision"],
            "replace",
            [_line()],
        )
        current = store.update_lines(
            order.draft_order_id,
            [_line("SENSOR-IO-20")],
            expected_version=1,
        )
        repeated = store.apply_recommendation(
            order.draft_order_id,
            first["recommendation_id"],
            first["revision"],
            "replace",
            [_line()],
        )
        self.assertFalse(applied["already_applied"])
        self.assertTrue(repeated["already_applied"])
        self.assertEqual(applied["order"]["version"], 1)
        self.assertEqual(repeated["order"]["version"], current.version)
        self.assertEqual(repeated["order"]["line_items"][0]["sku"], "SENSOR-IO-20")
        with self.assertRaises(DraftConflict):
            store.apply_recommendation(
                order.draft_order_id,
                first["recommendation_id"],
                first["revision"] + 1,
                "replace",
                [_line()],
            )
        with self.assertRaises(DraftConflict):
            store.apply_recommendation(
                order.draft_order_id,
                first["recommendation_id"],
                first["revision"],
                "add",
                [_line()],
            )

    def test_recommendation_keeps_agent_start_version_after_concurrent_edit(self) -> None:
        store = DraftOrderStore()
        order = store.create("acct-riverfront")
        snapshot, _ = store.get_agent_snapshot(order.draft_order_id, expected_revision=0)
        store.update_lines(order.draft_order_id, [_line("SENSOR-IO-20")], expected_version=0)

        recommendation = store.set_latest_recommendation(
            order.draft_order_id,
            {
                "summary": "Generated from the original draft",
                "items": [_line().model_dump()],
                "apply_mode": "replace",
            },
            draft_version=snapshot.version,
        )

        self.assertEqual(recommendation["draft_version"], 0)
        with self.assertRaises(DraftConflict):
            store.apply_recommendation(
                order.draft_order_id,
                recommendation["recommendation_id"],
                recommendation["revision"],
                "replace",
                [_line()],
            )

    def test_recommendation_apply_rejects_changed_draft(self) -> None:
        store = DraftOrderStore()
        order = store.create("acct-riverfront")
        recommendation = store.set_latest_recommendation(
            order.draft_order_id,
            {"summary": "First", "items": [_line().model_dump()]},
        )
        store.update_lines(order.draft_order_id, [_line("SENSOR-IO-20")])

        with self.assertRaises(DraftConflict):
            store.apply_recommendation(
                order.draft_order_id,
                recommendation["recommendation_id"],
                recommendation["revision"],
                "replace",
                [_line()],
            )

    def test_sent_quote_is_immutable_and_revision_is_editable(self) -> None:
        store = DraftOrderStore()
        original = store.create(
            "acct-riverfront",
            line_items=[_line()],
            owner_email="seller@example.com",
        )
        sent = store.attach_quote(original.draft_order_id, "PPQ-100")

        with self.assertRaises(DraftConflict):
            store.update_lines(sent.draft_order_id, [])
        with self.assertRaises(DraftConflict):
            store.delete_draft(sent.draft_order_id)

        revision = store.create_revision(
            sent.draft_order_id,
            owner_email="seller@example.com",
        )
        self.assertEqual(revision.status, "draft")
        self.assertEqual(revision.revision_number, 2)
        self.assertEqual(revision.parent_draft_order_id, sent.draft_order_id)
        self.assertEqual(revision.source_quote_id, "PPQ-100")
        self.assertIsNone(revision.quote_id)
        self.assertEqual(revision.line_items, sent.line_items)

        edited = store.update_lines(revision.draft_order_id, [], expected_version=0)
        self.assertEqual(edited.line_items, [])
        self.assertEqual(store.get(sent.draft_order_id).line_items, sent.line_items)

    def test_generated_quote_reads_are_deep_copy_safe(self) -> None:
        store = DraftOrderStore()
        payload = {
            "quote_id": "PPQ-100",
            "quote_document": {"equipment_lines": [{"sku": "IMAG-CBCT-210"}]},
        }
        store.save_quote("PPQ-100", "draft-100", "acct-riverfront", payload)

        first = store.get_quote("PPQ-100")
        first["quote_document"]["equipment_lines"][0]["sku"] = "MUTATED"

        self.assertEqual(
            store.get_quote("PPQ-100")["quote_document"]["equipment_lines"][0]["sku"],
            "IMAG-CBCT-210",
        )
        with self.assertRaises(KeyError):
            store.get_quote("missing-quote")

    def test_lakebase_generated_quote_reads_are_deep_copy_safe(self) -> None:
        payload = {
            "quote_id": "PPQ-200",
            "quote_document": {"equipment_lines": [{"sku": "SENSOR-IO-20"}]},
        }
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {"payload": payload}

        with patch.object(lakebase, "_connect", return_value=connection):
            result = lakebase.LakebaseDraftOrderStore().get_quote("PPQ-200")

        result["quote_document"]["equipment_lines"][0]["sku"] = "MUTATED"
        self.assertEqual(
            payload["quote_document"]["equipment_lines"][0]["sku"],
            "SENSOR-IO-20",
        )
        cursor.execute.assert_called_once_with(
            "SELECT payload FROM quotes WHERE quote_id = %s",
            ("PPQ-200",),
        )

        cursor.fetchone.return_value = None
        with patch.object(lakebase, "_connect", return_value=connection):
            with self.assertRaises(KeyError):
                lakebase.LakebaseDraftOrderStore().get_quote("missing-quote")

    def test_lakebase_admin_settings_round_trip_uses_singleton_record(self) -> None:
        payload = CPQAdminSettings().model_dump(mode="json")
        payload["pdf"]["brand_name"] = "Northstar"
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {"payload": payload}

        with patch.object(lakebase, "_connect", return_value=connection):
            loaded = lakebase.LakebaseDraftOrderStore().get_admin_settings()

        self.assertEqual(loaded.pdf.brand_name, "Northstar")
        cursor.execute.assert_called_once_with(
            "SELECT payload FROM admin_settings WHERE settings_key = %s",
            ("global",),
        )

        cursor.reset_mock()
        with patch.object(lakebase, "_connect", return_value=connection):
            saved = lakebase.LakebaseDraftOrderStore().save_admin_settings(
                loaded,
                updated_by="Manager@Example.com",
            )

        self.assertEqual(saved.pdf.brand_name, "Northstar")
        args = cursor.execute.call_args.args[1]
        self.assertEqual(args[0], "global")
        self.assertEqual(args[2], "manager@example.com")

    def test_resumable_draft_skips_empty_scratch_and_sent_quotes(self) -> None:
        store = DraftOrderStore()
        populated = store.create(
            "acct-riverfront",
            line_items=[_line()],
            owner_email="seller@example.com",
        )
        sent = store.create(
            "acct-riverfront",
            line_items=[_line("SENSOR-IO-20")],
            owner_email="seller@example.com",
        )
        store.attach_quote(sent.draft_order_id, "PPQ-200")
        store.create("acct-riverfront", owner_email="seller@example.com")

        resumed = store.find_resumable("acct-riverfront", "SELLER@example.com")

        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.draft_order_id, populated.draft_order_id)


if __name__ == "__main__":
    unittest.main()
