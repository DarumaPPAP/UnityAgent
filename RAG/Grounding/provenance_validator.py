"""Fail-closed validation for provenance that crosses the RAG boundary."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from RAG.Contracts.models import CandidateProvenance


class ProvenanceError(ValueError):
    """A candidate cannot be grounded because its source identity is incomplete."""

    def __init__(self, message: str, *, code: str = "provenance_invalid") -> None:
        super().__init__(message)
        self.code = code


_URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]+$")


def validate_provenance(value: CandidateProvenance | Mapping[str, Any]) -> CandidateProvenance:
    """Normalize and validate provenance without resolving or fetching originals."""

    if isinstance(value, CandidateProvenance):
        provenance = value
    elif isinstance(value, Mapping):
        raw_units = value.get("source_units", ())
        raw_evidence = value.get("evidence_ids", ())
        try:
            provenance = CandidateProvenance(
                source_kind=str(value.get("source_kind") or ""),
                source_ref=str(value.get("source_ref") or ""),
                document_id=value.get("document_id"),
                evidence_id=value.get("evidence_id"),
                evidence_ids=tuple(str(item) for item in (raw_evidence or ())),
                source_units=tuple(int(item) for item in (raw_units or ())),
                drive_file_id=value.get("drive_file_id"),
                workspace_path=value.get("workspace_path"),
                original_required=bool(value.get("original_required", False)),
            )
        except (TypeError, ValueError) as exc:
            raise ProvenanceError(str(exc)) from exc
    else:
        raise ProvenanceError("provenance must be an object")

    if not _URI_RE.fullmatch(provenance.source_ref):
        raise ProvenanceError("provenance.source_ref must be a non-empty URI")
    if ".." in provenance.source_ref.split("?", 1)[0].split("/"):
        raise ProvenanceError("provenance.source_ref must not traverse parent directories")
    if provenance.workspace_path and any(
        part in {"", ".", ".."} for part in str(provenance.workspace_path).replace("\\", "/").split("/")
    ):
        raise ProvenanceError("provenance.workspace_path must be a relative canonical path")
    if not provenance.has_identity:
        raise ProvenanceError(
            "provenance requires document/evidence/source-unit identity",
            code="provenance_missing",
        )
    if provenance.original_required and not (provenance.drive_file_id or provenance.workspace_path):
        raise ProvenanceError(
            "original_required provenance needs drive_file_id or workspace_path",
            code="blocked_original_unreadable",
        )
    return provenance
