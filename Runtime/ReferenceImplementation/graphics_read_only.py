"""Graphics PilotのRead-only結果をfixture境界で検証する。Runtime実測の代用にはしない。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class GraphicsPilotContractError(ValueError):
    pass


REQUIRED_FIELDS = frozenset({"status", "profile_id", "capability", "confirmed_facts", "hypotheses", "rejected_hypotheses", "required_observations", "proposed_diff", "required_approval", "observed_evidence", "evidence_level", "known_limitations", "received_context_id", "received_context_fingerprint", "runtime_evaluation"})
CAPABILITIES = frozenset({"graphics.inspect", "graphics.diagnose", "graphics.validate"})


def verify_graphics_read_only(manifest: Mapping[str, Any], transported: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Generated → Transported → Receivedと静的Evidenceの整合を確認する。"""
    view = manifest.get("materialized_context")
    if not isinstance(view, Mapping) or not isinstance(view.get("specialist_context"), Mapping):
        raise GraphicsPilotContractError("Graphics Specialist Context is missing")
    specialist = view["specialist_context"]
    if specialist.get("profile_id") != "graphics_subagent" or specialist.get("capability") not in CAPABILITIES:
        raise GraphicsPilotContractError("Graphics Specialist identity or capability is invalid")
    expected = (view.get("context_id"), (view.get("context_fingerprint") or {}).get("value"))
    if not all(isinstance(value, str) and value for value in expected):
        raise GraphicsPilotContractError("generated Context identity is invalid")
    if transported.get("context_id") != expected[0] or transported.get("context_fingerprint") != expected[1] or transported.get("specialist_context") != specialist:
        raise GraphicsPilotContractError("transported Specialist Context does not match generated Context")
    if not isinstance(result, Mapping) or set(result) != REQUIRED_FIELDS:
        raise GraphicsPilotContractError("Graphics result fields are not exact")
    if (result["received_context_id"], result["received_context_fingerprint"]) != expected:
        raise GraphicsPilotContractError("received Specialist Context identity does not match generated Context")
    if result["profile_id"] != "graphics_subagent" or result["capability"] != specialist["capability"]:
        raise GraphicsPilotContractError("Graphics result identity or capability is invalid")
    if result["status"] != "completed" or result["runtime_evaluation"] != "NOT_EVALUATED_RUNTIME" or result["evidence_level"] != "static":
        raise GraphicsPilotContractError("Pilot cannot claim runtime verification or a completed unavailable result")
    for field in ("confirmed_facts", "hypotheses", "rejected_hypotheses", "required_observations", "observed_evidence", "known_limitations"):
        if not isinstance(result[field], list):
            raise GraphicsPilotContractError(f"{field} must be a list")
    if not result["observed_evidence"]:
        raise GraphicsPilotContractError("static Graphics evidence is required")
    for item in result["observed_evidence"]:
        valid_shape = isinstance(item, Mapping) and set(item) == {"type", "source_ref", "observation"}
        if not valid_shape or not isinstance(item["type"], str) or item["type"] not in {"project_fact", "source_read", "static_review", "graphics_diagnosis"} or not isinstance(item["source_ref"], str) or not item["source_ref"] or not isinstance(item["observation"], str) or not item["observation"]:
            raise GraphicsPilotContractError("static Graphics evidence requires a type, source, and observation")
    if not any(item["type"] == "graphics_diagnosis" for item in result["observed_evidence"]):
        raise GraphicsPilotContractError("graphics_diagnosis evidence is required")
    if result["proposed_diff"] is not None and not isinstance(result["proposed_diff"], str):
        raise GraphicsPilotContractError("proposed_diff must be text or absent")
    if result["required_approval"] not in {"none", "required_before_apply"}:
        raise GraphicsPilotContractError("approval state is invalid")
    if result["proposed_diff"] is not None and result["required_approval"] != "required_before_apply":
        raise GraphicsPilotContractError("proposed changes require approval before apply")
    return {"status": "fixture_contract_verified", "receipt_integrity": "verified", "runtime_evaluation": "NOT_EVALUATED_RUNTIME", "evidence_level": "static"}
