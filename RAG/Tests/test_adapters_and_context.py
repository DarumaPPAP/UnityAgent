import copy
from pathlib import Path
import tempfile
import unittest

from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Retrieval.retrieval_service import retrieve_knowledge


ROOT = Path(__file__).resolve().parents[2]


class AdapterAndContextTests(unittest.TestCase):
    def test_mrc_index_is_read_only_candidate_source(self):
        index = ROOT / "Eval/Datasets/Retrieval/fixtures/search-index.json"
        before = index.read_bytes()
        result = MyResourceCenterAdapter(index).load()
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(len(result.candidates), 19)
        self.assertTrue(result.candidates[0].provenance.evidence_id)

    def test_retrieval_result_contains_grounding_and_context_projection(self):
        index = ROOT / "Eval/Datasets/Retrieval/fixtures/search-index.json"
        result = retrieve_knowledge(
            query="RenderGraph Blit replacement",
            route_id="graphics-mcp",
            execution_profile="generic_planning",
            sources=["my_resource_center"],
            my_resource_center_index=index,
        )
        self.assertEqual(result["status"], "grounded")
        self.assertTrue(result["grounding_bundle"]["grounding_bundle_ref"].startswith("rag://grounding/"))
        self.assertEqual(result["context_projection"]["selected_count"], 2)

    def test_missing_external_index_is_explicit(self):
        result = retrieve_knowledge(
            query="RenderGraph",
            route_id="graphics-mcp",
            execution_profile="generic_planning",
            sources=["my_resource_center"],
            my_resource_center_index=Path(tempfile.gettempdir()) / "unityagent-rag-index-does-not-exist.json",
        )
        self.assertIn(result["status"], {"blocked", "partial", "no_answer"})
        self.assertTrue(any(item.get("code") == "source_unavailable" for item in result["diagnostics"]))


if __name__ == "__main__":
    unittest.main()
