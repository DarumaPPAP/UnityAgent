from __future__ import annotations

"""Thin client for MyResourceCenter Knowledge/RAG Service.

This module owns request construction, transport resilience, and context
materialization only.  It intentionally contains no chunking, embedding,
vector-store, reranking, or index-management code.
"""

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


KNOWLEDGE_STATUSES = frozenset({"success", "empty", "partial", "stale", "blocked", "unavailable"})
RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_IDENTITY_BODY_FIELDS = frozenset({"identity", "tenant", "roles", "permissions", "user_id", "subject", "client_id"})


class KnowledgeClientError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _string(value: Any, field_name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise KnowledgeClientError("INVALID_QUERY", f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise KnowledgeClientError("INVALID_QUERY", f"{field_name} must be a string")
    value = value.strip()
    if required and not value:
        raise KnowledgeClientError("INVALID_QUERY", f"{field_name} must not be empty")
    return value or None


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise KnowledgeClientError("INVALID_QUERY", f"{field_name} must be an array")
    result: list[str] = []
    for item in value:
        clean = _string(item, field_name, required=True)
        assert clean is not None
        if clean not in result:
            result.append(clean)
    return tuple(result)


@dataclass(frozen=True)
class KnowledgeSearchRequest:
    query: str
    scope: Mapping[str, Any] | None = None
    filters: Mapping[str, Sequence[str]] | None = None
    top_k: int = 8
    retrieval_profile: str = "agent_grounding_v1"
    include_relations: bool = False
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        query = _string(self.query, "query", required=True)
        assert query is not None
        if len(query) > 4096:
            raise KnowledgeClientError("INVALID_QUERY", "query exceeds the maximum length")
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int) or not 1 <= self.top_k <= 20:
            raise KnowledgeClientError("INVALID_TOP_K", "top_k must be an integer between 1 and 20")
        _string(self.retrieval_profile, "retrieval_profile", required=True)
        if not isinstance(self.include_relations, bool):
            raise KnowledgeClientError("INVALID_QUERY", "include_relations must be boolean")
        _string(self.correlation_id, "correlation_id")
        if self.scope is not None and not isinstance(self.scope, Mapping):
            raise KnowledgeClientError("INVALID_QUERY", "scope must be an object")
        if self.filters is not None and not isinstance(self.filters, Mapping):
            raise KnowledgeClientError("INVALID_QUERY", "filters must be an object")

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": self.query,
            "top_k": self.top_k,
            "retrieval_profile": self.retrieval_profile,
            "include_relations": self.include_relations,
        }
        if self.scope is not None:
            payload["scope"] = dict(self.scope)
        if self.filters is not None:
            payload["filters"] = {str(key): list(_string_list(value, f"filters.{key}")) for key, value in self.filters.items()}
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        if _IDENTITY_BODY_FIELDS.intersection(payload):
            raise KnowledgeClientError("FORBIDDEN_SCOPE", "identity fields must not be sent in the request body")
        return payload


@dataclass(frozen=True)
class KnowledgeCitation:
    label: str
    locator: str


@dataclass(frozen=True)
class KnowledgeProvenance:
    workspace_path: str
    evidence_id: str


