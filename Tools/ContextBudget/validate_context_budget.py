#!/usr/bin/env python3
"""Validate Context Budget, Retrieval Budget, and Compression contracts."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools" / "ContextManifest"))
sys.path.insert(0, str(ROOT / "Tools" / "ContextBudget"))

from context_budget_runtime import (  # noqa: E402
    BudgetError,
    build_budget_report,
    load_yaml,
    validate_budget_report,
)
from context_manifest_runtime import build_manifest  # noqa: E402

REQUEST = ROOT / "Tests" / "ContextManifest" / "requests" / "csharp-local-fix.yaml"
CONTRACT = ROOT / ".ai" / "context-budget.yaml"


def expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def project_observations(manifest: dict, bytes_per_source: int = 8000) -> list[dict]:
    observations: list[dict] = []
    for item in manifest.get("context", {}).get("source_files", []) or []:
        path = str(item.get("source_path", ""))
        reason = str(item.get("reason", ""))
        role = "target_source" if reason == "mutation_target" else "direct_dependency"
        observations.append(
            {
                "source_id": f"project:{path}",
                "role": role,
                "source_revision": f"fixture:{path}",
                "original_utf8_bytes": bytes_per_source,
                "selected_utf8_bytes": bytes_per_source,
                "compression": {"mode": "none"},
            }
        )
    return observations


def run_self_test() -> list[str]:
    errors: list[str] = []
    try:
        contract = load_yaml(CONTRACT)
        expect(contract.get("schema_version") == "1.0", "Context Budget schema must be v1.0.", errors)
        estimator = contract.get("estimator", {}) or {}
        expect(estimator.get("exact_model_tokenizer") is False, "Estimator must not claim exact model tokens.", errors)
        expect(
            estimator.get("utf8_bytes_per_estimated_token") == 3,
            "Conservative estimator divisor must remain explicit.",
            errors,
        )

        base_request = load_yaml(REQUEST)
        manifest = build_manifest(ROOT, base_request)

        measured_request = copy.deepcopy(base_request)
        measured_request["retrieval_observations"] = project_observations(manifest)
        report = build_budget_report(ROOT, manifest, measured_request)
        errors.extend(validate_budget_report(manifest, report))
        expect(report["decision"] == "within_budget", "Measured local fix should fit tight budget.", errors)
        expect(
            report["estimator"].get("exact_model_tokenizer") is False,
            "Budget report must preserve estimated-token semantics.",
            errors,
        )

        unmeasured_request = copy.deepcopy(base_request)
        unmeasured = build_budget_report(ROOT, manifest, unmeasured_request)
        unmeasured_errors = validate_budget_report(manifest, unmeasured)
        expect(unmeasured["decision"] == "unmeasured", "Missing project observations must be unmeasured.", errors)
        expect(
            any("Mutation requires Context Budget" in error for error in unmeasured_errors),
            "Mutation must be blocked when Context Budget is unmeasured.",
            errors,
        )

        pressure_request = copy.deepcopy(measured_request)
        pressure_request["retrieval_observations"].append(
            {
                "source_id": "background:large-reference",
                "role": "background_reference",
                "source_revision": "fixture:background-v1",
                "original_utf8_bytes": 40000,
                "selected_utf8_bytes": 40000,
                "compression": {"mode": "none"},
            }
        )
        pressure = build_budget_report(ROOT, manifest, pressure_request)
        expect(
            pressure["decision"] == "compression_required",
            f"Soft overflow should require compression, got {pressure['decision']}",
            errors,
        )
        expect(bool(pressure["compression"]["candidates"]), "Compression candidates must be reported.", errors)

        compressed_request = copy.deepcopy(measured_request)
        compressed_request["retrieval_observations"].append(
            {
                "source_id": "background:large-reference",
                "role": "background_reference",
                "source_revision": "fixture:background-v1",
                "original_utf8_bytes": 40000,
                "selected_utf8_bytes": 8000,
                "compression": {
                    "mode": "semantic_summary",
                    "summary_revision": "fixture:background-summary-v1",
                },
            }
        )
        compressed = build_budget_report(ROOT, manifest, compressed_request)
        errors.extend(validate_budget_report(manifest, compressed))
        expect(compressed["decision"] == "within_budget", "Valid summary should restore budget.", errors)
        expect(compressed["compression"]["saved_utf8_bytes"] == 32000, "Saved bytes must be recorded.", errors)

        blocked_request = copy.deepcopy(measured_request)
        blocked_request["retrieval_observations"].append(
            {
                "source_id": "background:hard-overflow",
                "role": "background_reference",
                "source_revision": "fixture:hard-v1",
                "original_utf8_bytes": 120000,
                "selected_utf8_bytes": 120000,
                "compression": {"mode": "none"},
            }
        )
        blocked = build_budget_report(ROOT, manifest, blocked_request)
        expect(blocked["decision"] == "blocked", "Hard overflow must be blocked.", errors)
        expect(bool(blocked["blocking_reasons"]), "Blocked report must contain reasons.", errors)

        policy_path = ROOT / ".ai" / "user-policy.yaml"
        policy_bytes = policy_path.read_bytes()
        protected_request = copy.deepcopy(measured_request)
        protected_request["retrieval_observations"].append(
            {
                "source_id": "repo:.ai/user-policy.yaml",
                "role": "user_policy",
                "source_revision": f"sha256:{hashlib.sha256(policy_bytes).hexdigest()}",
                "original_utf8_bytes": len(policy_bytes),
                "selected_utf8_bytes": max(1, len(policy_bytes) // 2),
                "compression": {
                    "mode": "semantic_summary",
                    "summary_revision": "fixture:invalid-policy-summary",
                },
            }
        )
        try:
            build_budget_report(ROOT, manifest, protected_request)
            errors.append("Protected User Policy semantic_summary must be rejected.")
        except BudgetError as exc:
            expect(
                any("Protected Context role" in error or "semantic_summary" in error for error in exc.errors),
                "Protected compression failure must explain the violated role.",
                errors,
            )

    except BudgetError as exc:
        errors.extend(exc.errors)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Context Budget self-test crashed: {exc}")

    return errors


def main() -> int:
    errors = run_self_test()
    if errors:
        print("Context Budget validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Context Budget validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
