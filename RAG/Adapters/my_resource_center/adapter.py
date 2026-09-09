"""Normalize MyResourceCenter Search Index chunks into RAG candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate
from RAG.Adapters.my_resource_center.search_index_reader import (
    SearchIndexError,
    SearchIndexSnapshot,
    read_search_index,
)


@dataclass(frozen=True)
class AdapterLoadResult:
    candidates: tuple[RetrievalCandidate, ...]
    source_id: str
    source_revision: str | None
    diagnostics: tuple[dict[str, str], ...]


def _list_of_strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value is None else [value])
    return [str(item).strip() for item in values if str(item).strip()]


def _positive_ints(value: Any) -> tuple[int, ...]:
    values = value if isinstance(value, list) else ([] if value is None else [value])
    result: list[int] = []
    for item in values:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in result:
            result.append(number)
    return tuple(result)


def _confidence(chunk: dict[str, Any]) -> str:
    raw = str(chunk.get("confidence") or chunk.get("reviewStatus") or "unverified").casefold()
    return {
        "high": "verified",
        "reviewed": "reviewed",
        "verified": "verified",
        "medium": "probable",
        "probable": "probable",
    }.get(raw, "unverified")


class MyResourceCenterAdapter:
    """Read-only adapter; it never regenerates or mutates MyResourceCenter data."""

    source_id = "my_resource_center"

    def __init__(self, index_path: str | Path, *, expected_revision: str | None = None) -> None:
        self.index_path = Path(index_path)
        self.expected_revision = None if expected_revision is None else str(expected_revision).strip() or None
        self.last_revision: str | None = None

    def load(self) -> AdapterLoadResult:
        try:
            snapshot = read_search_index(self.index_path)
        except SearchIndexError as exc:
            return AdapterLoadResult(
                candidates=(),
                source_id=self.source_id,
                source_revision=None,
                diagnostics=({"code": exc.code, "message": str(exc)},),
            )
        self.last_revision = snapshot.revision
        diagnostic_list = [
            {"code": item["code"], "message": item["message"]}
            for item in snapshot.diagnostics
        ]
        if self.expected_revision and self.expected_revision != snapshot.revision:
            diagnostic_list.append({
                "code": "index_stale",
                "message": "Search Index revision does not match the requested revision",
                "expected_revision": self.expected_revision,
                "actual_revision": snapshot.revision,
            })
        candidates_list: list[RetrievalCandidate] = []
        for index, chunk in enumerate(snapshot.chunks):
            try:
                candidates_list.append(self._candidate(chunk))
            except (TypeError, ValueError, KeyError) as exc:
                diagnostic_list.append({
                    "code": "malformed_record",
                    "message": f"chunks[{index}] cannot be normalized: {exc}",
                })
        return AdapterLoadResult(
            candidates=tuple(candidates_list),
            source_id=self.source_id,
            source_revision=snapshot.revision,
            diagnostics=tuple(diagnostic_list),
        )

    def candidates(self) -> list[RetrievalCandidate]:
        return list(self.load().candidates)

    @staticmethod
    def _candidate(chunk: dict[str, Any]) -> RetrievalCandidate:
        chunk_id = str(chunk["chunkId"])
        document_id = str(chunk["documentId"])
        evidence_ids = _list_of_strings(chunk.get("evidence"))
        evidence_id = evidence_ids[0] if evidence_ids else None
        source_ref_tail = evidence_id or chunk_id
        source_ref = f"mrc://evidence/{document_id}/{source_ref_tail}"
        workspace_path = str(chunk.get("workspacePath") or "").strip() or None
        source_units = _positive_ints(chunk.get("sourceUnits"))
        metadata = {
            "repository": "DarumaPPAP/MyResourceCenter",
            "document_id": document_id,
            "project_id": str(chunk.get("projectId") or chunk.get("project_id") or "").strip() or None,
            "engine": str(chunk.get("engine") or "").strip() or None,
            "domains": _list_of_strings(chunk.get("domains")),
            "topics": _list_of_strings(chunk.get("topics")),
            "tags": _list_of_strings(chunk.get("tags")),
            "unity_versions": _list_of_strings(chunk.get("unityVersions", chunk.get("unity_versions"))),
            "render_pipelines": _list_of_strings(chunk.get("renderPipelines", chunk.get("render_pipelines"))),
            "pipeline_version": str(chunk.get("pipelineVersion") or chunk.get("pipeline_version") or "").strip() or None,
            "platforms": _list_of_strings(chunk.get("platforms")),
            "review_status": str(chunk.get("reviewStatus") or "unverified"),
            "source_revision": str(chunk.get("sourceRevision") or "") or None,
        }
        provenance = CandidateProvenance(
            source_kind="my_resource_center",
            source_ref=source_ref,
            document_id=document_id,
            evidence_id=evidence_id,
            evidence_ids=tuple(evidence_ids),
            source_units=source_units,
            drive_file_id=str(chunk.get("driveFileId") or "").strip() or None,
            workspace_path=workspace_path,
            original_required=bool(chunk.get("originalRequired", chunk.get("original_required", False))),
        )
        return RetrievalCandidate(
            candidate_id=chunk_id,
            source_kind="my_resource_center",
            source_ref=source_ref,
            document_id=document_id,
            evidence_id=evidence_id,
            heading=str(chunk.get("heading") or "evidence"),
            summary=str(chunk.get("summary") or "").strip(),
            content=str(chunk.get("content") or chunk.get("summary") or "").strip(),
            metadata=metadata,
            provenance=provenance,
            confidence=_confidence(chunk),
            review_status=str(chunk.get("reviewStatus") or "unverified"),
        )
