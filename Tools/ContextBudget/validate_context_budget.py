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
from context_budget_validation import validate_budget_integrity  # noqa: E402
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


def background_observation(source_id: str, original: int, selected: int, mode: str) -> dict:
    compression: dict = {"mode": mode}
    if mode == "semantic_summary":
        compression["summary_revision"] = f"fixture:{source_id}:summary"
    return {
        "source_id": source_id,
        "role": "background_reference",
        "source_revision": f"fixture:{source_id}:source",
        "original_utf8_bytes": original,
        "selected_utf8_bytes": selected,
        "compression": compression,
    }


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
        errors.extend(validate_budget_integrity(ROOT, manifest, report))
        expect(report["decision"] == "within_budget", "Measured local fix should fit tight budget.", errors)
        expect(
            report["estimator"].get("exact_model_tokenizer") is False,
            "Budget report must preserve estimated-token semantics.",
            errors,
        )

        unmeasured_request = copy.deepcopy(base_request)
        unmeasured_request["retrieval_observations"] = []
        unmeasured = build_budget_report(ROOT, manifest, unmeasured_request)
        unmeasured_errors = validate_budget_integrity(ROOT, manifest, unmeasured)
        expect(unmeasured["decision"] == "unmeasured", "Missing project observations must be unmeasured.", errors)
        expect(
            any("Mutation requires Context Budget" in error for error in unmeasured_errors),
            "Mutation must be blocked when Context Budget is unmeasured.",
            errors,
        )

        base_bytes = int(report["retrieval"]["selected_utf8_bytes"])
        divisor = int(report["estimator"]["utf8_bytes_per_estimated_token"])
        soft_bytes = int(report["context"]["soft_estimated_tokens"]) * divisor
        hard_bytes = min(
            int(report["context"]["hard_estimated_tokens"]) * divisor,
            int(report["retrieval"]["limits"]["max_selected_utf8_bytes"]),
        )
        pressure_bytes = max(1, soft_bytes - base_bytes + divisor * 1000)
        if base_bytes + pressure_bytes >= hard_bytes:
            pressure_bytes = max(1, hard_bytes - base_bytes - divisor)

        pressure_request = copy.deepcopy(measured_request)
        pressure_request["retrieval_observations"].append(
            background_observation("background:large-reference", pressure_bytes, pressure_bytes, "none")
        )
        pressure = build_budget_report(ROOT, manifest, pressure_request)
        expect(
            pressure["decision"] == "compression_required",
            f"Soft overflow should require compression, got {pressure['decision']}",
            errors,
        )
        expect(bool(pressure["compression"]["candidates"]), "Compression candidates must be reported.", errors)
        pressure_errors = validate_budget_integrity(ROOT, manifest, pressure)
        expect(
            any("Mutation requires Context Budget" in error for error in pressure_errors),
            "Mutation must be blocked while compression is required.",
            errors,
        )

        compressed_selected = max(1, pressure_bytes // 5)
        compressed_request = copy.deepcopy(measured_request)
        compressed_request["retrieval_observations"].append(
            background_observation(
                "background:large-reference",
                pressure_bytes,
                compressed_selected,
                "semantic_summary",
            )
        )
        compressed = build_budget_report(ROOT, manifest, compressed_request)
        errors.extend(validate_budget_integrity(ROOT, manifest, compressed))
        expect(compressed["decision"] == "within_budget", "Valid summary should restore budget.", errors)
        expect(
            compressed["compression"]["saved_utf8_bytes"] == pressure_bytes - compressed_selected,
            "Saved bytes must be recorded.",
            errors,
        )

        tampered = copy.deepcopy(compressed)
        tampered["context"]["estimated_tokens"] = 1
        tampered["decision"] = "within_budget"
        tampered_errors = validate_budget_integrity(ROOT, manifest, tampered)
        expect(
            any("estimated_tokens does not match artifact sum" in error for error in tampered_errors),
            "Persisted estimated-token tampering must be rejected.",
            errors,
        )

        tampered_missing = copy.deepcopy(unmeasured)
        tampered_missing["coverage"]["missing_observations"] = []
        tampered_missing["decision"] = "within_budget"
        tampered_missing_errors = validate_budget_integrity(ROOT, manifest, tampered_missing)
        expect(
            any("missing_observations does not match" in error for error in tampered_missing_errors),
            "Persisted missing-observation tampering must be rejected.",
            errors,
        )

        hard_extra = max(1, hard_bytes - base_bytes + divisor * 1000)
        blocked_request = copy.deepcopy(measured_request)
        blocked_request["retrieval_observations"].append(
            background_observation("background:hard-overflow", hard_extra, hard_extra, "none")
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
