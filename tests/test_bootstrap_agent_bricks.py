from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from pathlib import Path


def _install_fake_common() -> None:
    fake = types.ModuleType("common")
    fake.call_api = lambda *args, **kwargs: {}
    fake.ensure_volume_directory = lambda *args, **kwargs: None
    fake.find_by_title = lambda items, title: next(
        (item for item in items if item.get("title") == title), None
    )
    fake.get_dbutils = lambda _spark: object()
    fake.get_spark = lambda: object()
    fake.guidance_volume_path = (
        lambda catalog, schema, volume: f"/Volumes/{catalog}/{schema}/{volume}"
    )
    fake.runtime_file_path = lambda _globals=None: (
        Path(__file__).resolve().parents[1] / "src" / "bootstrap" / "bootstrap_agent_bricks.py"
    )
    sys.modules["common"] = fake


class BootstrapAgentBricksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_fake_common()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bootstrap"))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))
        cls.module = importlib.import_module("bootstrap_agent_bricks")

    def test_existing_genie_is_patched_with_guidance_volume(self) -> None:
        calls = []

        def fake_call_api(_spark, method, path, payload=None, query=None):
            calls.append((method, path, payload, query))
            if method == "GET":
                return {"spaces": [{"id": "genie-id", "title": "agentic-cpq-genie-dev"}]}
            return {}

        self.module.call_api = fake_call_api
        serialized = self.module.build_genie_serialized_space("catalog", "schema", "cpq_guidance")
        self.module.ensure_genie_space(
            object(),
            title="agentic-cpq-genie-dev",
            description="Unified seller intelligence",
            warehouse_id="warehouse-id",
            serialized_space=serialized,
        )

        patch = next(call for call in calls if call[0] == "PATCH")
        self.assertEqual(patch[1], "/api/2.0/genie/spaces/genie-id")
        self.assertEqual(
            patch[3],
            {"update_mask": "title,description,warehouse_id,serialized_space"},
        )
        payload = json.loads(patch[2]["serialized_space"])
        self.assertEqual(
            payload["data_sources"]["volumes"],
            [{"path": "/Volumes/catalog/schema/cpq_guidance/"}],
        )
        self.assertEqual({call[0] for call in calls}, {"GET", "PATCH"})

    def test_new_genie_post_includes_guidance_volume(self) -> None:
        calls = []

        def fake_call_api(_spark, method, path, payload=None, query=None):
            calls.append((method, path, payload, query))
            if method == "GET":
                return {"spaces": []}
            return {"id": "new-genie-id", "title": "agentic-cpq-genie-dev"}

        self.module.call_api = fake_call_api
        serialized = self.module.build_genie_serialized_space("catalog", "schema", "cpq_guidance")
        created = self.module.ensure_genie_space(
            object(),
            title="agentic-cpq-genie-dev",
            description="Unified seller intelligence",
            warehouse_id="warehouse-id",
            serialized_space=serialized,
        )

        post = next(call for call in calls if call[0] == "POST")
        self.assertEqual(post[1], "/api/2.0/genie/spaces")
        self.assertEqual(post[2]["parent_path"], "/Workspace/Shared")
        self.assertEqual(created["id"], "new-genie-id")
        self.assertEqual(
            json.loads(post[2]["serialized_space"])["data_sources"]["volumes"],
            [{"path": "/Volumes/catalog/schema/cpq_guidance/"}],
        )

    def test_exactly_five_reviewed_guidance_docx_artifacts(self) -> None:
        from guidance_documents import GUIDANCE_DOCUMENT_NAMES

        documents_dir = Path(__file__).resolve().parents[1] / "src" / "bootstrap" / "genie_guidance_docs"
        actual = sorted(path.name for path in documents_dir.glob("*.docx"))

        self.assertEqual(actual, sorted(GUIDANCE_DOCUMENT_NAMES))
        self.assertEqual(len(actual), 5)

    def test_dbutils_local_file_uri_preserves_workspace_user_at_sign(self) -> None:
        seed_demo_data = importlib.import_module("seed_demo_data")
        path = Path(
            "/Workspace/Users/demo.user@example.com/.bundle/agentic-cpq/dev/files/guide.docx"
        )

        uri = seed_demo_data._dbutils_local_file_uri(path)

        self.assertEqual(
            uri,
            "file:/Workspace/Users/demo.user@example.com/.bundle/agentic-cpq/dev/files/guide.docx",
        )
        self.assertNotIn("%40", uri)


if __name__ == "__main__":
    unittest.main()
