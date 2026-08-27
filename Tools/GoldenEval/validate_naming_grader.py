#!/usr/bin/env python3
"""Regression validation for the deterministic UnityAgent Type Naming grader."""

from __future__ import annotations

import shutil
from pathlib import Path

from naming_grader import GOLDEN_ARTIFACT_ROOT, grade_csharp_source, resolve_artifact_path
from run_golden_evals import infer_naming_failures

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "Tests" / "GoldenTasks" / "Fixtures" / "Naming"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def codes(grade: dict) -> set[str]:
    return {str(item.get("code")) for item in grade.get("findings", []) or []}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    good_debugger = grade_csharp_source(read_fixture("GoodCameraDebugger.cs"))
    require(good_debugger["passed"], "GoodCameraDebugger.cs must pass.", errors)

    good_tracker = grade_csharp_source(read_fixture("GoodCameraStateTracker.cs"))
    require(good_tracker["passed"], "GoodCameraStateTracker.cs must pass.", errors)

    long_name = grade_csharp_source(read_fixture("BadLongCameraController.cs"))
    require(long_name["passed"], "Length-only finding must not hard fail.", errors)
    require("NAME101_LENGTH_REVIEW" in codes(long_name), "Long Type must produce NAME101_LENGTH_REVIEW.", errors)

    suffix = grade_csharp_source(read_fixture("BadSuffixStacking.cs"))
    require(not suffix["passed"], "Role suffix stacking must hard fail.", errors)
    require("NAME001_ROLE_SUFFIX_STACKING" in codes(suffix), "Suffix stacking must produce NAME001.", errors)

    namespace_bad = grade_csharp_source(read_fixture("BadNamespaceRedundancy.cs"))
    require(namespace_bad["passed"], "Namespace redundancy is warning-only by default.", errors)
    require(
        "NAME103_NAMESPACE_REDUNDANCY" in codes(namespace_bad),
        "Namespace repetition must produce NAME103_NAMESPACE_REDUNDANCY.",
        errors,
    )

    namespace_good = grade_csharp_source(read_fixture("GoodNamespaceContext.cs"))
    require(
        "NAME103_NAMESPACE_REDUNDANCY" not in codes(namespace_good),
        "Good namespace context must not produce NAME103.",
        errors,
    )

    no_new_type = grade_csharp_source(
        read_fixture("GoodCameraDebugger.cs"),
        {"require_no_new_type": True},
    )
    require(not no_new_type["passed"], "require_no_new_type must fail when a Type is present.", errors)
    require("NAME005_UNEXPECTED_NEW_TYPE" in codes(no_new_type), "No-new-Type violation must produce NAME005.", errors)

    no_type_source = grade_csharp_source("namespace CameraDebugging { }", {"require_no_new_type": True})
    require(no_type_source["passed"], "require_no_new_type must pass when no Type declaration exists.", errors)

    sanitized = grade_csharp_source(
        '// class FakeCommentType {}\npublic class CameraDebugger { private const string Text = "class FakeStringType {}"; }'
    )
    require(
        sanitized["type_names"] == ["CameraDebugger"],
        "Comment/string sanitization must not extract fake Type declarations.",
        errors,
    )

    try:
        resolve_artifact_path("Artifacts/GoldenEval/../escape.cs")
        errors.append("Artifact path traversal must be rejected.")
    except Exception as exc:  # noqa: BLE001 - exact failure is asserted by behavior below.
        require("outside allowed Golden root" in str(exc), "Traversal rejection reason is unexpected.", errors)

    naming_case = {
        "category": "naming",
        "expectation": {"naming": {"required_type_names": ["CameraDebugger"]}},
    }

    temp_root = GOLDEN_ARTIFACT_ROOT / "_naming_validator_temp"
    temp_artifact = temp_root / "GOLDEN-NAMING-FIXTURE" / "CameraDebugger.cs"
    try:
        temp_artifact.parent.mkdir(parents=True, exist_ok=True)
        temp_artifact.write_text(read_fixture("GoodCameraDebugger.cs"), encoding="utf-8")
        success_result = {
            "generated_artifacts": [
                {
                    "path": str(temp_artifact.relative_to(ROOT)),
                    "language": "csharp",
                    "kind": "generated_source",
                }
            ]
        }
        success_failures, success_findings = infer_naming_failures(naming_case, success_result)
        require(success_failures == [], "Valid generated artifact must pass runner naming grading.", errors)
        require(
            not any(item.get("severity") == "error" for item in success_findings),
            "Valid generated artifact must not produce hard naming findings.",
            errors,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    missing_result = {
        "generated_artifacts": [
            {
                "path": "Artifacts/GoldenEval/does-not-exist/CameraDebugger.cs",
                "language": "csharp",
                "kind": "generated_source",
            }
        ]
    }
    missing_failures, _ = infer_naming_failures(naming_case, missing_result)
    require(missing_failures == ["broken_eval"], "Missing artifact must map to broken_eval.", errors)

    traversal_result = {
        "generated_artifacts": [
            {
                "path": "Artifacts/GoldenEval/../escape.cs",
                "language": "csharp",
                "kind": "generated_source",
            }
        ]
    }
    traversal_failures, _ = infer_naming_failures(naming_case, traversal_result)
    require(traversal_failures == ["broken_eval"], "Path traversal must map to broken_eval.", errors)

    if errors:
        print("Naming grader validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Naming grader validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
