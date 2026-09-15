"""Offline Context Explorer security and read-only surface tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/ContextExplorer"))
from context_map import validate_repository_relative_path  # noqa: E402


class ContextExplorerSecurityTests(unittest.TestCase):
    def test_frontend_uses_text_content_and_has_no_network_or_write_api(self) -> None:
        app = (ROOT / "Tools/ContextExplorer/frontend/app.js").read_text(encoding="utf-8")
        self.assertIn("textContent", app)
        self.assertNotIn("innerHTML", app)
        self.assertNotIn("fetch(", app)
        self.assertNotIn("XMLHttpRequest", app)
        self.assertNotIn('method: "POST"', app)
        self.assertNotIn('method: "DELETE"', app)

    def test_frontend_is_static_and_offline(self) -> None:
        html = (ROOT / "Tools/ContextExplorer/frontend/index.html").read_text(encoding="utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("__CONTEXT_GRAPH__", html)
        self.assertIn("__HUMAN_ARCHITECTURE__", html)

    def test_repository_path_validation_rejects_traversal_and_urls(self) -> None:
        for value in ("../secret.yaml", "javascript:alert(1)", "https://example.com/context.yaml"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_repository_relative_path(value)


if __name__ == "__main__":
    unittest.main()
