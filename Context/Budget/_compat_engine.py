#!/usr/bin/env python3
"""Deterministic Context Budget / Retrieval Budget accounting for UnityAgent."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import yaml

BUDGET_CONTRACT_PATH = Path(".ai/context-budget.yaml")

ROLE_PRIORITY = {
    "user_policy": 100,
    "context_pack": 95,
    "primary_skill": 90,
    "task_contract": 90,
    "project_fact": 85,
    "target_source": 80,
    "direct_dependency": 70,
    "required_context": 60,
    "conditional_context": 50,
    "context_include": 50,
    "external_reference": 45,
    "knowledge": 30,
    "background_reference": 20,
    "prior_failure": 10,
}


class BudgetError(ValueError):
    """Raised when budget inputs violate the canonical budget contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BudgetError([f"Missing file: {path.as_posix()}"])
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise BudgetError([f"Expected YAML mapping: {path.as_posix()}"])
    return document


def estimate_tokens(selected_utf8_bytes: int, divisor: int) -> int:
    """Return a conservative model-independent estimate, not an exact token count."""
    if selected_utf8_bytes <= 0:
        return 0
    return int(math.ceil(selected_utf8_bytes / divisor))


def _sha256_revision(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _merge_expected(
    expected: dict[str, dict[str, Any]],
    item: dict[str, Any],
) -> None:
    source_id = str(item["source_id"])
    current = expected.get(source_id)
    if current is None:
        expected[source_id] = item
        return

    current["required"] = bool(current.get("required")) or bool(item.get("required"))
    if ROLE_PRIORITY.get(str(item.get("role")), 0) > ROLE_PRIORITY.get(str(current.get("role")), 0):
        current["role"] = item["role"]
    for key in ("source_path", "repository", "path"):
        if item.get(key) and not current.get(key):
            current[key] = item[key]


def _repo_expected(path: str, role: str, required: bool = True) -> dict[str, Any]:
    return {
        "source_id": f"repo:{path}",
        "role": role,
        "required": required,
        "source_path": path,
        "auto_measurable": True,
    }


def _project_expected(path: str, role: str, required: bool = True) -> dict[str, Any]:
    return {
        "source_id": f"project:{path}",
        "role": role,
        "required": required,
        "source_path": path,
        "auto_measurable": False,
    }


def _external_expected(
    repository: str,
    path: str,
    required: bool,
) -> dict[str, Any]:
    return {
        "source_id": f"external:{repository}:{path}",
        "role": "external_reference",
        "required": required,
        "repository": repository,
        "path": path,
        "auto_measurable": False,
    }


def _fact_expected(item: dict[str, Any]) -> dict[str, Any]:
    key = str(item.get("key", ""))
    payload = {
        "key": key,
        "value": item.get("value"),
        "revision": item.get("revision"),
        "freshness": item.get("freshness"),
    }
    content = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True).encode("utf-8")
    return {
        "source_id": f"fact:{key}",
        "role": "project_fact",
        "required": True,
        "auto_measurable": True,
        "generated_content": content,
        "source_revision": str(item.get("revision", "generated")),
    }


def expected_artifacts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}

    for item in manifest.get("policy", {}).get("loaded", []) or []:
        if isinstance(item, dict) and item.get("source_path"):
            _merge_expected(expected, _repo_expected(str(item["source_path"]), "user_policy"))

    context = manifest.get("context", {}) or {}
    context_pack = context.get("context_pack", {}) or {}
    if context_pack.get("source_path"):
        _merge_expected(expected, _repo_expected(str(context_pack["source_path"]), "context_pack"))
    skill = context.get("primary_skill", {}) or {}
    if skill.get("source_path"):
        _merge_expected(expected, _repo_expected(str(skill["source_path"]), "primary_skill"))

    task_contract = manifest.get("harness", {}).get("task_contract", {}) or {}
    if task_contract.get("source_path"):
        _merge_expected(expected, _repo_expected(str(task_contract["source_path"]), "task_contract"))

    for fact in manifest.get("project_facts", {}).get("loaded", []) or []:
        if isinstance(fact, dict) and fact.get("key"):
            _merge_expected(expected, _fact_expected(fact))

    for key, role, required in (
        ("required_context", "required_context", True),
        ("conditional_context", "conditional_context", True),
        ("context_includes", "context_include", True),
    ):
        for item in context.get(key, []) or []:
            if isinstance(item, dict) and item.get("source_path"):
                _merge_expected(expected, _repo_expected(str(item["source_path"]), role, required))

    for item in context.get("source_files", []) or []:
        if not isinstance(item, dict) or not item.get("source_path"):
            continue
        reason = str(item.get("reason", ""))
        role = "target_source" if reason == "mutation_target" else "direct_dependency"
        _merge_expected(expected, _project_expected(str(item["source_path"]), role))

    for item in manifest.get("knowledge", {}).get("loaded", []) or []:
        if isinstance(item, dict) and item.get("source_path"):
            _merge_expected(expected, _repo_expected(str(item["source_path"]), "knowledge"))

    for item in context.get("external_references", []) or []:
        if not isinstance(item, dict):
            continue
        repository = str(item.get("repository", ""))
        path = str(item.get("path", ""))
        if repository and path:
            _merge_expected(
                expected,
                _external_expected(repository, path, str(item.get("requirement")) == "required"),
            )

    return sorted(expected.values(), key=lambda item: str(item["source_id"]))


