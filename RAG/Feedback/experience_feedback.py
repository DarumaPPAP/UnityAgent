"""Build auditable Memory promotion proposals from verified evaluation output.

This module is deliberately proposal-only. It does not import Persistence and it
does not write Memory; the canonical write boundary is implemented by
``Persistence.Memory.promotion_writer``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Any

from RAG.Contracts.models import deterministic_id


_PASS_VALUES = {"pass", "passed", "success", "verified"}
_SCOPE_VALUES = {"project_internal", "portable_artifact", "public_reference"}
_TARGET_VALUES = {"none", "execution_reference", "unityagent_knowledge", "user_policy_candidate"}
_REVIEW_VALUES = {"pending", "approved", "rejected", "not_required"}


def _strings(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _query_fingerprint(query: str) -> str:
    return "sha256:" + hashlib.sha256(" ".join(query.casefold().split()).encode("utf-8")).hexdigest()


def _evaluation_case(eval_result: Mapping[str, Any], case_id: str | None) -> Mapping[str, Any] | None:
    selected = str(case_id or "").strip()
    cases = eval_result.get("cases")
    if not selected or not isinstance(cases, list):
        return None
    for case in cases:
        if isinstance(case, Mapping) and str(case.get("case_id") or case.get("id") or "") == selected:
            return case
    return None


@dataclass(frozen=True)
class ExperienceFeedback:
    """Immutable proposal data that can be reviewed before durable promotion."""

    feedback_id: str
    proposal_id: str
    evaluation_run_id: str
    evaluation_case_id: str
    evaluation_decision: str
    query: str
    statement: str
    source_evidence_refs: tuple[str, ...]
    source_memory_refs: tuple[str, ...] = ()
    source_revision: str = "unbound"
    query_fingerprint: str = ""
    verification_status: str = "passed"
    applicability: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    scope_class: str = "portable_artifact"
    promotion_target: str = "execution_reference"
    review_status: str = "pending"
    supersedes: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    evaluation_metrics: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    definition_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.source_evidence_refs:
            raise ValueError("source_evidence_refs must not be empty")
        if self.evaluation_decision.casefold() not in _PASS_VALUES:
            raise ValueError("only passed evaluation output can produce a promotion proposal")
        if self.scope_class not in _SCOPE_VALUES:
            raise ValueError(f"unsupported scope_class: {self.scope_class}")
        if self.promotion_target not in _TARGET_VALUES:
            raise ValueError(f"unsupported promotion_target: {self.promotion_target}")
        if self.review_status not in _REVIEW_VALUES:
            raise ValueError(f"unsupported review_status: {self.review_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "kind": "rag_promotion_proposal",
            "feedback_id": self.feedback_id,
            "proposal_id": self.proposal_id,
            "evaluation_run_id": self.evaluation_run_id,
            "evaluation_case_id": self.evaluation_case_id,
            "evaluation_decision": self.evaluation_decision,
            "verification_status": self.verification_status,
            "query": self.query,
            "query_fingerprint": self.query_fingerprint,
            "statement": self.statement,
            "source_evidence_refs": list(self.source_evidence_refs),
            "source_memory_refs": list(self.source_memory_refs),
            "source_revision": self.source_revision,
            "applicability": list(self.applicability),
            "limits": list(self.limits),
            "scope_class": self.scope_class,
            "promotion_target": self.promotion_target,
            "review_status": self.review_status,
            "supersedes": list(self.supersedes),
            "conflicts_with": list(self.conflicts_with),
            "evaluation_metrics": dict(self.evaluation_metrics),
            "created_at": self.created_at,
            "definition_fingerprint": self.definition_fingerprint,
        }


def build_promotion_proposal(
    eval_result: Mapping[str, Any],
    *,
    statement: str,
    source_evidence_refs: Iterable[Any],
    source_revision: str,
    evaluation_case_id: str | None = None,
    query: str | None = None,
    source_memory_refs: Iterable[Any] = (),
    applicability: Iterable[Any] = (),
    limits: Iterable[Any] = (),
    scope_class: str = "portable_artifact",
    promotion_target: str = "execution_reference",
    review_status: str = "pending",
    supersedes: Iterable[Any] = (),
    conflicts_with: Iterable[Any] = (),
    definition_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Create a stable proposal only when the supplied evaluation passed."""

    if not isinstance(eval_result, Mapping):
        raise TypeError("eval_result must be a mapping")
    evaluation_decision = _required_text(eval_result.get("decision") or eval_result.get("status"), "eval_result.decision")
    if evaluation_decision.casefold() not in _PASS_VALUES:
        raise ValueError("only PASS evaluation results may be promoted")
    evaluation_run_id = _required_text(
        eval_result.get("run_id") or eval_result.get("evaluation_run_id"),
        "evaluation_run_id",
    )
    selected_case_id = str(evaluation_case_id or eval_result.get("case_id") or "run").strip()
    selected_query = str(query or eval_result.get("query") or "").strip()
    case = _evaluation_case(eval_result, selected_case_id)
    if not selected_query and case is not None:
        selected_query = str(case.get("query") or "").strip()
    selected_query = _required_text(selected_query, "query")
    selected_statement = _required_text(statement, "statement")
    evidence_refs = _strings(source_evidence_refs)
    if not evidence_refs:
        raise ValueError("source_evidence_refs must not be empty")
    revision = _required_text(source_revision, "source_revision")
    created_at = str(eval_result.get("generated_at") or datetime.now(timezone.utc).isoformat())
    fingerprint = _query_fingerprint(selected_query)
    proposal_id = deterministic_id(
        "proposal",
        evaluation_run_id,
        selected_case_id,
        selected_statement,
        evidence_refs,
        revision,
    )
    feedback = ExperienceFeedback(
        feedback_id=deterministic_id("feedback", proposal_id),
        proposal_id=proposal_id,
        evaluation_run_id=evaluation_run_id,
        evaluation_case_id=selected_case_id,
        evaluation_decision=evaluation_decision.upper(),
        query=selected_query,
        statement=selected_statement,
        source_evidence_refs=evidence_refs,
        source_memory_refs=_strings(source_memory_refs),
        source_revision=revision,
        query_fingerprint=fingerprint,
        verification_status="passed",
        applicability=_strings(applicability),
        limits=_strings(limits),
        scope_class=scope_class,
        promotion_target=promotion_target,
        review_status=review_status,
        supersedes=_strings(supersedes),
        conflicts_with=_strings(conflicts_with),
        evaluation_metrics=dict(eval_result.get("metrics") or (case or {}).get("metrics") or {}),
        created_at=created_at,
        definition_fingerprint=definition_fingerprint,
    )
    return feedback.to_dict()


__all__ = ["ExperienceFeedback", "build_promotion_proposal"]
