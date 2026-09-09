"""Compatibility entrypoint for the optional Qdrant backend."""

from RAG.Adapters.qdrant.adapter import QdrantAdapter, QdrantBackend, QdrantBackendError

__all__ = ["QdrantAdapter", "QdrantBackend", "QdrantBackendError"]
