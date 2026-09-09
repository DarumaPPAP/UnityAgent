#!/usr/bin/env python3
"""Run the deterministic RAG Golden Retrieval evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Observability.retrieval_metrics import calculate_retrieval_metrics
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.retrieval_service import retrieve_knowledge


DEFAULT_DATASET = ROOT / "Eval/Datasets/Retrieval/golden.yaml"
DEFAULT_INDEX = ROOT / "Eval/Datasets/Retrieval/fixtures/search-index.json"
DEFAULT_BASELINE = ROOT / "Eval/Retrieval/Baselines/local-lexical-v1.yaml"
THRESHOLDS = {
    "recall_at_5": 0.80,
    "recall_at_10": 0.90,
    "mrr": 0.70,
    "provenance_completeness": 1.00,
    "no_answer_false_positive_rate": 0.10,
    "exact_token_hit_rate": 0.95,
}


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise ValueError(f"invalid retrieval dataset: {path}")
    return value


def _exact_token_rate(case: dict[str, Any], candidates: list[Any]) -> float:
    expected = [str(value).casefold() for value in case.get("expected_exact_tokens", []) or []]
    if not expected:
        return 1.0
    text = " ".join(candidate.searchable_text() for candidate in candidates[:1]).casefold()
    return sum(1.0 for token in expected if token in text) / len(expected)


def run(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    index_path: Path = DEFAULT_INDEX,
    top_k: int = 10,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    adapter_result = MyResourceCenterAdapter(index_path).load()
    if adapter_result.diagnostics:
        raise RuntimeError(f"retrieval fixture is unavailable: {adapter_result.diagnostics}")
    backend = LocalLexicalBackend(adapter_result.candidates)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        if not isinstance(case, dict):
            raise ValueError("retrieval dataset cases must be mappings")
        expected = {str(value) for value in case.get("relevant", []) or []}
        result = retrieve_knowledge(
            query=str(case["query"]),
            route_id=str(case.get("route_id", "retrieval-eval")),
            execution_profile=str(case.get("execution_profile", "generic_planning")),
            top_k=top_k,
            candidate_k=max(top_k, 24),
            max_chars=6000,
            backend=backend,
            sources=["my_resource_center"],
            my_resource_center_index=index_path,
            filters=case.get("filters"),
        )
        retrieved = [str(item["candidate_id"]) for item in result.get("candidates", [])]
        grounding_items = (result.get("grounding_bundle") or {}).get("items", []) or []
        provenance_complete = all(
            bool(((item.get("provenance") or {}).get("document_id")))
            or bool(((item.get("provenance") or {}).get("evidence_id")))
            or bool(((item.get("provenance") or {}).get("source_units")))
            for item in grounding_items
        )
        selected_candidates = [
            candidate for candidate in adapter_result.candidates if candidate.candidate_id in set(retrieved[:1])
        ]
        row = {
            "case_id": str(case["id"]),
            "answerable": bool(case.get("answerable", bool(expected))),
            "relevant_ids": sorted(expected),
            "retrieved_ids": retrieved,
            "provenance_complete": provenance_complete,
            "exact_token_hit_rate": (
                1.0 if not retrieved and not bool(case.get("answerable", bool(expected)))
                else _exact_token_rate(case, selected_candidates)
            ),
            "status": result.get("status"),
            "latency_ms": float((result.get("trace") or {}).get("latency_ms") or 0.0),
            "candidate_count": int(((result.get("trace") or {}).get("counts") or {}).get("candidate", 0)),
            "selected_count": len(grounding_items),
        }
        rows.append(row)
        top5 = set(retrieved[:5])
        if expected and not (top5 & expected):
            failures.append({"case_id": row["case_id"], "kind": "relevant_missed", "expected": sorted(expected), "retrieved": retrieved[:10]})
        forbidden = {str(value) for value in case.get("forbidden", []) or []}
        leaked = sorted(forbidden & set(retrieved[:5]))
        if leaked:
            failures.append({"case_id": row["case_id"], "kind": "forbidden_returned", "candidate_ids": leaked})
        if not row["answerable"] and retrieved:
            failures.append({"case_id": row["case_id"], "kind": "no_answer_false_positive", "retrieved": retrieved[:10]})
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
    regression_failures: list[dict[str, Any]] = []
    if baseline_path is not None:
        baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8")) or {}
        baseline_metrics = baseline.get("metrics") or {}
        for key in ("precision_at_5", "recall_at_5", "recall_at_10", "mrr"):
            if key in baseline_metrics and metrics[key] + 1e-9 < float(baseline_metrics[key]):
                regression_failures.append({
                    "metric": key,
                    "actual": metrics[key],
                    "baseline": float(baseline_metrics[key]),
                })
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    if latencies:
        p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))
        performance = {
            "p50_ms": latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.50) - 1))],
            "p95_ms": latencies[p95_index],
            "max_ms": latencies[-1],
            "candidate_count": sum(int(row["candidate_count"]) for row in rows) / len(rows),
            "selected_count": sum(int(row["selected_count"]) for row in rows) / len(rows),
        }
    else:
        performance = {"p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0, "candidate_count": 0.0, "selected_count": 0.0}
    decision = "PASS" if not threshold_failures and not failures and not regression_failures else "FAIL"
    run_id = "rag-eval-" + hashlib.sha256(
        f"{_digest(dataset_path)}:{_digest(index_path)}:local-lexical-v1".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_revision": _digest(dataset_path),
        "rag_contract_revision": "1.0",
        "index_revision": adapter_result.source_revision,
        "backend": {"name": "local_lexical", "revision": "local-lexical-v1", "capabilities": sorted(backend.capabilities())},
        "ranking_config": {"algorithm": "lexical-v1", "candidate_k": 24, "top_k": 5, "top_k_10": 10},
        "metrics": metrics,
        "performance": performance,
        "thresholds": THRESHOLDS,
        "decision": decision,
        "failure_attribution": {
            "case_failures": failures,
            "threshold_failures": threshold_failures,
            "regression_failures": regression_failures,
            "likely_layer": "ranking_or_fixture" if failures else ("regression" if regression_failures else None),
        },
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    report = run(dataset_path=args.dataset, index_path=args.index, baseline_path=args.baseline)
    text = yaml.safe_dump(report, sort_keys=False, allow_unicode=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
