"""Configuration for the optional Qdrant adapter.

Configuration is deliberately environment-driven.  ``to_public_dict`` never
returns the API key, so traces and diagnostics can safely include it.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from urllib.parse import urlparse


_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")


class QdrantConfigurationError(ValueError):
    """Qdrant configuration is missing or unsafe."""


@dataclass(frozen=True)
class QdrantConfig:
    url: str
    collection: str
    api_key: str | None = None
    timeout_seconds: float = 10.0
    dense_vector_size: int = 384
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "sparse"
    embedding_model: str = "unconfigured"

    def __post_init__(self) -> None:
        url = str(self.url).strip().rstrip("/")
        collection = str(self.collection).strip()
        dense_name = str(self.dense_vector_name).strip()
        sparse_name = str(self.sparse_vector_name).strip()
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "collection", collection)
        object.__setattr__(self, "dense_vector_name", dense_name)
        object.__setattr__(self, "sparse_vector_name", sparse_name)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise QdrantConfigurationError("Qdrant URL must be an absolute http(s) URL")
        if not _COLLECTION_RE.fullmatch(collection):
            raise QdrantConfigurationError("Qdrant collection contains an unsafe character")
        if not 0.1 <= float(self.timeout_seconds) <= 120.0:
            raise QdrantConfigurationError("Qdrant timeout_seconds must be 0.1..120")
        if not 1 <= int(self.dense_vector_size) <= 65_536:
            raise QdrantConfigurationError("dense_vector_size must be 1..65536")
        if not dense_name or not sparse_name:
            raise QdrantConfigurationError("named vectors must be non-empty")
        if self.api_key is not None and not str(self.api_key).strip():
            raise QdrantConfigurationError("api_key cannot be blank")

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "QdrantConfig | None":
        values = environ if environ is not None else os.environ
        url = values.get("UNITYAGENT_QDRANT_URL") or values.get("QDRANT_URL")
        collection = values.get("UNITYAGENT_QDRANT_COLLECTION") or values.get("QDRANT_COLLECTION")
        if not url and not collection:
            return None
        if not url or not collection:
            raise QdrantConfigurationError(
                "UNITYAGENT_QDRANT_URL and UNITYAGENT_QDRANT_COLLECTION must be configured together"
            )
        raw_size = values.get("UNITYAGENT_QDRANT_DENSE_VECTOR_SIZE") or values.get("QDRANT_DENSE_VECTOR_SIZE") or "384"
        try:
            vector_size = int(raw_size)
        except ValueError as exc:
            raise QdrantConfigurationError("Qdrant dense vector size must be an integer") from exc
        try:
            timeout_seconds = float(
                values.get("UNITYAGENT_QDRANT_TIMEOUT_SECONDS")
                or values.get("QDRANT_TIMEOUT_SECONDS")
                or "10"
            )
        except (TypeError, ValueError) as exc:
            raise QdrantConfigurationError("Qdrant timeout_seconds must be a number") from exc
        return cls(
            url=url,
            collection=collection,
            api_key=values.get("UNITYAGENT_QDRANT_API_KEY") or values.get("QDRANT_API_KEY"),
            timeout_seconds=timeout_seconds,
            dense_vector_size=vector_size,
            dense_vector_name=(
                values.get("UNITYAGENT_QDRANT_DENSE_VECTOR_NAME")
                or values.get("QDRANT_DENSE_VECTOR_NAME")
                or "dense"
            ),
            sparse_vector_name=(
                values.get("UNITYAGENT_QDRANT_SPARSE_VECTOR_NAME")
                or values.get("QDRANT_SPARSE_VECTOR_NAME")
                or "sparse"
            ),
            embedding_model=(
                values.get("UNITYAGENT_QDRANT_EMBEDDING_MODEL")
                or values.get("QDRANT_EMBEDDING_MODEL")
                or "unconfigured"
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "collection": self.collection,
            "api_key_configured": bool(self.api_key),
            "timeout_seconds": float(self.timeout_seconds),
            "dense_vector_size": int(self.dense_vector_size),
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
            "embedding_model": self.embedding_model,
        }


__all__ = ["QdrantConfig", "QdrantConfigurationError"]
