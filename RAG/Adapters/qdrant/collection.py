"""Qdrant collection schema and candidate payload mapping."""

from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any

from RAG.Contracts.models import RetrievalCandidate


@dataclass(frozen=True)
class QdrantCollectionSchema:
    dense_dimension: int = 384
    distance: str = "Cosine"
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "sparse"
    on_disk_payload: bool = True

    def __post_init__(self) -> None:
        if not 1 <= int(self.dense_dimension) <= 65_536:
            raise ValueError("Qdrant dense_dimension must be 1..65536")
        if self.distance not in {"Cosine", "Dot", "Euclid", "Manhattan"}:
            raise ValueError("unsupported Qdrant distance")

    def create_payload(self) -> dict[str, Any]:
        return build_collection_create_payload(self)


PAYLOAD_INDEXES: tuple[dict[str, str], ...] = (
    {"field_name": "repository", "field_schema": "keyword"},
    {"field_name": "project_id", "field_schema": "keyword"},
    {"field_name": "engine", "field_schema": "keyword"},
    {"field_name": "unity_version_major", "field_schema": "keyword"},
    {"field_name": "unity_versions", "field_schema": "keyword"},
    {"field_name": "render_pipelines", "field_schema": "keyword"},
    {"field_name": "pipeline_version", "field_schema": "keyword"},
    {"field_name": "platforms", "field_schema": "keyword"},
    {"field_name": "domains", "field_schema": "keyword"},
    {"field_name": "topics", "field_schema": "keyword"},
    {"field_name": "tags", "field_schema": "keyword"},
    {"field_name": "source_kind", "field_schema": "keyword"},
    {"field_name": "document_id", "field_schema": "keyword"},
    {"field_name": "review_status", "field_schema": "keyword"},
    {"field_name": "confidence", "field_schema": "keyword"},
)


def _metadata_values(metadata: dict[str, Any], plural: str, singular: str) -> list[Any]:
    """Normalize scalar/list metadata before it is serialized to Qdrant."""

    value = metadata.get(plural)
    if value is None or value == []:
        value = metadata.get(singular)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def build_collection_create_payload(schema: QdrantCollectionSchema) -> dict[str, Any]:
    return {
        "vectors": {
            schema.dense_vector_name: {
                "size": int(schema.dense_dimension),
                "distance": schema.distance,
            }
        },
        "sparse_vectors": {
            schema.sparse_vector_name: {
                "index": {"on_disk": True},
            }
        },
        "on_disk_payload": bool(schema.on_disk_payload),
    }


def point_id_for_candidate(candidate: RetrievalCandidate) -> str:
    """Qdrant-compatible deterministic UUID for a source-qualified candidate."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, candidate.source_ref or candidate.candidate_id))


def build_point_payload(candidate: RetrievalCandidate) -> dict[str, Any]:
    metadata = dict(candidate.metadata or {})
    provenance = candidate.provenance.to_dict()
    unity_versions = [str(value) for value in _metadata_values(metadata, "unity_versions", "unity_version")]
    unity_version_major = sorted({str(value).split(".", 1)[0] for value in unity_versions if str(value).strip()})
    # Only summary/provenance metadata is sent. Canonical originals remain in
    # MyResourceCenter / Google Drive and are never copied into the vector DB.
    return {
        "candidate_id": candidate.candidate_id,
        "chunk_id": candidate.candidate_id,
        "document_id": candidate.document_id or provenance.get("document_id"),
        "evidence_id": candidate.evidence_id or provenance.get("evidence_id"),
        "heading": candidate.heading,
        "summary": candidate.summary,
        "domains": _metadata_values(metadata, "domains", "domain"),
        "topics": _metadata_values(metadata, "topics", "topic"),
        "tags": _metadata_values(metadata, "tags", "tag"),
        "unity_versions": unity_versions,
        "unity_version_major": unity_version_major,
        "render_pipelines": _metadata_values(metadata, "render_pipelines", "render_pipeline"),
        "pipeline_version": metadata.get("pipeline_version"),
        "platforms": _metadata_values(metadata, "platforms", "platform"),
        "repository": metadata.get("repository"),
        "project_id": metadata.get("project_id"),
        "engine": metadata.get("engine"),
        "source_kind": candidate.source_kind,
        "drive_file_id": provenance.get("drive_file_id"),
        "source_units": list(provenance.get("source_units") or []),
        "review_status": candidate.review_status,
        "confidence": candidate.confidence,
        "original_required": bool(provenance.get("original_required", False)),
        "provenance": provenance,
    }


def build_upsert_payload(
    candidates: list[RetrievalCandidate] | tuple[RetrievalCandidate, ...],
    dense_vectors: list[list[float]],
    sparse_vectors: list[dict[str, list[float] | list[int]]],
    *,
    schema: QdrantCollectionSchema | None = None,
) -> dict[str, Any]:
    selected_schema = schema or QdrantCollectionSchema()
    if not len(candidates) == len(dense_vectors) == len(sparse_vectors):
        raise ValueError("candidate and vector counts must match")
    points: list[dict[str, Any]] = []
    for candidate, dense, sparse in zip(candidates, dense_vectors, sparse_vectors):
        if len(dense) != int(selected_schema.dense_dimension):
            raise ValueError(f"dense vector dimension mismatch for {candidate.candidate_id}")
        points.append({
            "id": point_id_for_candidate(candidate),
            "vector": {
                selected_schema.dense_vector_name: [float(value) for value in dense],
                selected_schema.sparse_vector_name: sparse,
            },
            "payload": build_point_payload(candidate),
        })
    return {"points": points}


__all__ = [
    "PAYLOAD_INDEXES",
    "QdrantCollectionSchema",
    "build_collection_create_payload",
    "build_point_payload",
    "build_upsert_payload",
    "point_id_for_candidate",
]