@dataclass(frozen=True)
class KnowledgeResult:
    rank: int
    score: float
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_uri: str
    drive_file_id: str
    source_revision: str
    source_units: tuple[str, ...]
    citation: KnowledgeCitation
    provenance: KnowledgeProvenance
    relation_refs: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Any) -> "KnowledgeResult":
        if not isinstance(payload, Mapping):
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval result is not an object")
        citation = payload.get("citation")
        provenance = payload.get("provenance")
        if not isinstance(citation, Mapping) or not isinstance(provenance, Mapping):
            raise KnowledgeClientError("PROVENANCE_INCOMPLETE", "retrieval result has incomplete provenance")
        required = {
            "chunk_id": payload.get("chunk_id"),
            "document_id": payload.get("document_id"),
            "title": payload.get("title"),
            "content": payload.get("content"),
            "source_uri": payload.get("source_uri"),
            "drive_file_id": payload.get("drive_file_id"),
            "source_revision": payload.get("source_revision"),
            "citation.label": citation.get("label"),
            "citation.locator": citation.get("locator"),
            "provenance.workspace_path": provenance.get("workspace_path"),
            "provenance.evidence_id": provenance.get("evidence_id"),
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            raise KnowledgeClientError("PROVENANCE_INCOMPLETE", "retrieval result has incomplete provenance")
        workspace_path = str(provenance["workspace_path"])
        if not workspace_path.startswith(("sources/evidence/", "runtime/knowledge/")):
            raise KnowledgeClientError("PROVENANCE_INCOMPLETE", "retrieval result has an invalid provenance workspace")
        units = _string_list(payload.get("source_units"), "source_units")
        if not units:
            raise KnowledgeClientError("PROVENANCE_INCOMPLETE", "retrieval result has no source units")
        relation_refs = _string_list(payload.get("relation_refs"), "relation_refs")
        return cls(
            rank=int(payload.get("rank", 0)),
            score=float(payload.get("score", 0.0)),
            chunk_id=str(payload["chunk_id"]),
            document_id=str(payload["document_id"]),
            title=str(payload["title"]),
            content=str(payload["content"]),
            source_uri=str(payload["source_uri"]),
            drive_file_id=str(payload["drive_file_id"]),
            source_revision=str(payload["source_revision"]),
            source_units=units,
            citation=KnowledgeCitation(str(citation["label"]), str(citation["locator"])),
            provenance=KnowledgeProvenance(str(provenance["workspace_path"]), str(provenance["evidence_id"])),
            relation_refs=relation_refs,
        )


@dataclass(frozen=True)
class KnowledgeDiagnostics:
    backend: str
    latency_ms: int
    candidate_count: int
    returned_count: int
    filtered_count: int
    trace_id: str
    error_code: str | None = None


@dataclass(frozen=True)
class KnowledgeSearchResponse:
    status: str
    query_id: str
    index_revision: str | None
    results: tuple[KnowledgeResult, ...]
    diagnostics: KnowledgeDiagnostics
    error: Mapping[str, str] | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "KnowledgeSearchResponse":
        if not isinstance(payload, Mapping):
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval response is not an object")
        status = payload.get("status")
        if status not in KNOWLEDGE_STATUSES:
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval response has an unknown status")
        results_payload = payload.get("results", [])
        if not isinstance(results_payload, list):
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval results must be an array")
        results = tuple(KnowledgeResult.from_payload(item) for item in results_payload)
        diagnostics_payload = payload.get("diagnostics") or {}
        if not isinstance(diagnostics_payload, Mapping):
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval diagnostics are invalid")
        diagnostics = KnowledgeDiagnostics(
            backend=str(diagnostics_payload.get("backend", "unknown")),
            latency_ms=int(diagnostics_payload.get("latency_ms", 0)),
            candidate_count=int(diagnostics_payload.get("candidate_count", 0)),
            returned_count=int(diagnostics_payload.get("returned_count", len(results))),
            filtered_count=int(diagnostics_payload.get("filtered_count", 0)),
            trace_id=str(diagnostics_payload.get("trace_id", "trace-client-unknown")),
            error_code=str(diagnostics_payload["error_code"]) if diagnostics_payload.get("error_code") else None,
        )
        error = payload.get("error")
        if error is not None and not isinstance(error, Mapping):
            raise KnowledgeClientError("BACKEND_PARTIAL_FAILURE", "retrieval error payload is invalid")
        return cls(
            status=str(status),
            query_id=str(payload.get("query_id", "qry-client-unknown")),
            index_revision=str(payload["index_revision"]) if payload.get("index_revision") else None,
            results=results,
            diagnostics=diagnostics,
            error={str(key): str(value) for key, value in error.items()} if error else None,
        )


class IKnowledgeClient(Protocol):
    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        ...


@dataclass(frozen=True)
class KnowledgeClientOptions:
    base_url: str
    bearer_token: str | None = None
    timeout_seconds: float = 2.0
    max_retries: int = 1
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 5.0
    user_agent: str = "UnityAgent-KnowledgeClient/1.0"

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use HTTP or HTTPS")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("timeout_seconds must be between 0 and 60")
        if not 0 <= self.max_retries <= 3:
            raise ValueError("max_retries must be between 0 and 3")
        if self.circuit_failure_threshold < 1:
            raise ValueError("circuit_failure_threshold must be positive")


class KnowledgeHttpClient:
    def __init__(self, options: KnowledgeClientOptions, *, opener: Any = urllib.request.urlopen) -> None:
        self.options = options
        self._opener = opener
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _unavailable(self, code: str, started: float) -> KnowledgeSearchResponse:
        return KnowledgeSearchResponse(
            status="unavailable",
            query_id=f"qry-client-{uuid.uuid4().hex}",
            index_revision=None,
            results=(),
            diagnostics=KnowledgeDiagnostics(
                backend="http",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                candidate_count=0,
                returned_count=0,
                filtered_count=0,
                trace_id=f"trace-client-{uuid.uuid4().hex}",
                error_code=code,
            ),
            error={"code": code, "message": "Knowledge/RAG Service is unavailable"},
        )

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.options.circuit_failure_threshold:
            self._circuit_open_until = time.monotonic() + self.options.circuit_cooldown_seconds

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        started = time.monotonic()
        if time.monotonic() < self._circuit_open_until:
            return self._unavailable("BACKEND_TIMEOUT", started)
        payload = json.dumps(request.to_payload(), ensure_ascii=False).encode("utf-8")
        url = self.options.base_url.rstrip("/") + "/v1/knowledge/search"
        correlation_id = request.correlation_id or f"trace-client-{uuid.uuid4().hex}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.options.user_agent,
            "X-Correlation-ID": correlation_id,
        }
        if self.options.bearer_token:
            headers["Authorization"] = f"Bearer {self.options.bearer_token}"
        last_error = "INDEX_UNAVAILABLE"
        for attempt in range(self.options.max_retries + 1):
            try:
                http_request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                with self._opener(http_request, timeout=self.options.timeout_seconds) as response:
                    raw = response.read()
                parsed = KnowledgeSearchResponse.from_payload(json.loads(raw.decode("utf-8")))
                self._record_success()
                return parsed
            except urllib.error.HTTPError as error:
                last_error = "AUTH_REQUIRED" if error.code == 401 else "FORBIDDEN_SCOPE" if error.code == 403 else "RATE_LIMITED" if error.code == 429 else "BACKEND_PARTIAL_FAILURE"
                if error.code not in RETRYABLE_HTTP_STATUSES or attempt >= self.options.max_retries:
                    self._record_failure()
                    return self._unavailable(last_error, started)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KnowledgeClientError):
                last_error = "BACKEND_TIMEOUT" if attempt < self.options.max_retries else "INDEX_UNAVAILABLE"
                if attempt >= self.options.max_retries:
                    self._record_failure()
                    return self._unavailable(last_error, started)
        self._record_failure()
        return self._unavailable(last_error, started)


