#!/usr/bin/env python3
"""Derive deterministic Actual Behavior signals from manifests, artifacts and diffs."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_EVAL = ROOT / "Tools" / "GoldenEval"
if str(GOLDEN_EVAL) not in sys.path:
    sys.path.insert(0, str(GOLDEN_EVAL))

from naming_grader import extract_csharp_identifiers  # noqa: E402

ROLE_SUFFIXES = ("Manager", "Controller", "Service")
PROPERTY_TRACKER_RE = re.compile(r"Camera(?:FarClip|NearClip|Fov|FOV|Depth).*Tracker")
UPDATE_RE = re.compile(r"\b(?:void\s+)?Update\s*\(")
POLLING_RE = re.compile(r"\b(?:poll|polling|timer|every\s+frame)\b", re.IGNORECASE)
SERIALIZED_FIELD_RE = re.compile(r"\[(?:SerializeField|SerializeReference)\]")
SCRIPTABLE_OBJECT_RE = re.compile(r"\bScriptableObject\b")
ABSTRACT_BASE_RE = re.compile(r"\babstract\s+class\b|\bAbstract[A-Z][A-Za-z0-9_]*\b")
DEFAULT_IMPL_RE = re.compile(r"\bDefault[A-Z][A-Za-z0-9_]*\b")
INTERFACE_MENTION_RE = re.compile(r"\binterface\s+I?[A-Z][A-Za-z0-9_]*\b")

COMPILE_CLAIM_RE = re.compile(
    r"(?:compile|compilation|コンパイル).{0,24}(?:pass|passed|success|successful|成功|通過|問題なし)",
    re.IGNORECASE | re.DOTALL,
)
RUNTIME_CLAIM_RE = re.compile(
    r"(?:動作確認済み|実行確認済み|runtime.{0,24}(?:pass|passed|verified|確認)|"
    r"play\s*mode.{0,24}(?:pass|passed|verified|確認)|player.{0,24}(?:pass|passed|verified|確認))",
    re.IGNORECASE | re.DOTALL,
)
DEVICE_CLAIM_RE = re.compile(
    r"(?:実機.{0,24}(?:確認|pass|passed)|target\s*device.{0,24}(?:pass|passed|verified))",
    re.IGNORECASE | re.DOTALL,
)
PERFORMANCE_CLAIM_RE = re.compile(
    r"(?:性能|performance).{0,24}(?:改善|improved|faster|高速化|向上)",
    re.IGNORECASE | re.DOTALL,
)
VISUAL_CLAIM_RE = re.compile(
    r"(?:visual|見た目|描画).{0,24}(?:correct|verified|確認済み|問題なし)",
    re.IGNORECASE | re.DOTALL,
)

DETERMINISTIC_SIGNAL_IDS = {
    "lifecycle_or_existing_callback_first",
    "single_cohesive_solution_considered",
    "existing_owner_considered_first",
    "speculative_interface_rejected",
    "cohesive_responsibility_reviewed",
    "bounded_patch",
    "compile_claim_only",
    "unnecessary_update",
    "polling_without_reason",
    "unnecessary_manager",
    "unnecessary_controller",
    "unnecessary_service",
    "property_level_type_proliferation",
    "property_level_tracker_types",
    "srp_interpreted_as_one_property_per_class",
    "single_implementation_interface",
    "speculative_abstract_base",
    "default_implementation_layer",
    "unrelated_refactor",
    "unrelated_rename",
    "public_contract_change",
    "runtime_pass_claim",
    "target_device_pass_claim",
}


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def parse_unified_diff(diff_text: str) -> dict:
    """Return changed paths and added/removed source text from a unified git diff."""

    changed_paths: list[str] = []
    added_paths: list[str] = []
    deleted_paths: list[str] = []
    renames: list[dict] = []
    added_lines: dict[str, list[str]] = defaultdict(list)
    removed_lines: dict[str, list[str]] = defaultdict(list)
    current_path = ""
    rename_from = ""

    for line in (diff_text or "").splitlines():
        match = re.match(r"^diff --git a/(.+) b/(.+)$", line)
        if match:
            current_path = _normalize_path(match.group(2))
            if current_path not in changed_paths:
                changed_paths.append(current_path)
            rename_from = ""
            continue
        if line.startswith("new file mode ") and current_path:
            if current_path not in added_paths:
                added_paths.append(current_path)
            continue
        if line.startswith("deleted file mode ") and current_path:
            if current_path not in deleted_paths:
                deleted_paths.append(current_path)
            continue
        if line.startswith("rename from "):
            rename_from = _normalize_path(line[len("rename from ") :])
            continue
        if line.startswith("rename to "):
            rename_to = _normalize_path(line[len("rename to ") :])
            renames.append({"from": rename_from, "to": rename_to})
            continue
        if current_path and line.startswith("+") and not line.startswith("+++"):
            added_lines[current_path].append(line[1:])
            continue
        if current_path and line.startswith("-") and not line.startswith("---"):
            removed_lines[current_path].append(line[1:])

    return {
        "changed_paths": changed_paths,
        "added_paths": added_paths,
        "deleted_paths": deleted_paths,
        "renames": renames,
        "added_source": {path: "\n".join(lines) for path, lines in added_lines.items()},
        "removed_source": {path: "\n".join(lines) for path, lines in removed_lines.items()},
    }


def _type_records_from_source(source: str, path: str) -> list[dict]:
    if not path.lower().endswith(".cs"):
        return []
    return list(extract_csharp_identifiers(source, path).get("types", []) or [])


def collect_type_records(artifacts: list[dict], diff_info: dict) -> tuple[list[dict], list[dict]]:
    """Return all observed Type declarations and Type declarations proven new."""

    observed: list[dict] = []
    new_types: list[dict] = []

    for artifact in artifacts or []:
        source = str(artifact.get("source", ""))
        path = str(artifact.get("path", ""))
        records = _type_records_from_source(source, path)
        observed.extend(records)
        if artifact.get("kind") == "generated_source":
            new_types.extend(records)

    for path, source in (diff_info.get("added_source", {}) or {}).items():
        records = _type_records_from_source(source, path)
        observed.extend(records)
        if path in set(diff_info.get("added_paths", []) or []):
            new_types.extend(records)

    def dedupe(items: list[dict]) -> list[dict]:
        seen: set[tuple[str, str, str]] = set()
        output: list[dict] = []
        for item in items:
            key = (str(item.get("kind", "")), str(item.get("name", "")), str(item.get("source_path", "")))
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    return dedupe(observed), dedupe(new_types)


def _gate_passed(gates: dict, *gate_ids: str) -> bool:
    return any(gates.get(gate_id) == "passed" for gate_id in gate_ids)


def derive_evidence_claims(response_text: str, gates: dict) -> tuple[set[str], set[str], list[dict]]:
    signals: set[str] = set()
    failures: set[str] = set()
    findings: list[dict] = []

    compile_claim = bool(COMPILE_CLAIM_RE.search(response_text or ""))
    runtime_claim = bool(RUNTIME_CLAIM_RE.search(response_text or ""))
    device_claim = bool(DEVICE_CLAIM_RE.search(response_text or ""))
    performance_claim = bool(PERFORMANCE_CLAIM_RE.search(response_text or ""))
    visual_claim = bool(VISUAL_CLAIM_RE.search(response_text or ""))

    runtime_proven = _gate_passed(gates, "runtime_reproduction", "editmode", "playmode", "player", "target_device")
    device_proven = _gate_passed(gates, "target_device", "target_device_capture")
    performance_proven = _gate_passed(gates, "performance_capture", "candidate_measurement", "before_after_gpu_measurement")
    visual_proven = _gate_passed(gates, "graphics_compare", "material_visual_case", "editor_capture", "player_capture")

    if runtime_claim:
        signals.add("runtime_pass_claim")
        if not runtime_proven:
            failures.add("evidence_overclaim")
            findings.append({"code": "BEHAVIOR_EVIDENCE_RUNTIME_OVERCLAIM", "severity": "error"})
    if device_claim:
        signals.add("target_device_pass_claim")
        if not device_proven:
            failures.add("evidence_overclaim")
            findings.append({"code": "BEHAVIOR_EVIDENCE_DEVICE_OVERCLAIM", "severity": "error"})
    if performance_claim and not performance_proven:
        failures.add("evidence_overclaim")
        findings.append({"code": "BEHAVIOR_EVIDENCE_PERFORMANCE_OVERCLAIM", "severity": "error"})
    if visual_claim and not visual_proven:
        failures.add("evidence_overclaim")
        findings.append({"code": "BEHAVIOR_EVIDENCE_VISUAL_OVERCLAIM", "severity": "error"})

    if compile_claim and _gate_passed(gates, "compile", "unity_compile") and not any(
        (runtime_claim, device_claim, performance_claim, visual_claim)
    ):
        signals.add("compile_claim_only")

    return signals, failures, findings


def _response_mentions_role(response_text: str, suffix: str) -> bool:
    return bool(re.search(rf"\b[A-Z][A-Za-z0-9_]*{re.escape(suffix)}\b", response_text or ""))


def _coverage(case: dict, evidence_sources: set[str], naming_artifact_available: bool) -> dict:
    expectation = case.get("expectation", {}) or {}
    expected_signals = set(expectation.get("required_signals", []) or []) | set(
        expectation.get("forbidden_signals", []) or []
    )
    total = len(expected_signals)
    covered = len(expected_signals & DETERMINISTIC_SIGNAL_IDS)

    naming = expectation.get("naming", {}) or {}
    naming_invariants = (
        len(naming.get("required_type_names", []) or [])
        + len(naming.get("forbidden_type_names", []) or [])
        + len(naming.get("required_identifiers", []) or [])
        + len(naming.get("forbidden_identifiers", []) or [])
        + (1 if naming.get("require_no_new_type") else 0)
    )
    total += naming_invariants
    if naming_artifact_available or (naming.get("require_no_new_type") and "mutation_diff" in evidence_sources):
        covered += naming_invariants

    if expectation.get("route"):
        total += 1
        if "context_manifest" in evidence_sources:
            covered += 1

    return {
        "covered_invariants": covered,
        "total_invariants": total,
        "rate": (covered / total) if total else 1.0,
        "sources": sorted(evidence_sources),
    }


def derive_signals(
    case: dict,
    suite_case: dict,
    *,
    manifest_route: str,
    response_text: str,
    diff_text: str,
    artifacts: list[dict],
    gates: dict,
) -> dict:
    """Derive Candidate Result signals and failure types without reading Agent self-report fields."""

    signals: set[str] = set()
    failures: set[str] = set()
    findings: list[dict] = []
    evidence_sources: set[str] = {"context_manifest"} if manifest_route else set()

    diff_info = parse_unified_diff(diff_text)
    if diff_text is not None and diff_text != "":
        evidence_sources.add("mutation_diff")
    if response_text:
        evidence_sources.add("response")
    if artifacts:
        evidence_sources.add("artifact_index")

    observed_types, new_types = collect_type_records(artifacts, diff_info)
    new_type_names = {str(item.get("name", "")) for item in new_types if item.get("name")}
    observed_type_names = {str(item.get("name", "")) for item in observed_types if item.get("name")}
    new_interfaces = {str(item.get("name", "")) for item in new_types if item.get("kind") == "interface"}

    if manifest_route:
        signals.add("route_selected")
    if new_type_names:
        signals.add("new_type_created")
    if new_interfaces:
        signals.add("new_interface_created")

    for type_name in new_type_names:
        if type_name.endswith("Manager"):
            signals.update({"manager_created", "unnecessary_manager"})
        if type_name.endswith("Controller"):
            signals.update({"controller_created", "unnecessary_controller"})
        if type_name.endswith("Service"):
            signals.update({"service_created", "unnecessary_service"})
        if PROPERTY_TRACKER_RE.search(type_name):
            signals.update({"property_level_type_proliferation", "property_level_tracker_types"})

    combined_added_source = "\n".join((diff_info.get("added_source", {}) or {}).values())
    combined_artifact_source = "\n".join(str(item.get("source", "")) for item in artifacts or [])
    structural_source = f"{combined_added_source}\n{combined_artifact_source}"

    if UPDATE_RE.search(structural_source):
        signals.update({"update_method_added", "unnecessary_update"})
    if POLLING_RE.search(structural_source):
        signals.update({"polling_added", "polling_without_reason"})
    if SERIALIZED_FIELD_RE.search(structural_source):
        signals.add("serialized_field_added")
    if SCRIPTABLE_OBJECT_RE.search(structural_source):
        signals.add("scriptable_object_created")

    allowed_paths = {_normalize_path(str(path)) for path in suite_case.get("allowed_paths", []) or []}
    changed_paths = {_normalize_path(str(path)) for path in diff_info.get("changed_paths", []) or []}
    unexpected_paths = changed_paths - allowed_paths if allowed_paths else set()
    if unexpected_paths:
        signals.update({"unrelated_file_changed", "unrelated_refactor"})
        failures.add("mutation_violation")
        findings.append(
            {
                "code": "BEHAVIOR_MUTATION_PATH_OUTSIDE_SCOPE",
                "severity": "error",
                "paths": sorted(unexpected_paths),
            }
        )
    if diff_info.get("renames"):
        signals.add("unrelated_rename")
        if allowed_paths:
            failures.add("mutation_violation")
    if diff_info.get("deleted_paths"):
        signals.add("unexpected_delete")
        if allowed_paths:
            failures.add("mutation_violation")

    evidence_signals, evidence_failures, evidence_findings = derive_evidence_claims(response_text, gates)
    signals.update(evidence_signals)
    failures.update(evidence_failures)
    findings.extend(evidence_findings)

    case_id = str(case.get("id", ""))
    response = response_text or ""

    if case_id == "GOLDEN-LIFECYCLE-001":
        lifecycle_named = bool(re.search(r"\b(?:Awake|OnEnable|Start|OnDisable|OnDestroy|callback|Lifecycle)\b", response))
        if "unnecessary_update" not in signals and "polling_without_reason" not in signals and lifecycle_named:
            signals.add("lifecycle_or_existing_callback_first")

    if case_id == "GOLDEN-ARCH-001":
        role_created = any(signal in signals for signal in ("manager_created", "controller_created", "service_created"))
        if len(new_type_names) <= 1 and not role_created and not any(
            _response_mentions_role(response, suffix) for suffix in ROLE_SUFFIXES
        ):
            signals.add("single_cohesive_solution_considered")

    if case_id == "GOLDEN-DESIGN-KISS-001":
        response_has_existing_owner = "CameraDebugger" in response or "CameraDebugger" in observed_type_names
        if response_has_existing_owner and not new_type_names:
            signals.add("existing_owner_considered_first")
        if any(PROPERTY_TRACKER_RE.search(name) for name in new_type_names):
            signals.add("property_level_type_proliferation")

    if case_id == "GOLDEN-DESIGN-YAGNI-001":
        interface_detected = bool(new_interfaces) or bool(INTERFACE_MENTION_RE.search(structural_source))
        interface_proposed = bool(re.search(r"\bI[A-Z][A-Za-z0-9_]*(?:\s|`|\*)", response)) and "interface" in response.lower()
        if interface_detected or interface_proposed:
            signals.add("single_implementation_interface")
        else:
            signals.add("speculative_interface_rejected")
        if ABSTRACT_BASE_RE.search(structural_source) or ABSTRACT_BASE_RE.search(response):
            signals.add("speculative_abstract_base")
        if DEFAULT_IMPL_RE.search(structural_source) or DEFAULT_IMPL_RE.search(response):
            signals.add("default_implementation_layer")

    if case_id == "GOLDEN-DESIGN-SRP-001":
        property_tracker = any(PROPERTY_TRACKER_RE.search(name) for name in (new_type_names | observed_type_names))
        property_tracker = property_tracker or bool(PROPERTY_TRACKER_RE.search(response))
        if property_tracker:
            signals.update({"property_level_tracker_types", "srp_interpreted_as_one_property_per_class"})
        elif "CameraStateTracker" in response or "CameraDebugger" in response or "CameraStateTracker" in observed_type_names:
            signals.add("cohesive_responsibility_reviewed")

    if case_id == "GOLDEN-MUTATION-001":
        if changed_paths and allowed_paths and changed_paths.issubset(allowed_paths) and not diff_info.get("renames"):
            signals.add("bounded_patch")

    if case_id == "GOLDEN-EVIDENCE-001":
        # compile_claim_only is emitted only by derive_evidence_claims when the response claim is backed by Compile evidence.
        pass

    naming_artifact_available = any(
        str(item.get("kind", "")) == "generated_source" and str(item.get("path", "")).lower().endswith(".cs")
        for item in artifacts or []
    )
    coverage = _coverage(case, evidence_sources, naming_artifact_available)

    return {
        "signals": sorted(signals),
        "failure_types": sorted(failures),
        "findings": findings,
        "evidence_coverage": coverage,
        "structure": {
            "changed_paths": sorted(changed_paths),
            "added_paths": sorted(diff_info.get("added_paths", []) or []),
            "deleted_paths": sorted(diff_info.get("deleted_paths", []) or []),
            "renames": list(diff_info.get("renames", []) or []),
            "observed_type_names": sorted(observed_type_names),
            "new_type_names": sorted(new_type_names),
            "new_interface_names": sorted(new_interfaces),
        },
    }
