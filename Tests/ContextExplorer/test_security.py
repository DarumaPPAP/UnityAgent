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
        html = (ROOT / "Tools/ContextExplorer/frontend/index.html").read_text(encoding="utf-8")
        source = app + "\n" + html
        self.assertIn("textContent", app)
        for token in (
            "innerHTML",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            'method: "POST"',
            'method: "DELETE"',
            "function execute(",
            "function dispatch(",
            "function route(",
            "function approve(",
            "function apply(",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_frontend_is_static_offline_and_uses_context_map_vocabulary(self) -> None:
        html = (ROOT / "Tools/ContextExplorer/frontend/index.html").read_text(encoding="utf-8")
        app = (ROOT / "Tools/ContextExplorer/frontend/app.js").read_text(encoding="utf-8")
        build = (ROOT / "Tools/ContextExplorer/build.py").read_text(encoding="utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("__CONTEXT_MAP__", html)
        self.assertIn("__CONTEXT_MAP__", app)
        self.assertIn("__CONTEXT_MAP__", build)
        self.assertNotIn("__CONTEXT_GRAPH__", html + app + build)
        self.assertNotIn("const graph =", app)
        self.assertIn("__HUMAN_ARCHITECTURE__", html)

    def test_relation_projection_is_explicit_one_hop_and_read_only(self) -> None:
        html = (ROOT / "Tools/ContextExplorer/frontend/index.html").read_text(encoding="utf-8")
        app = (ROOT / "Tools/ContextExplorer/frontend/app.js").read_text(encoding="utf-8")
        self.assertIn("explicitOneHopRelations", app)
        self.assertIn("edge.source === nodeId || edge.target === nodeId", app)
        self.assertIn("metadata.related only", html)
        self.assertIn('data-direction', app.replace("dataset.direction", "data-direction"))

    def test_repository_path_validation_rejects_traversal_and_urls(self) -> None:
        for value in ("../secret.yaml", "javascript:alert(1)", "https://example.com/context.yaml"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_repository_relative_path(value)


if __name__ == "__main__":
    unittest.main()
