#!/usr/bin/env python3
"""Validate the RAG module and its rebuildable retrieval fixture."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FILES = (
    "RAG/Contracts/rag-query.schema.yaml",
    "RAG/Contracts/retrieval-request.schema.yaml",
    "RAG/Contracts/retrieval-candidate.schema.yaml",
    "RAG/Contracts/retrieval-result.schema.yaml",
    "RAG/Contracts/grounding-bundle.schema.yaml",
    "RAG/Contracts/backend-capability.schema.yaml",
    "RAG/Contracts/qdrant-collection.schema.yaml",
    "RAG/Contracts/ranking-config.schema.yaml",
    "RAG/Contracts/query-plan.schema.yaml",
    "RAG/Contracts/graph-expansion.schema.yaml",
    "RAG/Contracts/promotion-proposal.schema.yaml",
    "RAG/Retrieval/retrieval_service.py",
    "RAG/Retrieval/dense_retriever.py",
    "RAG/Retrieval/query_planner.py",
    "RAG/Retrieval/graph_expander.py",
    "RAG/Ranking/rrf.py",
    "RAG/Ranking/reranker.py",
    "RAG/Ranking/ranking-config.yaml",
    "RAG/Adapters/qdrant/adapter.py",
    "RAG/Adapters/qdrant/backend.py",
    "RAG/Adapters/qdrant/collection.py",
    "RAG/Adapters/qdrant/schema.py",
    "RAG/Adapters/qdrant/collection-schema.yaml",
    "RAG/Adapters/qdrant/ingest.py",
    "RAG/Adapters/qdrant/ingestion.py",
    "RAG/Adapters/my_resource_center/adapter.py",
    "RAG/Adapters/memory/adapter.py",
    "RAG/Feedback/experience_feedback.py",
    "RAG/Grounding/grounding_builder.py",
    "RAG/Observability/retrieval_trace.py",
    "RAG/Observability/retrieval_metrics.py",
    "Eval/Datasets/Retrieval/golden.yaml",
    "Eval/Datasets/Retrieval/fixtures/search-index.json",
    "Eval/Datasets/Retrieval/retrieval-eval-report.schema.yaml",
    "Eval/Datasets/Retrieval/retrieval-variants-report.schema.yaml",
    "Eval/Datasets/Retrieval/fixtures/knowledge-relations.yaml",
    "Eval/Retrieval/failure-taxonomy.yaml",
    "Eval/Retrieval/Baselines/local-lexical-v1.yaml",
    "Eval/Retrieval/run_retrieval_variants.py",
    "Persistence/Memory/promotion_writer.py",
)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing required RAG file: {relative}")
    contract_ids: set[str] = set()
    for path in sorted((root / "RAG/Contracts").glob("*.schema.yaml")):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - validator reports the exact file.
            errors.append(f"invalid YAML: {path.relative_to(root)}: {exc}")
            continue
        if not isinstance(value, dict) or value.get("schema_version", "1.0") not in {None, "1.0"}:
            # Schemas use const rather than a schema-level schema_version; retain a
            # clear check for accidental contract-version drift when present.
            errors.append(f"RAG schema has invalid schema_version: {path.relative_to(root)}")
        schema_id = value.get("$id")
        if not schema_id:
            errors.append(f"RAG schema missing $id: {path.relative_to(root)}")
        elif schema_id in contract_ids:
            errors.append(f"duplicate RAG schema $id: {schema_id}")
        else:
            contract_ids.add(str(schema_id))
    dataset_path = root / "Eval/Datasets/Retrieval/golden.yaml"
    index_path = root / "Eval/Datasets/Retrieval/fixtures/search-index.json"
    try:
        dataset: dict[str, Any] = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
        index: dict[str, Any] = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return errors + [f"retrieval fixture cannot be loaded: {exc}"]
    cases = dataset.get("cases") if isinstance(dataset, dict) else None
    chunks = index.get("chunks") if isinstance(index, dict) else None
    if not isinstance(cases, list) or len(cases) < 20:
        errors.append("retrieval Golden dataset must contain at least 20 cases")
    if not any(isinstance(case, dict) and case.get("answerable") is False for case in (cases or [])):
        errors.append("retrieval Golden dataset must contain a no-answer case")
    chunk_ids = {str(chunk.get("chunkId")) for chunk in (chunks or []) if isinstance(chunk, dict)}
    for case in cases or []:
        if not isinstance(case, dict):
            errors.append("retrieval Golden case must be a mapping")
            continue
        for candidate_id in case.get("relevant", []) or []:
            if str(candidate_id) not in chunk_ids:
                errors.append(f"Golden case {case.get('id')} references missing candidate: {candidate_id}")
    if not isinstance(index, dict) or index.get("schemaVersion") != "2.0.0" or index.get("kind") != "rebuildable-evidence-search-index":
        errors.append("retrieval fixture must use MyResourceCenter Search Index schema 2.0.0")
    for index_number, chunk in enumerate(chunks or []):
        if not isinstance(chunk, dict):
            errors.append(f"fixture chunk {index_number} must be a mapping")
            continue
        for field in ("chunkId", "documentId", "workspacePath", "heading", "summary", "sourceUnits", "evidence"):
            if not chunk.get(field):
                errors.append(f"fixture chunk {index_number} missing {field}")
        if not chunk.get("evidence"):
            errors.append(f"fixture chunk {index_number} requires evidence provenance")
    try:
        importlib.import_module("RAG.Retrieval.retrieval_service")
        importlib.import_module("RAG.Grounding.grounding_builder")
        importlib.import_module("RAG.Adapters.qdrant")
        importlib.import_module("RAG.Feedback.experience_feedback")
        importlib.import_module("Persistence.Memory.promotion_writer")
        importlib.import_module("Eval.Retrieval.run_retrieval_variants")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"RAG import smoke failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    errors = validate(Path(args.root).resolve())
    if errors:
        print("RAG validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RAG validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
