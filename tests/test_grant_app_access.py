from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import types
import unittest
from pathlib import Path


class FakeSpark:
    def __init__(self) -> None:
        self.sql_statements: list[str] = []

    def sql(self, statement: str) -> None:
        self.sql_statements.append(statement)


def _install_fake_common() -> FakeSpark:
    fake_spark = FakeSpark()
    fake = types.ModuleType("common")
    fake.get_spark = lambda: fake_spark
    fake.grant_permission = lambda *args, **kwargs: {}
    fake.guidance_volume_path = (
        lambda catalog, schema, volume: f"/Volumes/{catalog}/{schema}/{volume}"
    )
    fake.runtime_file_path = lambda _globals=None: (
        Path(__file__).resolve().parents[1] / "src" / "bootstrap" / "grant_app_access.py"
    )
    sys.modules["common"] = fake
    return fake_spark


class GrantAppAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fake_spark = _install_fake_common()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bootstrap"))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "shared"))
        cls.module = importlib.import_module("grant_app_access")

    def test_grants_only_genie_tables_and_guidance_volume(self) -> None:
        grants = []
        self.fake_spark.sql_statements.clear()
        self.module.grant_permission = lambda _spark, **kwargs: grants.append(kwargs) or {}
        self.module.parse_args = lambda: argparse.Namespace(
            catalog="catalog",
            schema="schema",
            guidance_volume="cpq_guidance",
            genie_space_id="genie-id",
            app_client_id="app-client-id",
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.module.main()

        self.assertEqual(
            grants,
            [
                {
                    "object_type": "genie",
                    "object_id": "genie-id",
                    "service_principal_name": "app-client-id",
                    "permission_level": "CAN_RUN",
                }
            ],
        )
        self.assertTrue(
            any("`accounts`" in statement for statement in self.fake_spark.sql_statements)
        )
        self.assertTrue(
            any("`source_freshness`" in statement for statement in self.fake_spark.sql_statements)
        )
        self.assertIn(
            "GRANT READ VOLUME ON VOLUME `catalog`.`schema`.`cpq_guidance` TO `app-client-id`",
            self.fake_spark.sql_statements,
        )
        manifest = json.loads(output.getvalue())
        self.assertEqual(manifest["genie_space_id"], "genie-id")
        self.assertEqual(
            manifest["guidance_volume"]["path"],
            "/Volumes/catalog/schema/cpq_guidance/",
        )
        self.assertNotIn("endpoint_grants", manifest)


if __name__ == "__main__":
    unittest.main()
