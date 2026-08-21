"""Offline Context Explorer security and read-only surface tests."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/GraphObservatory"))
from context_projection import validate_repository_relative_path  # noqa: E402


class ContextExplorerSecurityTests(unittest.TestCase):
    def test_frontend_uses_text_content_and_has_no_network_or_write_api(self) -> None:
        app = (ROOT / "Tools/GraphObservatory/frontend/app.js").read_text(encoding="utf-8")
        self.assertIn("textContent", app)
        self.assertNotIn("innerHTML", app)
        self.assertNotIn("fetch(", app)
        self.assertNotIn("XMLHttpRequest", app)
        self.assertNotIn("method: \"POST\"", app)
        self.assertNotIn("method: \"DELETE\"", app)

    def test_frontend_is_static_and_offline(self) -> None:
        html = (ROOT / "Tools/GraphObservatory/frontend/index.html").read_text(encoding="utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("__CONTEXT_GRAPH__", html)

    def test_repository_path_validation_rejects_traversal_and_urls(self) -> None:
        with self.assertRaises(ValueError):
            validate_repository_relative_path("../secret.yaml")
        with self.assertRaises(ValueError):
            validate_repository_relative_path("javascript:alert(1)")
