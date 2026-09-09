"""Compatibility entrypoint for Qdrant collection schema helpers."""

from RAG.Adapters.qdrant.collection import (
    PAYLOAD_INDEXES,
    QdrantCollectionSchema,
    build_collection_create_payload,
    build_point_payload,
    build_upsert_payload,
    point_id_for_candidate,
)

__all__ = [
    "PAYLOAD_INDEXES",
    "QdrantCollectionSchema",
    "build_collection_create_payload",
    "build_point_payload",
    "build_upsert_payload",
    "point_id_for_candidate",
]
