from __future__ import annotations

import unittest
from pathlib import Path


class GitignoreTests(unittest.TestCase):
    def test_customer_source_directory_is_ignored(self) -> None:
        root = Path(__file__).resolve().parents[1]
        gitignore = (root / ".gitignore").read_text()

        self.assertIn("data/", gitignore.splitlines())
