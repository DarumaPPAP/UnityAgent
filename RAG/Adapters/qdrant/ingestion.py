"""Explicit Qdrant collection setup and ingestion boundary."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote
from typing import Any

from RAG.Adapters.qdrant.collection import PAYLOAD_INDEXES, QdrantCollectionSchema, build_upsert_payload
from RAG.Adapters.qdrant.config import QdrantConfig
from RAG.Adapters.qdrant.embeddings import DenseEmbedder, SparseEncoder
from RAG.Adapters.qdrant.transport import QdrantHttpError, QdrantTransport, UrllibQdrantTransport
from RAG.Contracts.models import RetrievalCandidate


class QdrantCollectionManager:
    """Write-only operations are explicit and never run during retrieval."""

    def __init__(self, config: QdrantConfig, *, transport: QdrantTransport | None = None, schema: QdrantCollectionSchema | None = None) -> None:
        self.config = config
        self.transport = transport or UrllibQdrantTransport(config)
        self.schema = schema or QdrantCollectionSchema(
            dense_dimension=config.dense_vector_size,
            dense_vector_name=config.dense_vector_name,
            sparse_vector_name=config.sparse_vector_name,
        )

    @property
    def collection_path(self) -> str:
        return "/collections/" + quote(self.config.collection, safe="")

    def ensure_collection(self) -> dict[str, Any]:
        try:
            existing = self.transport.request("GET", self.collection_path, timeout_seconds=self.config.timeout_seconds)
            return {"created": False, "collection": existing}
        except QdrantHttpError as exc:
            if exc.status != 404:
                raise
        created = self.transport.request(
            "PUT",
            self.collection_path,
            self.schema.create_payload(),
            timeout_seconds=self.config.timeout_seconds,
        )
        return {"created": True, "collection": created}

    def ensure_payload_indexes(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index in PAYLOAD_INDEXES:
            results.append(self.transport.request(
                "PUT",
                self.collection_path + "/index",
                index,
                timeout_seconds=self.config.timeout_seconds,
            ))
        return results

    def upsert_candidates(
        self,
        candidates: Iterable[RetrievalCandidate],
        *,
        dense_embedder: DenseEmbedder,
        sparse_encoder: SparseEncoder,
        batch_size: int = 64,
    ) -> dict[str, Any]:
        values = list(candidates)
        if not values:
            return {"upserted": 0, "batches": 0}
        if int(getattr(dense_embedder, "dimension", 0)) != int(self.schema.dense_dimension):
            raise ValueError("dense embedder dimension does not match Qdrant collection schema")
        if not 1 <= int(batch_size) <= 1024:
            raise ValueError("batch_size must be 1..1024")
        collection = self.ensure_collection()
        # Qdrant recommends creating payload indexes before point ingestion so
        # filtered vector search can use them during index construction.
        indexes = self.ensure_payload_indexes()
        batches = 0
        for offset in range(0, len(values), int(batch_size)):
            batch = values[offset : offset + int(batch_size)]
            dense = [dense_embedder.embed_document(candidate.summary) for candidate in batch]
            sparse = [sparse_encoder.encode(candidate.summary) for candidate in batch]
            payload = build_upsert_payload(batch, dense, sparse, schema=self.schema)
            self.transport.request(
                "PUT",
                self.collection_path + "/points?wait=true",
                payload,
                timeout_seconds=self.config.timeout_seconds,
            )
            batches += 1
        return {
            "upserted": len(values),
            "batches": batches,
            "collection_created": bool(collection.get("created")),
            "payload_indexes": len(indexes),
            "embedding_revision": getattr(dense_embedder, "revision", "unknown"),
            "sparse_revision": getattr(sparse_encoder, "revision", "unknown"),
        }


__all__ = ["QdrantCollectionManager"]
