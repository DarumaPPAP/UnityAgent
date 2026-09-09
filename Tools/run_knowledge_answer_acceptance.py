from __future__ import annotations

"""Run secret-safe staging acceptance for grounded Knowledge answers."""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Knowledge.answer_generation import (  # noqa: E402
    AnswerRequest,
    DeterministicAnswerModel,
    GroundedAnswer,
    KnowledgeAnswerGenerator,
    OpenAICompatibleAnswerModel,
)
from Context.Retrieval.Knowledge.knowledge_client import KnowledgeClientOptions, KnowledgeHttpClient  # noqa: E402


ANSWER_STATUSES = {"answered", "retrieval_empty", "retrieval_unavailable", "insufficient_evidence", "generation_failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def safe_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("service URL must use HTTP or HTTPS")
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, Mapping) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("answer acceptance file must contain a non-empty cases array")
    normalized: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("answer acceptance case must be an object")
        case_id = str(case.get("id") or "").strip()
        question = str(case.get("question") or "").strip()
        expected_status = str(case.get("expected_status") or "").strip()
        if not case_id or not question or expected_status not in ANSWER_STATUSES:
            raise ValueError("answer acceptance cases require id, question, and a valid expected_status")
        normalized.append(dict(case))
    return normalized


def validate_answer(answer: GroundedAnswer, case: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    expected_status = str(case["expected_status"])
    failures: list[str] = []
    if answer.status != expected_status:
        failures.append(f"unexpected_status:{answer.status}")
    expected_abstained = bool(case.get("expected_abstained", expected_status != "answered"))
    if answer.abstained != expected_abstained:
        failures.append("abstention_mismatch")
    minimum_coverage = max(
        1.0 if expected_status == "answered" else 0.0,
        float(case.get("minimum_citation_coverage", 0.0)),
    )
    if answer.coverage < minimum_coverage:
        failures.append("citation_coverage_below_threshold")
    minimum_citations = max(
        1 if expected_status == "answered" else 0,
        int(case.get("minimum_citations", 0)),
    )
    if len(answer.citations) < minimum_citations:
        failures.append("citation_count_below_threshold")
    if expected_status == "answered" and not answer.index_revision:
        failures.append("index_revision_missing")
    safe_diagnostics = {
        key: answer.diagnostics.get(key)
        for key in ("retrieval_status", "context_characters", "trimmed_results", "retrieval_trace_id", "reason", "error_code")
        if key in answer.diagnostics
    }
    safe = {
        "case_id": str(case["id"]),
        "expected_status": expected_status,
        "status": answer.status,
        "abstained": answer.abstained,
        "coverage": answer.coverage,
        "citation_count": len(answer.citations),
        "index_revision": answer.index_revision,
        "model_version": answer.model_version,
        "diagnostics": safe_diagnostics,
        "passed": not failures,
        "failures": failures,
    }
    return failures, safe


def run_case(case: Mapping[str, Any], *, service_url: str, token: str, timeout_seconds: float, max_retries: int, deterministic: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        model = DeterministicAnswerModel() if deterministic else OpenAICompatibleAnswerModel.from_environment()
        provider_health = model.health()
        client = KnowledgeHttpClient(
            KnowledgeClientOptions(
                service_url,
                bearer_token=token,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        )
        result = KnowledgeAnswerGenerator(client, model).generate(
            AnswerRequest(
                question=str(case["question"]),
                scope=case.get("scope") if isinstance(case.get("scope"), Mapping) else None,
                filters=case.get("filters") if isinstance(case.get("filters"), Mapping) else None,
                top_k=int(case.get("top_k", 8)),
                retrieval_profile=str(case.get("retrieval_profile", "hybrid_v1")),
                max_context_characters=int(case.get("max_context_characters", 12000)),
                answer_style=str(case.get("answer_style", "concise")),
                require_citations=bool(case.get("require_citations", True)),
                correlation_id=f"answer-staging-{os.urandom(8).hex()}",
            )
        )
        _, safe = validate_answer(result, case)
        if isinstance(provider_health, Mapping):
            safe["provider_health"] = {
                key: provider_health.get(key)
                for key in ("ready", "provider", "model_version")
                if key in provider_health
            }
    except Exception as error:  # provider and transport details never enter the report
        safe = {
            "case_id": str(case.get("id") or "unknown"),
            "expected_status": str(case.get("expected_status") or "unknown"),
            "status": "runner_error",
            "abstained": True,
            "coverage": 0.0,
            "citation_count": 0,
            "index_revision": None,
            "model_version": None,
            "provider_health": {},
            "diagnostics": {"error_type": type(error).__name__},
            "passed": False,
            "failures": ["runner_error"],
        }
    safe["latency_ms"] = max(0, int((time.perf_counter() - started) * 1000))
    return safe


def run_cases(cases: list[Mapping[str, Any]], *, request_count: int, concurrency: int, **kwargs: Any) -> list[dict[str, Any]]:
    jobs = [cases[index % len(cases)] for index in range(request_count)]
    if concurrency <= 1:
        return [run_case(case, **kwargs) for case in jobs]
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_case, case, **kwargs) for case in jobs]
        for future in as_completed(futures):
            records.append(future.result())
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [int(record.get("latency_ms", 0)) for record in records]
    failures = [record for record in records if not record.get("passed")]
    by_case: dict[str, dict[str, Any]] = {}
    for record in records:
        case_id = str(record.get("case_id") or "unknown")
        bucket = by_case.setdefault(case_id, {"requests": 0, "passed": 0, "failed": 0, "latencies_ms": []})
        bucket["requests"] += 1
        bucket["passed"] += int(bool(record.get("passed")))
        bucket["failed"] += int(not record.get("passed"))
        bucket["latencies_ms"].append(int(record.get("latency_ms", 0)))
    for bucket in by_case.values():
        values = bucket.pop("latencies_ms")
        bucket.update({"p50_ms": percentile(values, 0.50), "p95_ms": percentile(values, 0.95), "p99_ms": percentile(values, 0.99)})
    return {
        "requests": len(records),
        "passed": len(records) - len(failures),
        "failed": len(failures),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies, default=0),
        },
        "by_case": by_case,
        "failure_samples": [
            {"case_id": record.get("case_id"), "failures": record.get("failures", [])[:10]}
            for record in failures[:20]
        ],
        "sample_results": records[:20],
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run secret-safe staging acceptance for UnityAgent grounded answers")
    parser.add_argument("--service-url", default=os.environ.get("KNOWLEDGE_SERVICE_URL", ""))
    parser.add_argument("--token-env", default="KNOWLEDGE_SERVICE_TOKEN")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--environment", default="staging")
    parser.add_argument("--mode", choices=("smoke", "load", "soak"), default="smoke")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--duration-seconds", type=float, default=0)
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("KNOWLEDGE_CLIENT_TIMEOUT_SECONDS", "10")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("KNOWLEDGE_CLIENT_MAX_RETRIES", "1")))
    parser.add_argument("--p95-slo-ms", type=int, default=0)
    parser.add_argument("--deterministic-model", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.service_url:
        parser.error("--service-url or KNOWLEDGE_SERVICE_URL is required")
    if args.mode == "load" and args.requests < 1:
        parser.error("--requests must be positive in load mode")
    if args.mode == "soak" and (args.duration_seconds <= 0 or args.interval_seconds < 0):
        parser.error("soak mode requires --duration-seconds > 0 and --interval-seconds >= 0")
    if args.concurrency < 1 or args.timeout_seconds <= 0 or not 0 <= args.max_retries <= 3:
        parser.error("concurrency, timeout, and max-retries are invalid")
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        parser.error(f"the bearer token must be supplied through {args.token_env}; it is never accepted as a CLI argument")
    cases = load_cases(args.cases)
    service_url = safe_base_url(args.service_url)
    started_at = utc_now()
    kwargs = {
        "service_url": service_url,
        "token": token,
        "timeout_seconds": args.timeout_seconds,
        "max_retries": args.max_retries,
        "deterministic": args.deterministic_model,
    }
    if args.mode == "smoke":
        records = run_cases(cases, request_count=len(cases), concurrency=1, **kwargs)
    elif args.mode == "load":
        records = run_cases(cases, request_count=args.requests, concurrency=args.concurrency, **kwargs)
    else:
        records = []
        deadline = time.monotonic() + args.duration_seconds
        batch_size = max(len(cases), args.concurrency)
        while time.monotonic() < deadline or not records:
            records.extend(run_cases(cases, request_count=batch_size, concurrency=args.concurrency, **kwargs))
            remaining = deadline - time.monotonic()
            if remaining > 0 and args.interval_seconds > 0:
                time.sleep(min(args.interval_seconds, remaining))
    workload = summarize(records)
    if args.p95_slo_ms > 0 and workload["latency_ms"]["p95"] > args.p95_slo_ms:
        workload["passed"] = False
        workload["failure_samples"].append({"case_id": "__slo__", "failures": [f"p95_above_slo:{args.p95_slo_ms}"]})
    report = {
        "schemaVersion": "1.0.0",
        "tool": "knowledge-answer-staging-acceptance-v1",
        "environment": args.environment,
        "mode": args.mode,
        "service_url": service_url,
        "started_at": started_at,
        "finished_at": utc_now(),
        "model_mode": "deterministic" if args.deterministic_model else "configured_provider",
        "workload": workload,
        "passed": bool(workload["passed"]),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