def _auto_observation(root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    role = str(expected["role"])
    source_id = str(expected["source_id"])
    if "generated_content" in expected:
        content = bytes(expected["generated_content"])
        revision = str(expected.get("source_revision") or _sha256_revision(content))
    else:
        source_path = str(expected.get("source_path", ""))
        path = root / source_path
        if not path.is_file():
            raise BudgetError([f"Budget auto-measure source does not exist: {source_path}"])
        content = path.read_bytes()
        revision = _sha256_revision(content)

    size = len(content)
    return {
        "source_id": source_id,
        "role": role,
        "source_revision": revision,
        "original_utf8_bytes": size,
        "selected_utf8_bytes": size,
        "compression": {"mode": "none"},
        "measurement": "automatic",
    }


def _normalize_observation(
    raw: Any,
    *,
    expected: dict[str, Any] | None,
    contract: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BudgetError(["retrieval_observations entries must be mappings."])

    source_id = str(raw.get("source_id", "")).strip()
    role = str(raw.get("role", "")).strip()
    revision = str(raw.get("source_revision", "")).strip()
    compression = raw.get("compression")
    errors: list[str] = []

    allowed_roles = set(contract.get("retrieval_observation", {}).get("allowed_roles", []) or [])
    allowed_modes = set(contract.get("retrieval_observation", {}).get("compression_modes", []) or [])
    if not source_id:
        errors.append("retrieval_observation.source_id is required.")
    if role not in allowed_roles:
        errors.append(f"Unsupported retrieval role: {role}")
    if not revision:
        errors.append(f"source_revision is required: {source_id}")
    if not isinstance(compression, dict):
        errors.append(f"compression mapping is required: {source_id}")
        compression = {}
    mode = str(compression.get("mode", ""))
    if mode not in allowed_modes:
        errors.append(f"Unsupported compression mode: {source_id}={mode}")

    original = raw.get("original_utf8_bytes")
    selected = raw.get("selected_utf8_bytes")
    if not isinstance(original, int) or original < 0:
        errors.append(f"original_utf8_bytes must be an integer >= 0: {source_id}")
    if not isinstance(selected, int) or selected < 0:
        errors.append(f"selected_utf8_bytes must be an integer >= 0: {source_id}")
    if isinstance(original, int) and isinstance(selected, int) and selected > original:
        errors.append(f"selected_utf8_bytes exceeds original: {source_id}")

    if expected is not None:
        expected_role = str(expected.get("role", ""))
        if role != expected_role:
            errors.append(f"Observation role mismatch: {source_id}={role}, expected={expected_role}")
        if expected.get("required") and selected == 0:
            errors.append(f"Required Context artifact cannot be dropped: {source_id}")

        if expected.get("auto_measurable") and expected.get("source_path"):
            path = root / str(expected["source_path"])
            if path.is_file():
                content = path.read_bytes()
                actual_size = len(content)
                actual_revision = _sha256_revision(content)
                if original != actual_size:
                    errors.append(
                        f"Local source original_utf8_bytes mismatch: {source_id}={original}, actual={actual_size}"
                    )
                if revision != actual_revision:
                    errors.append(f"Local source revision mismatch: {source_id}")

    policy = contract.get("compression_policy", {}) or {}
    full_only = set(policy.get("full_only_roles", []) or [])
    excerpt_allowed = set(policy.get("lossless_excerpt_allowed_roles", []) or [])
    summary_allowed = set(policy.get("semantic_summary_allowed_roles", []) or [])

    if mode != "none" and role in full_only:
        errors.append(f"Protected Context role must remain full: {source_id} ({role})")
    if mode == "none" and isinstance(original, int) and isinstance(selected, int) and original != selected:
        errors.append(f"compression.mode none requires original == selected: {source_id}")
    if mode == "lossless_excerpt":
        if role not in excerpt_allowed:
            errors.append(f"lossless_excerpt is not allowed for role {role}: {source_id}")
        ranges = compression.get("selected_ranges")
        if not isinstance(ranges, list) or not ranges:
            errors.append(f"lossless_excerpt requires selected_ranges: {source_id}")
    if mode == "semantic_summary":
        if role not in summary_allowed:
            errors.append(f"semantic_summary is not allowed for role {role}: {source_id}")
        if not str(compression.get("summary_revision", "")).strip():
            errors.append(f"semantic_summary requires summary_revision: {source_id}")

    if errors:
        raise BudgetError(errors)

    result = {
        "source_id": source_id,
        "role": role,
        "source_revision": revision,
        "original_utf8_bytes": original,
        "selected_utf8_bytes": selected,
        "compression": dict(compression),
        "measurement": str(raw.get("measurement", "explicit")),
    }
    return result


def _compression_candidates(
    artifacts: list[dict[str, Any]],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    policy = contract.get("compression_policy", {}) or {}
    excerpt_allowed = set(policy.get("lossless_excerpt_allowed_roles", []) or [])
    summary_allowed = set(policy.get("semantic_summary_allowed_roles", []) or [])
    candidates: list[dict[str, Any]] = []
    for item in artifacts:
        role = str(item["role"])
        modes: list[str] = []
        if role in excerpt_allowed:
            modes.append("lossless_excerpt")
        if role in summary_allowed:
            modes.append("semantic_summary")
        if not modes or item.get("selected_utf8_bytes", 0) <= 0:
            continue
        candidates.append(
            {
                "source_id": item["source_id"],
                "role": role,
                "selected_utf8_bytes": item["selected_utf8_bytes"],
                "allowed_modes": modes,
            }
        )
    candidates.sort(key=lambda item: int(item["selected_utf8_bytes"]), reverse=True)
    return candidates


def build_budget_report(
    root: Path,
    manifest: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    contract = load_yaml(root / BUDGET_CONTRACT_PATH)
    route_id = str(manifest.get("task", {}).get("route", ""))
    route_profiles = contract.get("route_profiles", {}) or {}
    profile_id = str(route_profiles.get(route_id, ""))
    profiles = contract.get("profiles", {}) or {}
    profile = profiles.get(profile_id)
    if not isinstance(profile, dict):
        raise BudgetError([f"No Context Budget profile for route: {route_id}"])

    expected_list = expected_artifacts(manifest)
    expected_by_id = {str(item["source_id"]): item for item in expected_list}

    raw_observations = request.get("retrieval_observations", []) or []
    if not isinstance(raw_observations, list):
        raise BudgetError(["request.retrieval_observations must be a list."])

    explicit: dict[str, dict[str, Any]] = {}
    for raw in raw_observations:
        if not isinstance(raw, dict):
            raise BudgetError(["retrieval_observations entries must be mappings."])
        source_id = str(raw.get("source_id", "")).strip()
        if source_id in explicit:
            raise BudgetError([f"Duplicate retrieval observation: {source_id}"])
        explicit[source_id] = raw

    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []
    for expected in expected_list:
        source_id = str(expected["source_id"])
        raw = explicit.pop(source_id, None)
        if raw is not None:
            artifacts.append(_normalize_observation(raw, expected=expected, contract=contract, root=root))
        elif expected.get("auto_measurable"):
            artifacts.append(_auto_observation(root, expected))
        else:
            missing.append(source_id)

    for source_id, raw in sorted(explicit.items()):
        role = str(raw.get("role", "")) if isinstance(raw, dict) else ""
        if role not in {"background_reference", "prior_failure", "knowledge"}:
            raise BudgetError([f"Unexpected retrieval observation not selected by Context: {source_id}"])
        artifacts.append(_normalize_observation(raw, expected=None, contract=contract, root=root))

    divisor = int(contract.get("estimator", {}).get("utf8_bytes_per_estimated_token", 3))
    for item in artifacts:
        item["estimated_tokens"] = estimate_tokens(int(item["selected_utf8_bytes"]), divisor)

    original_bytes = sum(int(item["original_utf8_bytes"]) for item in artifacts)
    selected_bytes = sum(int(item["selected_utf8_bytes"]) for item in artifacts)
    estimated = sum(int(item["estimated_tokens"]) for item in artifacts)
    external_fetches = len(
        [item for item in expected_list if str(item.get("source_id", "")).startswith("external:")]
    )
    context_includes = len(manifest.get("context", {}).get("context_includes", []) or [])

    context_pack_path = str(manifest.get("context", {}).get("context_pack", {}).get("source_path", ""))
    expansion_hops = 0
    if context_pack_path:
        context_pack = load_yaml(root / context_pack_path)
        expansion_hops = int(context_pack.get("limits", {}).get("context_expansion_hops", 0) or 0)

    retrieval_limit = profile.get("retrieval", {}) or {}
    context_limit = profile.get("context", {}) or {}
    hard_reasons: list[str] = []
    if len(artifacts) > int(retrieval_limit.get("max_artifacts", 0)):
        hard_reasons.append("max_artifacts_exceeded")
    if selected_bytes > int(retrieval_limit.get("max_selected_utf8_bytes", 0)):
        hard_reasons.append("max_selected_utf8_bytes_exceeded")
    if external_fetches > int(retrieval_limit.get("max_external_fetches", 0)):
        hard_reasons.append("max_external_fetches_exceeded")
    if context_includes > int(retrieval_limit.get("max_context_includes", 0)):
        hard_reasons.append("max_context_includes_exceeded")
    if expansion_hops > int(retrieval_limit.get("max_expansion_hops", 0)):
        hard_reasons.append("max_expansion_hops_exceeded")

    soft_limit = int(context_limit.get("soft_estimated_tokens", 0))
    hard_limit = int(context_limit.get("hard_estimated_tokens", 0))
    if estimated > hard_limit:
        hard_reasons.append("hard_estimated_tokens_exceeded")

    if hard_reasons:
        decision = "blocked"
    elif missing:
        decision = "unmeasured"
    elif estimated > soft_limit:
        decision = "compression_required"
    else:
        decision = "within_budget"

    compressed = [item for item in artifacts if item.get("compression", {}).get("mode") != "none"]
    saved_bytes = original_bytes - selected_bytes
    candidates = _compression_candidates(artifacts, contract)

    return {
        "contract": BUDGET_CONTRACT_PATH.as_posix(),
        "profile": profile_id,
        "estimator": {
            "id": contract.get("estimator", {}).get("id"),
            "exact_model_tokenizer": False,
            "utf8_bytes_per_estimated_token": divisor,
        },
        "coverage": {
            "expected_artifacts": len(expected_list),
            "measured_artifacts": len(artifacts),
            "missing_observations": missing,
        },
        "retrieval": {
            "artifacts": len(artifacts),
            "original_utf8_bytes": original_bytes,
            "selected_utf8_bytes": selected_bytes,
            "external_fetches": external_fetches,
            "context_includes": context_includes,
            "expansion_hops": expansion_hops,
            "limits": dict(retrieval_limit),
        },
        "context": {
            "estimated_tokens": estimated,
            "soft_estimated_tokens": soft_limit,
            "hard_estimated_tokens": hard_limit,
        },
        "compression": {
            "applied": bool(compressed),
            "compressed_artifacts": len(compressed),
            "saved_utf8_bytes": saved_bytes,
            "modes": sorted({str(item.get("compression", {}).get("mode")) for item in compressed}),
            "candidates": candidates,
        },
        "artifacts": artifacts,
        "decision": decision,
        "blocking_reasons": hard_reasons,
    }


def validate_budget_report(
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    decision = str(report.get("decision", ""))
    if decision not in {"within_budget", "compression_required", "blocked", "unmeasured"}:
        errors.append(f"Unsupported Context Budget decision: {decision}")

    coverage = report.get("coverage", {}) or {}
    missing = coverage.get("missing_observations", []) or []
    if decision == "within_budget" and missing:
        errors.append("within_budget cannot have missing observations.")

    context = report.get("context", {}) or {}
    estimated = int(context.get("estimated_tokens", 0) or 0)
    soft = int(context.get("soft_estimated_tokens", 0) or 0)
    hard = int(context.get("hard_estimated_tokens", 0) or 0)
    if soft <= 0 or hard <= 0 or soft >= hard:
        errors.append("Context Budget requires 0 < soft_estimated_tokens < hard_estimated_tokens.")
    if decision == "within_budget" and estimated > soft:
        errors.append("within_budget exceeds soft Context Budget.")
    if decision == "compression_required" and not (soft < estimated <= hard):
        errors.append("compression_required must be above soft and at or below hard Context Budget.")
    if decision == "blocked" and not report.get("blocking_reasons"):
        errors.append("blocked Context Budget requires blocking_reasons.")

    mutation_target = str(manifest.get("task", {}).get("fingerprint", {}).get("mutation_target", "none"))
    if mutation_target != "none" and decision != "within_budget":
        errors.append(
            f"Mutation requires Context Budget within_budget: mutation_target={mutation_target}, decision={decision}"
        )
    return errors
