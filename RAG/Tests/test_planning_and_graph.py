import unittest

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate
from RAG.Retrieval.graph_expander import GraphExpansionConfig, KnowledgeGraphExpander
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.query_planner import build_query_plan, execute_query_plan
from RAG.Retrieval.retrieval_service import retrieve_knowledge


def item(candidate_id: str, summary: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_id=candidate_id,
        source_kind="fixture",
        source_ref=f"fixture://knowledge/{candidate_id}",
        document_id=f"DOC-{candidate_id}",
        evidence_id=f"EV-{candidate_id}",
        heading="fixture",
        summary=summary,
        content=summary,
        metadata={"domains": ["rendering"]},
        provenance=CandidateProvenance(
            source_kind="fixture",
            source_ref=f"fixture://knowledge/{candidate_id}",
            document_id=f"DOC-{candidate_id}",
            evidence_id=f"EV-{candidate_id}",
        ),
        confidence="verified",
        review_status="reviewed",
    )


class PlanningAndGraphTests(unittest.TestCase):
    def test_query_plan_is_bounded_and_reproducible(self):
        first = build_query_plan("RenderGraph URP 6000.x", max_subqueries=3)
        second = build_query_plan("RenderGraph URP 6000.x", max_subqueries=3)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertLessEqual(len(first.subqueries), 3)
        self.assertTrue(any(query.purpose == "technical_identifier" for query in first.subqueries))

    def test_failed_subquery_is_traced_and_successful_results_are_kept(self):
        plan = build_query_plan("RenderGraph replacement for URP", max_subqueries=3)
        keep = item("keep", "RenderGraph raster pass")

        def retrieve(subquery):
            if subquery.purpose == "intent":
                raise RuntimeError("fixture subquery failure")
            return [keep]

        result = execute_query_plan(plan, retrieve, max_workers=2, candidate_limit=10)
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(any(trace.status == "failed" for trace in result.subquery_traces))
        self.assertTrue(any(diagnostic["code"] == "subquery_failure" for diagnostic in result.diagnostics))

    def test_graph_expansion_is_bounded_and_relation_provenance_is_preserved(self):
        one, two, three = item("one", "seed"), item("two", "support"), item("three", "dependency")
        expander = KnowledgeGraphExpander(
            {
                "one": [{
                    "relation_id": "rel-1",
                    "target_candidate_id": "two",
                    "relation_type": "supports",
                    "provenance_ref": "mrc://relations/rel-1",
                }],
                "two": [{
                    "relation_id": "rel-2",
                    "target_candidate_id": "three",
                    "relation_type": "depends_on",
                    "provenance_ref": "mrc://relations/rel-2",
                }],
                "three": [{
                    "relation_id": "cycle",
                    "target_candidate_id": "one",
                    "relation_type": "related",
                    "provenance_ref": "mrc://relations/cycle",
                }],
            },
            config=GraphExpansionConfig(max_hops=2, max_nodes=3),
        )
        result = expander.expand([one], candidate_lookup={"one": one, "two": two, "three": three})
        self.assertEqual([candidate.candidate_id for candidate in result.candidates], ["one", "two", "three"])
        self.assertEqual(result.expanded_count, 2)
        self.assertEqual(result.candidates[1].provenance.relation_refs, ("mrc://relations/rel-1",))
        self.assertEqual(result.candidates[2].provenance.relation_refs, ("mrc://relations/rel-2",))

    def test_service_reports_graph_expansion_and_keeps_grounding_valid(self):
        one, two = item("one", "RenderGraph raster pass"), item("two", "resource lifetime")
        result = retrieve_knowledge(
            query="RenderGraph",
            route_id="test",
            execution_profile="generic_planning",
            top_k=1,
            candidate_k=2,
            max_chars=256,
            backend=LocalLexicalBackend([one, two]),
            sources=[],
            graph_relations={"one": [{
                "relation_id": "rel-1",
                "target_candidate_id": "two",
                "relation_type": "supports",
                "provenance_ref": "mrc://relations/rel-1",
            }]},
            graph_candidate_lookup={"two": two},
            max_graph_hops=1,
            max_graph_nodes=2,
        )
        self.assertEqual(result["status"], "grounded")
        self.assertEqual(result["graph_expansion"]["expanded_count"], 1)
        self.assertIn("knowledge_graph_expansion", result["trace"]["retrieval_methods"])


if __name__ == "__main__":
    unittest.main()
