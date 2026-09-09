from pathlib import Path
import unittest

from Context.Assembly.materialize_context import materialize_context


ROOT = Path(__file__).resolve().parents[2]


class ContextHandoffTests(unittest.TestCase):
    def test_context_keeps_rag_bundle_and_projection_references(self):
        view = materialize_context(
            "rag-context-test",
            "graphics-mcp",
            root=ROOT,
            rag_projection_refs=["mrc://evidence/DOC-RAG-003/EV-RAG-003"],
            grounding_bundle_ref="rag://grounding/gb-test",
            rag_bundle_revision="sha256:test",
            rag_selected_utf8_bytes=128,
        )
        self.assertEqual(view["selected_refs"]["rag"]["grounding_bundle_ref"], "rag://grounding/gb-test")
        self.assertEqual(view["selected_refs"]["rag"]["projection_refs"], ["mrc://evidence/DOC-RAG-003/EV-RAG-003"])
        self.assertEqual(view["definition_fingerprint"]["rag_contract_revision"], "1.0")
        self.assertEqual(view["definition_fingerprint"]["retrieval_index_revision"], "sha256:test")


if __name__ == "__main__":
    unittest.main()
