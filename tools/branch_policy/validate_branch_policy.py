#!/usr/bin/env python3
"""Validate UnityAgent repository branch naming policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / ".github" / "branch-policy.json"
EXPECTED_REPOSITORY = "DarumaPPAP/UnityAgent"
EXPECTED_BRANCHES = {
    "main": ("常に統合済みの正本", "permanent"),
    "feature/*": ("新機能", "delete_after_pr_merge"),
    "fix/*": ("不具合修正", "delete_after_pr_merge"),
    "chore/*": ("CI・Docs・Refactor・Repository整理", "delete_after_pr_merge"),
    "release/*": ("Release準備が本当に必要な場合だけ", "delete_after_release"),
}
VALID_EXAMPLES = (
    "feature/cloud-development",
    "fix/control-plane-bootstrap",
    "chore/branch-policy",
    "release/v0.0.9-beta",
)
INVALID_EXAMPLES = (
    "develop",
    "codex/cloud-development",
    "refactor/runtime-cleanup",
    "docs/readme",
    "ci/workflow",
    "feature/CloudDevelopment",
    "feature/foo/bar",
    "feature/",
)


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate_policy(policy: dict) -> list[str]:
    errors: list[str] = []

    if policy.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if policy.get("repository") != EXPECTED_REPOSITORY:
        errors.append(f"repository must be {EXPECTED_REPOSITORY}")
    if policy.get("default_branch") != "main":
        errors.append("default_branch must be main")

    branches = policy.get("branches")
    if not isinstance(branches, dict):
        errors.append("branches must be an object")
        return errors

    if set(branches) != set(EXPECTED_BRANCHES):
        errors.append(
            "branches must contain exactly: " + ", ".join(EXPECTED_BRANCHES)
        )
    else:
        for name, (purpose, lifetime) in EXPECTED_BRANCHES.items():
            item = branches[name]
            if item.get("purpose") != purpose:
                errors.append(f"{name}: unexpected purpose")
            if item.get("lifetime") != lifetime:
                errors.append(f"{name}: unexpected lifetime")

    pattern_text = policy.get("working_branch_regex")
    if not isinstance(pattern_text, str):
        errors.append("working_branch_regex must be a string")
        return errors

    try:
        pattern = re.compile(pattern_text)
    except re.error as exc:
        errors.append(f"working_branch_regex is invalid: {exc}")
        return errors

    for branch in VALID_EXAMPLES:
        if pattern.fullmatch(branch) is None:
            errors.append(f"valid example rejected: {branch}")
    for branch in INVALID_EXAMPLES:
        if pattern.fullmatch(branch) is not None:
            errors.append(f"invalid example accepted: {branch}")

    rules = policy.get("rules", {})
    if rules.get("normal_pr_base") != "main":
        errors.append("rules.normal_pr_base must be main")
    for key in (
        "working_branches_merge_via_pull_request",
        "squash_merge_only",
        "delete_head_branch_after_merge",
    ):
        if rules.get(key) is not True:
            errors.append(f"rules.{key} must be true")

    return errors


def validate_branch(policy: dict, branch: str, event: str | None) -> list[str]:
    pattern = re.compile(policy["working_branch_regex"])
    default_branch = policy["default_branch"]

    if event == "pull_request":
        if pattern.fullmatch(branch) is None:
            return [
                f"Pull request branch '{branch}' violates branch policy. "
                "Use feature/*, fix/*, chore/*, or release/*."
            ]
        return []

    if branch == default_branch or pattern.fullmatch(branch) is not None:
        return []

    return [
        f"Branch '{branch}' violates branch policy. "
        f"Use {default_branch} or feature/*, fix/*, chore/*, release/*."
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch")
    parser.add_argument("--event")
    args = parser.parse_args()

    try:
        policy = load_policy()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Branch policy load failed: {exc}")
        return 1

    errors = validate_policy(policy)
    if args.branch and not errors:
        errors.extend(validate_branch(policy, args.branch, args.event))

    if errors:
        print("Branch policy validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    if args.branch:
        print(f"Branch policy validation passed: {args.branch}")
    else:
        print("Branch policy contract validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
