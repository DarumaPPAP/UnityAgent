"""Pure retrieval evaluation metrics used by the offline runner."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _ids(results: Iterable[Any]) -> list[str]:
    values: list[str] = []
    for result in results:
        if isinstance(result, str):
            values.append(result)
            continue
        if isinstance(result, Mapping):
            value = result.get("candidate_id") or result.get("chunk_id") or result.get("id")
        else:
            value = getattr(result, "candidate_id", None)
        if value is not None:
            values.append(str(value))
    return values


def calculate_retrieval_metrics(
    cases: Iterable[Mapping[str, Any]],
    *,
    top_k: int = 5,
    top_k_10: int = 10,
) -> dict[str, float]:
    """Calculate Recall/Precision/MRR and provenance/no-answer diagnostics.

    Each case has ``relevant_ids``, ``retrieved_ids`` and ``answerable``. The optional
    ``provenance_complete`` flag describes the returned top-k grounding records.
    """

    rows = list(cases)
    if not rows:
        return {
            "precision_at_5": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "mrr": 0.0,
            "no_answer_false_positive_rate": 0.0,
            "provenance_completeness": 0.0,
            "exact_token_hit_rate": 0.0,
        }
    precision_values: list[float] = []
    recall_values: list[float] = []
    recall10_values: list[float] = []
    reciprocal_values: list[float] = []
    no_answer_false_positives = 0
    no_answer_count = 0
    provenance_values: list[float] = []
    exact_token_values: list[float] = []
    for row in rows:
        expected = {str(value) for value in (row.get("relevant_ids") or [])}
        retrieved = _ids(row.get("retrieved_ids") or row.get("retrieved") or [])
        top = retrieved[:top_k]
        top10 = retrieved[:top_k_10]
        precision_values.append(len(set(top) & expected) / top_k)
        recall_values.append(len(set(top) & expected) / len(expected) if expected else 0.0)
        recall10_values.append(len(set(top10) & expected) / len(expected) if expected else 0.0)
        reciprocal_values.append(
            next((1.0 / index for index, value in enumerate(retrieved, start=1) if value in expected), 0.0)
        )
        if not bool(row.get("answerable", bool(expected))):
            no_answer_count += 1
            if retrieved:
                no_answer_false_positives += 1
        provenance_values.append(1.0 if bool(row.get("provenance_complete", False)) else 0.0)
        exact_token_values.append(float(row.get("exact_token_hit_rate", 0.0) or 0.0))
    return {
        "precision_at_5": sum(precision_values) / len(rows),
        "recall_at_5": sum(recall_values) / len(rows),
        "recall_at_10": sum(recall10_values) / len(rows),
        "mrr": sum(reciprocal_values) / len(rows),
        "no_answer_false_positive_rate": no_answer_false_positives / no_answer_count if no_answer_count else 0.0,
        "provenance_completeness": sum(provenance_values) / len(rows),
        "exact_token_hit_rate": sum(exact_token_values) / len(rows),
    }


def calculate_latency_metrics(values: Iterable[float]) -> dict[str, float]:
    """Return stable nearest-rank latency summaries for offline comparisons."""

    latencies = sorted(max(0.0, float(value)) for value in values)
    if not latencies:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}

    def percentile(percent: float) -> float:
        index = min(len(latencies) - 1, max(0, int(len(latencies) * percent) - 1))
        return latencies[index]

    return {
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "max_ms": latencies[-1],
    }
