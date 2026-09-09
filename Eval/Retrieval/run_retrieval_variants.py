#!/usr/bin/env python3
"""Compare deterministic lexical, dense, hybrid, and reranked RAG variants."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Contracts.models import RetrievalCandidate
from RAG.Observability.retrieval_metrics import calculate_latency_metrics, calculate_retrieval_metrics
from RAG.Query.extract_filters import extract_filters
from RAG.Ranking.reranker import TechnicalReranker
from RAG.Ranking.rrf import RRFConfig
from RAG.Retrieval.dense_retriever import LocalDenseBackend
from RAG.Retrieval.hybrid_retriever import HybridRetriever
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.retrieval_service import retrieve_knowledge


DEFAULT_DATASET = ROOT / "Eval/Datasets/Retrieval/golden.yaml"
DEFAULT_INDEX = ROOT / "Eval/Datasets/Retrieval/fixtures/search-index.json"
THRESHOLDS = {
    "recall_at_5": 0.80,
    "recall_at_10": 0.90,
    "mrr": 0.70,
    "provenance_completeness": 1.00,
    "no_answer_false_positive_rate": 0.10,
    "exact_token_hit_rate": 0.95,
}
VARIANT_NAMES = (
    "local_lexical",
    "local_lexical_explicit_filters",
    "local_dense",
    "hybrid_rrf",
    "hybrid_weighted_rrf",
    "hybrid_rerank",
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _backend_factory(
    name: str,
    candidates: tuple[RetrievalCandidate, ...],
) -> tuple[Any, dict[str, Any]]:
    """Build one isolated backend so mutable ranking scores do not leak between variants."""

    lexical = lambda: LocalLexicalBackend(deepcopy(candidates))
    dense = lambda: LocalDenseBackend(deepcopy(candidates))
    if name in {"local_lexical", "local_lexical_explicit_filters"}:
        backend = lexical()
        ranking = {"algorithm": "lexical-v1", "candidate_k": 24, "top_k": 5, "top_k_10": 10}
    elif name == "local_dense":
        backend = dense()
        ranking = {"algorithm": "dense-v1", "candidate_k": 24, "top_k": 5, "top_k_10": 10}
    elif name == "hybrid_rrf":
        backend = HybridRetriever(
            lexical(),
            dense(),
            rrf_config=RRFConfig(
                weights={"lexical": 1.0, "semantic": 1.0},
                revision="rrf-eval-equal-v1",
            ),
        )
        ranking = {
            "algorithm": "rrf",
            "rrf": backend.rrf_config.to_dict(),
            "candidate_k": 24,
            "top_k": 5,
            "top_k_10": 10,
        }
    elif name == "hybrid_weighted_rrf":
        backend = HybridRetriever(
            lexical(),
            dense(),
            rrf_config=RRFConfig(
                weights={"lexical": 1.35, "semantic": 1.0},
                revision="rrf-eval-weighted-v1",
            ),
        )
        ranking = {
            "algorithm": "weighted_rrf",
            "rrf": backend.rrf_config.to_dict(),
            "candidate_k": 24,
            "top_k": 5,
            "top_k_10": 10,
        }
    elif name == "hybrid_rerank":
        backend = HybridRetriever(
            lexical(),
            dense(),
            rrf_config=RRFConfig(
                weights={"lexical": 1.35, "semantic": 1.0},
                revision="rrf-eval-weighted-v1",
            ),
            reranker=TechnicalReranker(),
        )
        ranking = {
            "algorithm": "weighted_rrf",
            "rrf": backend.rrf_config.to_dict(),
            "reranker": TechnicalReranker.revision,
            "candidate_k": 24,
            "top_k": 5,
            "top_k_10": 10,
        }
    else:
        raise ValueError(f"unknown retrieval variant: {name}")
    return backend, ranking


def _exact_token_rate(case: dict[str, Any], candidates: list[RetrievalCandidate]) -> float:
    expected = [str(value).casefold() for value in case.get("expected_exact_tokens", []) or []]
    if not expected:
        return 1.0
    text = " ".join(candidate.searchable_text() for candidate in candidates[:1]).casefold()
    return sum(1.0 for token in expected if token in text) / len(expected)


def _failure_kind(variant: str) -> str:
    if variant == "local_dense":
        return "SEMANTIC_MISS"
    if variant == "hybrid_rerank":
        return "RERANKING"
    if variant in {"hybrid_rrf", "hybrid_weighted_rrf"}:
        return "FUSION_RANKING"
    return "LEXICAL_MISS"


def _run_variant(
    name: str,
    dataset: dict[str, Any],
    candidates: tuple[RetrievalCandidate, ...],
    *,
    index_revision: str,
    top_k: int,
) -> dict[str, Any]:
    backend, ranking_config = _backend_factory(name, candidates)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    for case in dataset["cases"]:
        expected = {str(value) for value in case.get("relevant", []) or []}
        explicit_filters = extract_filters(str(case["query"])) if name == "local_lexical_explicit_filters" else None
        result = retrieve_knowledge(
            query=str(case["query"]),
            route_id=f"retrieval-variant-{name}",
            execution_profile=str(case.get("execution_profile", "generic_planning")),
            top_k=top_k,
            candidate_k=max(top_k, 24),
            max_chars=6000,
            backend=backend,
            sources=[],
            filters=explicit_filters,
        )
        retrieved = [str(item["candidate_id"]) for item in result.get("candidates", [])]
        grounding_items = (result.get("grounding_bundle") or {}).get("items", []) or []
        provenance_complete = all(
            bool(((item.get("provenance") or {}).get("document_id")))
            or bool(((item.get("provenance") or {}).get("evidence_id")))
            or bool(((item.get("provenance") or {}).get("source_units")))
            for item in grounding_items
        )
        selected = [candidate_by_id[item] for item in retrieved[:1] if item in candidate_by_id]
        trace = result.get("trace") or {}
        row = {
            "case_id": str(case["id"]),
            "answerable": bool(case.get("answerable", bool(expected))),
            "relevant_ids": sorted(expected),
            "retrieved_ids": retrieved,
            "provenance_complete": provenance_complete,
            "exact_token_hit_rate": (
                1.0 if not retrieved and not bool(case.get("answerable", bool(expected)))
                else _exact_token_rate(case, selected)
            ),
            "status": result.get("status"),
            "latency_ms": float(trace.get("latency_ms") or 0.0),
            "candidate_count": int((trace.get("counts") or {}).get("candidate", 0)),
            "selected_count": len(grounding_items),
        }
        rows.append(row)
        if expected and not (set(retrieved[:5]) & expected):
            failures.append({
                "case_id": row["case_id"],
                "kind": _failure_kind(name),
                "expected": sorted(expected),
                "retrieved": retrieved[:10],
            })
        forbidden = {str(value) for value in case.get("forbidden", []) or []}
        leaked = sorted(forbidden & set(retrieved[:5]))
        if leaked:
            failures.append({"case_id": row["case_id"], "kind": "NO_ANSWER_FALSE_POSITIVE", "candidate_ids": leaked})
        if not row["answerable"] and retrieved:
            failures.append({"case_id": row["case_id"], "kind": "NO_ANSWER_FALSE_POSITIVE", "retrieved": retrieved[:10]})
    metrics = calculate_retrieval_metrics(rows, top_k=5, top_k_10=10)
    metrics.update({
        "Precision@5": metrics["precision_at_5"],
        "Recall@5": metrics["recall_at_5"],
        "Recall@10": metrics["recall_at_10"],
        "MRR": metrics["mrr"],
    })
    threshold_failures = {
        key: {"actual": metrics[key], "minimum": value}
        for key, value in THRESHOLDS.items()
        if (metrics[key] < value if key != "no_answer_false_positive_rate" else metrics[key] > value)
    }
    latency = calculate_latency_metrics(row["latency_ms"] for row in rows)
    latency.update({
        "candidate_count": sum(row["candidate_count"] for row in rows) / len(rows),
        "selected_count": sum(row["selected_count"] for row in rows) / len(rows),
    })
    decision = "PASS" if not failures and not threshold_failures else "FAIL"
    return {
        "variant_id": name,
        "backend": {
            "name": backend.__class__.__name__,
            "revision": str(getattr(backend, "revision", "unknown")),
            "capabilities": sorted(backend.capabilities()),
        },
        "ranking_config": ranking_config,
        "metrics": metrics,
        "performance": latency,
        "thresholds": THRESHOLDS,
        "decision": decision,
        "failure_attribution": {
            "case_failures": failures,
            "threshold_failures": threshold_failures,
            "likely_layer": _failure_kind(name) if failures else None,
        },
        "cases": rows,
        "index_revision": index_revision,
    }


def run(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    index_path: Path = DEFAULT_INDEX,
    top_k: int = 10,
    variants: tuple[str, ...] = VARIANT_NAMES,
) -> dict[str, Any]:
    if not 1 <= int(top_k) <= 20:
        raise ValueError("top_k must be 1..20")
    unknown = sorted(set(variants) - set(VARIANT_NAMES))
    if unknown:
        raise ValueError(f"unknown retrieval variants: {unknown}")
    dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
    loaded = MyResourceCenterAdapter(index_path).load()
    if loaded.diagnostics:
        raise RuntimeError(f"retrieval fixture is unavailable: {loaded.diagnostics}")
    candidates = tuple(loaded.candidates)
    reports = {
        name: _run_variant(
            name,
            dataset,
            candidates,
            index_revision=loaded.source_revision or "unbound",
            top_k=top_k,
        )
        for name in variants
    }
    baseline = reports.get("local_lexical")
    overall = "PASS" if baseline and baseline["decision"] == "PASS" else "FAIL"
    run_id = "rag-variants-" + hashlib.sha256(
        f"{_digest(dataset_path)}:{_digest(index_path)}:{','.join(variants)}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_revision": _digest(dataset_path),
        "index_revision": loaded.source_revision or "unbound",
        "rag_contract_revision": "1.0",
        "overall_decision": overall,
        "variants": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--variant", action="append", dest="variants", choices=VARIANT_NAMES)
    args = parser.parse_args()
    report = run(
        dataset_path=args.dataset,
        index_path=args.index,
        variants=tuple(args.variants or VARIANT_NAMES),
    )
    rendered = yaml.safe_dump(report, sort_keys=False, allow_unicode=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["overall_decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
