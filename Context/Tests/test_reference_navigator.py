from __future__ import annotations

import unittest

from Context.Retrieval.Reference.reference_navigator import (
    build_investigation_plan,
    search_snapshot,
)


def snapshot_fixture() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "myresourcecenter-reference-snapshot",
        "snapshot_revision": "ref-test-0001",
        "source_policy": {"raw_document_body_included": False},
        "resources": [
            {
                "resource_id": "RES-TAA",
                "title": "Temporal AAのちらつき対策",
                "source_uri": "https://example.test/taa",
                "drive_file_id": None,
                "summary": "時間方向の再投影と履歴管理で細い形状のちらつきを抑える。",
                "topics": ["TAA", "Reprojection"],
                "tags": ["Shader", "MotionVector"],
                "key_facts": ["履歴リセット条件を定義する。"],
                "collection_ids": ["COL-TEMPORAL"],
                "relation_refs": [{"resource_id": "RES-MOTION", "relation": "related", "direction": "outgoing"}],
                "review_state": "Reviewed",
                "use_state": "Reference",
                "confidence": "High",
                "freshness": "Current",
                "eligibility": {"default": True, "investigation": True},
            },
            {
                "resource_id": "RES-MOTION",
                "title": "Motion Vectorの欠落確認",
                "source_uri": "https://example.test/motion",
                "drive_file_id": None,
                "summary": "カメラとオブジェクトのMotion Vectorを分離して確認する。",
                "topics": ["MotionVector"],
                "tags": ["Rendering"],
                "key_facts": [],
                "collection_ids": [],
                "relation_refs": [],
                "review_state": "Reviewed",
                "use_state": "Reference",
                "confidence": "Medium",
                "freshness": "Current",
                "eligibility": {"default": True, "investigation": True},
            },
            {
                "resource_id": "RES-TRY",
                "title": "実験的な透明表現",
                "source_uri": "https://example.test/transparent",
                "drive_file_id": None,
                "summary": "透明描画の実験候補。",
                "topics": ["Transparency"],
                "tags": ["Rendering"],
                "key_facts": [],
                "collection_ids": [],
                "relation_refs": [],
                "review_state": "Triaged",
                "use_state": "ToTry",
                "confidence": "Unverified",
                "freshness": "Unknown",
                "eligibility": {"default": False, "investigation": True},
            },
        ],
        "collections": [
            {
                "collection_id": "COL-TEMPORAL",
                "title": "Temporal Rendering",
                "description": "TAAと再投影の読み物。",
                "topics": ["TAA"],
                "resources": [{"resource_id": "RES-TAA", "role": "foundation"}],
            }
        ],
        "relations": [{"from": "RES-TAA", "to": "RES-MOTION", "relation": "related"}],
        "evidence_documents": [
            {
                "document_id": "DOC-TAA",
                "resource_id": "RES-TAA",
                "title": "TAAのSource Evidence",
                "summary": "細い形状のちらつきと履歴リセット条件のEvidence。",
                "topics": ["TAA"],
                "source": {"source_uri": "https://example.test/evidence", "source_units": [12]},
                "facts": [{"evidence_id": "E1", "kind": "limitation", "fact": "履歴が不適切だと残像が発生する。", "source_units": [12]}],
                "reference_status": "DONE_SOURCE_FAITHFUL",
                "untrusted_reference": True,
            }
        ],
    }


class ReferenceNavigatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = snapshot_fixture()

    def test_japanese_and_tag_query_returns_local_candidates(self):
        result = search_snapshot(self.snapshot, "画面のちらつき TAA", max_items=3)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["snapshot_revision"], "ref-test-0001")
        self.assertIn("DOC-TAA", [candidate["candidate_id"] for candidate in result["candidates"]])
        self.assertFalse(result["raw_document_body_included"])
        self.assertIn("Source: https://example.test/evidence", result["context"])

    def test_one_hop_relation_is_added_only_as_secondary_candidate(self):
        result = search_snapshot(self.snapshot, "ちらつき", max_items=3, include_relations=True)
        ids = [candidate["candidate_id"] for candidate in result["candidates"]]
        self.assertIn("RES-TAA", ids)
        self.assertIn("RES-MOTION", ids)
        related = next(candidate for candidate in result["candidates"] if candidate["candidate_id"] == "RES-MOTION")
        self.assertEqual(related["selection_reason"], "related_one_hop")

    def test_investigation_plan_orders_by_relevance_and_explicitly_avoids_mutation(self):
        plan = build_investigation_plan(self.snapshot, "TAAのちらつき", environment="Unity URP")
        self.assertEqual(plan["operating_mode"], "local_project_observation_first")
        self.assertTrue(plan["hypotheses"])
        for hypothesis in plan["hypotheses"]:
            self.assertFalse(hypothesis["mutation_allowed"])
            self.assertEqual([check["mutation"] for check in hypothesis["checks"]], ["none"] * 4)
        self.assertIn("原因確率", plan["ordering_note"])

    def test_no_match_requests_recheck_instead_of_fabricating_context(self):
        result = search_snapshot(self.snapshot, "存在しない未知の症状", max_items=3)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["next_action"], "recheck_myresourcecenter")
        self.assertEqual(result["context"], "")


if __name__ == "__main__":
    unittest.main()
