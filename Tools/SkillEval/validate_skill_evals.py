#!/usr/bin/env python3
"""Validate deterministic contracts for UnityAgent Skill evaluation suites."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REQUIRED_CASE_FIELDS = {
    "id",
    "category",
    "evaluation_type",
    "prompt",
    "expected_primary",
    "must_include",
    "must_not",
    "pass_condition",
}
ALLOWED_EVALUATION_TYPES = {"routing", "behavior", "evidence"}
DEFAULT_REQUIRED_CATEGORIES = {
    "positive_direct",
    "positive_paraphrase",
    "negative_adjacent",
    "negative_simple",
    "conflict",
    "scope_guard",
    "evidence_guard",
}


def fail(message: str) -> None:
    print(f"[ERROR] {message}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    suite_root = root / "Tests" / "SkillEvals"
    paths = sorted(suite_root.glob("*.yaml")) if suite_root.is_dir() else []

    if not paths:
        fail("No Tests/SkillEvals/*.yaml suites were found.")
        return 1

    errors = 0
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    required_categories: set[str] = set()
    case_count = 0

    for path in paths:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001 - validator should report parser failures.
            fail(f"{path.relative_to(root)}: cannot parse YAML: {error}")
            errors += 1
            continue

        relative = path.relative_to(root).as_posix()
        if not isinstance(payload, dict):
            fail(f"{relative}: root must be a mapping.")
            errors += 1
            continue

        if payload.get("version") != 1:
            fail(f"{relative}: version must be 1.")
            errors += 1

        declared_categories = payload.get("required_categories", [])
        if declared_categories:
            if not isinstance(declared_categories, list) or not all(
                isinstance(value, str) and value for value in declared_categories
            ):
                fail(f"{relative}: required_categories must be a list of strings.")
                errors += 1
            else:
                required_categories.update(declared_categories)

        cases = payload.get("cases")
        if not isinstance(cases, list) or not cases:
            fail(f"{relative}: cases must be a non-empty list.")
            errors += 1
            continue

        for index, case in enumerate(cases, start=1):
            case_count += 1
            prefix = f"{relative}: case #{index}"
            if not isinstance(case, dict):
                fail(f"{prefix} must be a mapping.")
                errors += 1
                continue

            missing = sorted(REQUIRED_CASE_FIELDS.difference(case))
            if missing:
                fail(f"{prefix} missing fields: {', '.join(missing)}")
                errors += 1
                continue

            case_id = case["id"]
            if not isinstance(case_id, str) or not case_id.strip():
                fail(f"{prefix}: id must be a non-empty string.")
                errors += 1
            elif case_id in seen_ids:
                fail(f"{prefix}: duplicate id '{case_id}'.")
                errors += 1
            else:
                seen_ids.add(case_id)

            category = case["category"]
            if not isinstance(category, str) or not category.strip():
                fail(f"{prefix}: category must be a non-empty string.")
                errors += 1
            else:
                seen_categories.add(category)

            evaluation_type = case["evaluation_type"]
            if evaluation_type not in ALLOWED_EVALUATION_TYPES:
                fail(
                    f"{prefix}: evaluation_type must be one of "
                    f"{', '.join(sorted(ALLOWED_EVALUATION_TYPES))}."
                )
                errors += 1

            for key in ("prompt", "expected_primary", "pass_condition"):
                value = case[key]
                if not isinstance(value, str) or not value.strip():
                    fail(f"{prefix}: {key} must be a non-empty string.")
                    errors += 1

            for key in ("must_include", "must_not"):
                value = case[key]
                if not isinstance(value, list) or not value or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    fail(f"{prefix}: {key} must be a non-empty list of strings.")
                    errors += 1

            secondary = case.get("expected_secondary")
            if secondary is not None and (
                not isinstance(secondary, list)
                or not all(isinstance(item, str) and item.strip() for item in secondary)
            ):
                fail(f"{prefix}: expected_secondary must be a list of strings.")
                errors += 1

    if not required_categories:
        required_categories = set(DEFAULT_REQUIRED_CATEGORIES)

    missing_categories = sorted(required_categories.difference(seen_categories))
    if missing_categories:
        fail(
            "Skill eval coverage is incomplete; missing categories: "
            + ", ".join(missing_categories)
        )
        errors += 1

    print(
        f"Validated {case_count} Skill eval case(s) across {len(paths)} suite(s): "
        f"{errors} error(s)."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
