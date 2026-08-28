#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

def _load_materializer():
    path = ROOT / "Context/Assembly/materialize_context.py"
    spec = importlib.util.spec_from_file_location("phase2_materializer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load context materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build(run_id: str, route_id: str, attempt: int = 1, prompt_spec_ref: str | None = None) -> dict:
    materializer = _load_materializer()
    view = materializer.materialize_context(run_id, route_id, prompt_spec_ref, root=ROOT)
    return {
        "schema_version": "1.0",
        "manifest_id": f"{view['context_id']}-a{attempt}",
        "run_id": run_id,
        "attempt": attempt,
        "previous_manifest_ref": None,
        "materialized_context": view,
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = build(args.run_id, args.route, args.attempt, args.prompt_spec_ref)
    text = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