@dataclass(frozen=True)
class KnowledgeContextItem:
    result: KnowledgeResult
    content: str


@dataclass(frozen=True)
class KnowledgeContext:
    status: str
    index_revision: str | None
    items: tuple[KnowledgeContextItem, ...]
    citations: tuple[KnowledgeCitation, ...]
    consumed_characters: int
    trimmed_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeCitationState:
    status: str = "unavailable"
    index_revision: str | None = None
    citations: list[KnowledgeCitation] = field(default_factory=list)

    def apply(self, response: KnowledgeSearchResponse) -> None:
        self.status = response.status
        self.index_revision = response.index_revision
        self.citations = [item.citation for item in response.results]


class KnowledgeContextAssembler:
    """Place returned evidence into Context without re-ranking or re-searching."""

    def __init__(self, max_characters: int = 12000) -> None:
        if max_characters < 1:
            raise ValueError("max_characters must be positive")
        self.max_characters = max_characters

    def assemble(self, response: KnowledgeSearchResponse) -> KnowledgeContext:
        if response.status not in {"success", "partial", "stale"}:
            return KnowledgeContext(
                status=response.status,
                index_revision=response.index_revision,
                items=(),
                citations=(),
                consumed_characters=0,
                trimmed_count=0,
                diagnostics={"error": dict(response.error or {})},
            )

        selected: list[KnowledgeContextItem] = []
        citations: list[KnowledgeCitation] = []
        seen_source_units: set[tuple[str, tuple[str, ...]]] = set()
        consumed = 0
        trimmed = 0
        for result in sorted(response.results, key=lambda item: (item.rank, -item.score, item.document_id, item.chunk_id)):
            signature = (result.document_id, result.source_units)
            if signature in seen_source_units:
                trimmed += 1
                continue
            seen_source_units.add(signature)
            remaining = self.max_characters - consumed
            if remaining <= 0:
                trimmed += 1
                continue
            content = result.content[:remaining]
            if not content:
                trimmed += 1
                continue
            selected.append(KnowledgeContextItem(result=result, content=content))
            citations.append(result.citation)
            consumed += len(content)
            if len(content) < len(result.content):
                trimmed += 1

        return KnowledgeContext(
            status=response.status,
            index_revision=response.index_revision,
            items=tuple(selected),
            citations=tuple(citations),
            consumed_characters=consumed,
            trimmed_count=trimmed,
            diagnostics={"error": dict(response.error or {})},
        )
