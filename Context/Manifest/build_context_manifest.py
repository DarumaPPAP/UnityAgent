#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_materializer():
    path = ROOT / "Context/Assembly/materialize_context.py"
    spec = importlib.util.spec_from_file_location("context_materializer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load context materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_project_facts(project_facts: list[dict[str, Any]], attempt: int) -> None:
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    for index, fact in enumerate(project_facts):
        if not isinstance(fact, dict):
            raise ValueError(f"project_facts[{index}] must be a mapping")
        observed = int(fact.get("observed_at_attempt", 0) or 0)
        freshness = fact.get("freshness") or {}
        if not isinstance(freshness, dict):
            raise ValueError(f"project_facts[{index}].freshness must be a mapping")
        checked = int(freshness.get("checked_at_attempt", 0) or 0)
        status = str(freshness.get("status", ""))
        if observed < 1 or observed > attempt:
            raise ValueError(f"project_facts[{index}] observed_at_attempt must be within current manifest history")
        if checked < observed or checked > attempt:
            raise ValueError(f"project_facts[{index}] checked_at_attempt must be between observation and current attempt")
        if status == "current" and checked != attempt:
            raise ValueError(f"project_facts[{index}] current fact must be reobserved or revalidated at current attempt")
        if status not in {"current", "stale", "unknown"}:
            raise ValueError(f"project_facts[{index}] has invalid freshness status: {status}")


def build(
    run_id: str,
    route_id: str,
    attempt: int = 1,
    prompt_spec_ref: str | None = None,
    *,
    project_facts: list[dict[str, Any]] | None = None,
    previous_manifest_ref: str | None = None,
) -> dict:
    facts = list(project_facts or [])
    validate_project_facts(facts, attempt)
    if attempt > 1 and not previous_manifest_ref:
        raise ValueError("retry Context Manifest requires previous_manifest_ref")
    if attempt == 1 and previous_manifest_ref is not None:
        raise ValueError("attempt 1 must not declare previous_manifest_ref")
    materializer = _load_materializer()
    view = materializer.materialize_context(run_id, route_id, prompt_spec_ref, root=ROOT)
    return {
        "schema_version": "1.0",
        "manifest_id": f"{view['context_id']}-a{attempt}",
        "run_id": run_id,
        "attempt": attempt,
        "previous_manifest_ref": previous_manifest_ref,
        "materialized_context": view,
        "project_facts": facts,
        "budget_report": view["budget_report"],
        "unresolved_bindings": list(view["unresolved_bindings"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--prompt-spec-ref")
    parser.add_argument("--previous-manifest-ref")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = build(
        args.run_id,
        args.route,
        args.attempt,
        args.prompt_spec_ref,
        previous_manifest_ref=args.previous_manifest_ref,
    )
    text = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
