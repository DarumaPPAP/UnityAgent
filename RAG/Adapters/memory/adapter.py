"""Project Memory → RAG candidate projection.

Persistence remains the only owner of durable Memory. This adapter only calls its read
API and never invokes put/promote or writes a projection cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Persistence.Memory.memory_store import MemoryStore
from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate


@dataclass(frozen=True)
class MemoryLoadResult:
    candidates: tuple[RetrievalCandidate, ...]
    source_id: str
    source_revision: str | None
    diagnostics: tuple[dict[str, str], ...]


class MemoryAdapter:
    source_id = "project_memory"

    def __init__(self, store_root: str | Path, execution_profile: str) -> None:
        self.store_root = Path(store_root)
        self.execution_profile = execution_profile

    def load(self) -> MemoryLoadResult:
        try:
            records = MemoryStore(self.store_root).list_accessible(self.execution_profile)
        except Exception as exc:  # Persistence exposes typed errors; adapter reports source health.
            return MemoryLoadResult((), self.source_id, None, ({"code": "source_unavailable", "message": str(exc)},))
        candidates: list[RetrievalCandidate] = []
        diagnostics: list[dict[str, str]] = []
        for index, record in enumerate(records):
            try:
                candidates.append(self._candidate(record))
            except (TypeError, ValueError, KeyError) as exc:
                diagnostics.append({
                    "code": "malformed_record",
                    "message": f"memory record {index} cannot be normalized: {exc}",
                })
        return MemoryLoadResult(tuple(candidates), self.source_id, None, tuple(diagnostics))

    def candidates(self) -> list[RetrievalCandidate]:
        return list(self.load().candidates)

    @staticmethod
    def _candidate(record: dict[str, Any]) -> RetrievalCandidate:
        memory_id = str(record["memory_id"])
        evidence_refs = [str(item) for item in record.get("source_evidence_refs", []) if str(item).strip()]
        evidence_id = evidence_refs[0] if evidence_refs else None
        source_ref = f"persistence://memory/{memory_id}"
        metadata = {
            "repository": record.get("repository"),
            "project_id": record.get("project_id"),
            "unity_version": record.get("unity_version"),
            "platform": record.get("platform"),
            "domains": list(record.get("applicability") or []),
            "tags": list(record.get("tags") or []),
            "limits": list(record.get("limits") or []),
            "scope_class": record.get("scope_class"),
            "layer": record.get("layer"),
            "review_status": record.get("review_status"),
        }
        provenance = CandidateProvenance(
            source_kind="project_memory",
            source_ref=source_ref,
            document_id=memory_id,
            evidence_id=evidence_id,
            evidence_ids=tuple(evidence_refs),
        )
        confidence = str(record.get("confidence") or "unverified")
        return RetrievalCandidate(
            candidate_id=memory_id,
            source_kind="project_memory",
            source_ref=source_ref,
            document_id=memory_id,
            evidence_id=evidence_id,
            heading="memory",
            summary=str(record["statement"]),
            content=str(record["statement"]),
            metadata=metadata,
            provenance=provenance,
            confidence=confidence if confidence in {"verified", "probable", "unverified"} else "unverified",
            review_status=str(record.get("review_status") or "not_required"),
        )
