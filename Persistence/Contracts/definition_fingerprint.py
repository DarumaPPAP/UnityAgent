"""Runtime-light validation for the canonical DefinitionFingerprint contract."""
from __future__ import annotations
from typing import Any

from Persistence.Store.atomic_store import PersistenceError

DEFINITION_FIELDS = (
    "architecture_version",
    "policy_revision",
    "prompt_revision",
    "context_revision",
    "graph_revision",
    "runtime_profile_revision",
    "tool_schema_revision",
    "checkpoint_schema_revision",
    "evidence_schema_revision",
    "eval_contract_revision",
)
OPTIONAL_DEFINITION_FIELDS = (
    "rag_contract_revision",
    "retrieval_backend_revision",
    "retrieval_index_revision",
    "ranking_revision",
)


def validate_definition_fingerprint(value: Any, *, field: str = "definition_fingerprint") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PersistenceError("invalid_definition_fingerprint", f"{field} must be an object")
    allowed = {"schema_version", *DEFINITION_FIELDS, *OPTIONAL_DEFINITION_FIELDS}
    # Existing checkpoints and frozen baselines predate RAG. New fingerprints
    # may carry the optional RAG fields, but old durable records remain valid.
    missing = sorted(set(DEFINITION_FIELDS) - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise PersistenceError("invalid_definition_fingerprint", f"{field} missing fields: {missing}")
    if extra:
        raise PersistenceError("invalid_definition_fingerprint", f"{field} has unknown fields: {extra}")
    if value.get("schema_version") != "1.0":
        raise PersistenceError("invalid_definition_fingerprint", f"{field}.schema_version must be 1.0")
    for key in (*DEFINITION_FIELDS, *OPTIONAL_DEFINITION_FIELDS):
        if key not in value:
            continue
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise PersistenceError("invalid_definition_fingerprint", f"{field}.{key} must be a non-empty string")
    return value


def changed_definition_fields(saved: dict[str, Any], current: dict[str, Any]) -> list[str]:
    validate_definition_fingerprint(saved, field="saved_definition_fingerprint")
    validate_definition_fingerprint(current, field="current_definition_fingerprint")
    return sorted(
        key for key in (*DEFINITION_FIELDS, *OPTIONAL_DEFINITION_FIELDS)
        if saved.get(key, "") != current.get(key, "")
    )
