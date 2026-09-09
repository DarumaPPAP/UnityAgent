"""Optional Qdrant adapter and explicit collection-management boundary.

The rest of RAG depends only on ``RetrievalBackend``.  Qdrant-specific HTTP
payloads, vector names, and authentication stay inside this package.
"""

from RAG.Adapters.qdrant.adapter import QdrantBackend, QdrantBackendError
from RAG.Adapters.qdrant.collection import (
    QdrantCollectionSchema,
    build_collection_create_payload,
    build_point_payload,
    build_upsert_payload,
    point_id_for_candidate,
)
from RAG.Adapters.qdrant.config import QdrantConfig, QdrantConfigurationError
from RAG.Adapters.qdrant.embeddings import (
    BM25SparseEncoder,
    DenseEmbedder,
    HashingDenseEmbedder,
    SparseEncoder,
)
from RAG.Adapters.qdrant.filters import build_qdrant_filter
from RAG.Adapters.qdrant.ingestion import QdrantCollectionManager
from RAG.Adapters.qdrant.transport import (
    QdrantError,
    QdrantHttpError,
    QdrantTransport,
    UrllibQdrantTransport,
)

__all__ = [
    "BM25SparseEncoder",
    "DenseEmbedder",
    "HashingDenseEmbedder",
    "QdrantBackend",
    "QdrantBackendError",
    "QdrantCollectionManager",
    "QdrantCollectionSchema",
    "QdrantConfig",
    "QdrantConfigurationError",
    "QdrantError",
    "QdrantHttpError",
    "QdrantTransport",
    "SparseEncoder",
    "UrllibQdrantTransport",
    "build_collection_create_payload",
    "build_point_payload",
    "build_qdrant_filter",
    "build_upsert_payload",
    "point_id_for_candidate",
]
