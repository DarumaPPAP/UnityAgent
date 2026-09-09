"""Optional Qdrant dense+sparse hybrid RetrievalBackend."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from RAG.Adapters.qdrant.collection import QdrantCollectionSchema
from RAG.Adapters.qdrant.config import QdrantConfig
from RAG.Adapters.qdrant.embeddings import BM25SparseEncoder, DenseEmbedder, HashingDenseEmbedder, SparseEncoder
from RAG.Adapters.qdrant.filters import build_qdrant_filter
from RAG.Adapters.qdrant.transport import (
    QdrantError,
    QdrantHttpError,
    QdrantTransport,
    UrllibQdrantTransport,
)
from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate, RetrievalRequest
from RAG.Retrieval.backend import BackendUnavailableError, RetrievalBackend


class QdrantBackendError(BackendUnavailableError):
    """Configured Qdrant cannot satisfy a retrieval request."""


class QdrantBackend:
    """Query Qdrant using named dense/sparse prefetches and server-side RRF.

    Fallback is opt-in. A fallback result is explicitly marked as partial in the
    service trace; it is never presented as a successful Qdrant response.
    """

    revision = "qdrant-hybrid-v1"

    def __init__(
        self,
        config: QdrantConfig,
        *,
        dense_embedder: DenseEmbedder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        transport: QdrantTransport | None = None,
        fallback: RetrievalBackend | None = None,
        allow_fallback: bool = False,
        required: bool = False,
    ) -> None:
        self.config = config
        self.schema = QdrantCollectionSchema(
            dense_dimension=config.dense_vector_size,
            dense_vector_name=config.dense_vector_name,
            sparse_vector_name=config.sparse_vector_name,
        )
        self.dense_embedder = dense_embedder or HashingDenseEmbedder(config.dense_vector_size)
        self.sparse_encoder = sparse_encoder or BM25SparseEncoder()
        self.transport = transport or UrllibQdrantTransport(config)
        self.fallback = fallback
        self.allow_fallback = bool(allow_fallback)
        self.required = bool(required)
        self.last_diagnostics: list[dict[str, Any]] = []
        self.last_fallback_used = False
        self.last_status = "uninitialized"

    def capabilities(self) -> set[str]:
        capabilities = {"dense", "sparse", "hybrid", "filtering", "rrf", "provenance"}
        if self.fallback is not None and self.allow_fallback:
            capabilities.add("fallback")
        return capabilities

    @classmethod
    def from_environment(
        cls,
        *,
        dense_embedder: DenseEmbedder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        transport: QdrantTransport | None = None,
        fallback: RetrievalBackend | None = None,
        allow_fallback: bool = False,
        required: bool = False,
    ) -> "QdrantBackend | None":
        """Return ``None`` when Qdrant is not configured at the integration boundary."""

        config = QdrantConfig.from_environment()
        if config is None:
            return None
        return cls(
            config,
            dense_embedder=dense_embedder,
            sparse_encoder=sparse_encoder,
            transport=transport,
            fallback=fallback,
            allow_fallback=allow_fallback,
            required=required,
        )

    def capability_contract(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "backend": "qdrant",
            "revision": self.revision,
            "capabilities": sorted(self.capabilities()),
            "supports_filters": True,
            "supports_provenance": True,
            "config": self.config.to_public_dict(),
        }

    @property
    def query_path(self) -> str:
        return "/collections/" + quote(self.config.collection, safe="") + "/points/query"

    def build_query_payload(self, request: RetrievalRequest) -> dict[str, Any]:
        dense = self.dense_embedder.embed_query(request.normalized_query)
        if len(dense) != int(self.schema.dense_dimension):
            raise QdrantBackendError("dense embedding dimension does not match configured collection")
        sparse = self.sparse_encoder.encode(request.normalized_query)
        payload_filter = build_qdrant_filter(request.filters)
        prefetch: list[dict[str, Any]] = [
            {
                "query": [float(value) for value in dense],
                "using": self.config.dense_vector_name,
                "limit": int(request.candidate_k),
            },
            {
                "query": sparse,
                "using": self.config.sparse_vector_name,
                "limit": int(request.candidate_k),
            },
        ]
        if payload_filter is not None:
            for item in prefetch:
                item["filter"] = payload_filter
        return {
            "prefetch": prefetch,
            "query": {"fusion": "rrf"},
            "limit": int(request.candidate_k),
            "with_payload": True,
            "with_vector": False,
        }

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        self.last_diagnostics = []
        self.last_fallback_used = False
        try:
            payload = self.build_query_payload(request)
            response = self.transport.request(
                "POST",
                self.query_path,
                payload,
                timeout_seconds=self.config.timeout_seconds,
            )
            candidates = self._parse_response(response)
            self.last_status = "ok"
            return candidates[: request.candidate_k]
        except (QdrantError, QdrantBackendError, ValueError) as exc:
            return self._fallback_or_raise(exc, request)

    def _fallback_or_raise(self, error: Exception, request: RetrievalRequest) -> list[RetrievalCandidate]:
        code = getattr(error, "code", "qdrant_unavailable")
        self.last_diagnostics.append({
            "code": "qdrant_unavailable",
            "backend": "qdrant",
            "reason_code": code,
            "message": str(error),
        })
        if self.fallback is not None and self.allow_fallback:
            self.last_fallback_used = True
            self.last_status = "fallback"
            self.last_diagnostics.append({
                "code": "backend_fallback",
                "backend": "qdrant",
                "fallback_backend": self.fallback.__class__.__name__,
                "reason_code": code,
            })
            try:
                return list(self.fallback.retrieve(request))[: request.candidate_k]
            except Exception as fallback_error:
                self.last_diagnostics.append({
                    "code": "fallback_failure",
                    "backend": self.fallback.__class__.__name__,
                    "message": str(fallback_error),
                })
                self.last_status = "blocked"
                raise QdrantBackendError("Qdrant and configured fallback were unavailable") from fallback_error
        self.last_status = "blocked" if self.required else "unavailable"
        raise QdrantBackendError("Qdrant backend is unavailable and no configured fallback was allowed") from error

    def _parse_response(self, response: Mapping[str, Any]) -> list[RetrievalCandidate]:
        raw_result = response.get("result", response)
        if isinstance(raw_result, Mapping):
            points = raw_result.get("points") or raw_result.get("result") or []
        else:
            points = raw_result
        if not isinstance(points, list):
            raise QdrantError("Qdrant query result must contain a points array")
        candidates: list[RetrievalCandidate] = []
        for point in points:
            if not isinstance(point, Mapping):
                continue
            try:
                candidates.append(self._candidate_from_point(point))
            except (TypeError, ValueError, KeyError) as exc:
                self.last_diagnostics.append({"code": "malformed_record", "message": str(exc)})
        return candidates

    def _candidate_from_point(self, point: Mapping[str, Any]) -> RetrievalCandidate:
        payload = point.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise ValueError("Qdrant point payload must be an object")
        raw_provenance = payload.get("provenance") or {}
        if not isinstance(raw_provenance, Mapping):
            raw_provenance = {}
        point_id = str(point.get("id") or "qdrant-point")
        candidate_id = str(payload.get("candidate_id") or payload.get("chunk_id") or point_id)
        document_id = str(payload.get("document_id") or raw_provenance.get("document_id") or "").strip() or None
        evidence_ids = tuple(str(value) for value in (raw_provenance.get("evidence_ids") or []) if str(value).strip())
        evidence_id = str(payload.get("evidence_id") or raw_provenance.get("evidence_id") or (evidence_ids[0] if evidence_ids else "")).strip() or None
        source_kind = str(payload.get("source_kind") or raw_provenance.get("source_kind") or "qdrant").strip()
        source_ref = str(raw_provenance.get("source_ref") or payload.get("source_ref") or f"qdrant://{self.config.collection}/{point_id}").strip()
        source_units = tuple(int(value) for value in (raw_provenance.get("source_units") or payload.get("source_units") or []) if int(value) > 0)
        provenance = CandidateProvenance(
            source_kind=source_kind,
            source_ref=source_ref,
            document_id=document_id,
            evidence_id=evidence_id,
            evidence_ids=evidence_ids,
            source_units=source_units,
            drive_file_id=str(raw_provenance.get("drive_file_id") or payload.get("drive_file_id") or "").strip() or None,
            workspace_path=str(raw_provenance.get("workspace_path") or "").strip() or None,
            original_required=bool(raw_provenance.get("original_required", payload.get("original_required", False))),
            relation_refs=tuple(str(value) for value in (raw_provenance.get("relation_refs") or []) if str(value).strip()),
        )
        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
        for key in (
            "repository", "project_id", "engine", "unity_versions", "unity_version_major",
            "render_pipelines", "pipeline_version", "platforms", "domains", "topics", "tags",
            "review_status", "confidence",
        ):
            if key in payload and key not in metadata:
                metadata[key] = payload[key]
        candidate = RetrievalCandidate(
            candidate_id=candidate_id,
            source_kind=source_kind,
            source_ref=source_ref,
            document_id=document_id,
            evidence_id=evidence_id,
            heading=str(payload.get("heading") or "evidence"),
            summary=str(payload.get("summary") or "").strip(),
            content=str(payload.get("content") or payload.get("summary") or "").strip(),
            metadata=metadata,
            provenance=provenance,
            confidence=str(payload.get("confidence") or "unverified"),
            review_status=str(payload.get("review_status") or "unverified"),
        )
        score = float(point.get("score") or 0.0)
        candidate.fusion_score = score
        candidate.semantic_score = score
        return candidate


__all__ = ["QdrantBackend", "QdrantBackendError"]
