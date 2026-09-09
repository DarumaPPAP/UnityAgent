"""RAG の Runtime で共有する型付き Contract。

YAML Schema は機械検証用、このファイルは Python 実装間の境界用である。どちらか一方
だけを正本にせず、シリアライズ結果が Schema の形を保つように実装する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
DEFAULT_TOP_K = 8
DEFAULT_CANDIDATE_K = 24
DEFAULT_MAX_CHARS = 6000
MAX_TOP_K = 20
MAX_CANDIDATE_K = 200
MAX_CONTEXT_CHARS = 100_000
ALLOWED_EXECUTION_PROFILES = {
    "generic_planning",
    "personal_full_control",
    "team_safe_import",
}
SOURCE_REF_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]+$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _string_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class RetrievalFilters:
    """検索時に適用する Metadata Filter。

    repository / project / platform / source_kind / document_id は hard filter として
    扱い、Unity minor version や domain は Retriever 側の boost に使う。
    """

    repository: str | None = None
    project_id: str | None = None
    engine: str | None = None
    unity_version: str | None = None
    unity_version_major: str | None = None
    render_pipeline: str | None = None
    pipeline_version: str | None = None
    platforms: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source_kind: str | None = None
    document_id: str | None = None
    review_status: str | None = None
    confidence: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RetrievalFilters":
        data = dict(value or {})
        platforms = data.get("platforms")
        if platforms is None or platforms == []:
            platforms = data.get("platform")
        domains = data.get("domains")
        if domains is None or domains == []:
            domains = data.get("domain")
        return cls(
            repository=_optional_string(data.get("repository")),
            project_id=_optional_string(data.get("project_id")),
            engine=_optional_string(data.get("engine")),
            unity_version=_optional_string(data.get("unity_version")),
            unity_version_major=_optional_string(data.get("unity_version_major")),
            render_pipeline=_optional_string(data.get("render_pipeline")),
            pipeline_version=_optional_string(data.get("pipeline_version")),
            platforms=_string_tuple(_coerce_list(platforms)),
            domains=_string_tuple(_coerce_list(domains)),
            topics=_string_tuple(_coerce_list(data.get("topics"))),
            tags=_string_tuple(_coerce_list(data.get("tags"))),
            source_kind=_optional_string(data.get("source_kind")),
            document_id=_optional_string(data.get("document_id")),
            review_status=_optional_string(data.get("review_status")),
            confidence=_optional_string(data.get("confidence")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "project_id": self.project_id,
            "engine": self.engine,
            "unity_version": self.unity_version,
            "unity_version_major": self.unity_version_major,
            "render_pipeline": self.render_pipeline,
            "pipeline_version": self.pipeline_version,
            "platforms": list(self.platforms),
            "domains": list(self.domains),
            "topics": list(self.topics),
            "tags": list(self.tags),
            "source_kind": self.source_kind,
            "document_id": self.document_id,
            "review_status": self.review_status,
            "confidence": self.confidence,
        }

    @property
    def has_hard_filters(self) -> bool:
        return any(
            value
            for value in (
                self.repository,
                self.project_id,
                self.platforms,
                self.source_kind,
                self.document_id,
            )
        )


@dataclass(frozen=True)
class RetrievalRequest:
    """1 回の検索を再現可能にする Request Contract。"""

    request_id: str
    raw_query: str
    normalized_query: str
    route_id: str
    execution_profile: str
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    top_k: int = DEFAULT_TOP_K
    candidate_k: int = DEFAULT_CANDIDATE_K
    max_chars: int = DEFAULT_MAX_CHARS
    sources: tuple[str, ...] = ()
    query_tokens: tuple[str, ...] = ()
    technical_tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.request_id).strip() or not SAFE_ID_RE.fullmatch(str(self.request_id)):
            raise ValueError("request_id must be a safe non-empty identifier")
        if not str(self.raw_query).strip() or not str(self.normalized_query).strip():
            raise ValueError("query must not be empty")
        if not str(self.route_id).strip():
            raise ValueError("route_id is required")
        if self.execution_profile not in ALLOWED_EXECUTION_PROFILES:
            raise ValueError(f"unsupported execution_profile: {self.execution_profile}")
        if not 1 <= int(self.top_k) <= MAX_TOP_K:
            raise ValueError("top_k must be 1..20")
        if not int(self.top_k) <= int(self.candidate_k) <= MAX_CANDIDATE_K:
            raise ValueError("candidate_k must be >= top_k and <= 200")
        if not 256 <= int(self.max_chars) <= MAX_CONTEXT_CHARS:
            raise ValueError("max_chars must be 256..100000")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "query": {
                "raw": self.raw_query,
                "normalized": self.normalized_query,
                "tokens": list(self.query_tokens),
                "technical_tokens": list(self.technical_tokens),
            },
            "route_id": self.route_id,
            "execution_profile": self.execution_profile,
            "filters": self.filters.to_dict(),
            "limits": {
                "top_k": int(self.top_k),
                "candidate_k": int(self.candidate_k),
                "max_chars": int(self.max_chars),
            },
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class CandidateProvenance:
    """Candidate と一緒に移動する Source provenance。"""

    source_kind: str
    source_ref: str
    document_id: str | None = None
    evidence_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    source_units: tuple[int, ...] = ()
    drive_file_id: str | None = None
    workspace_path: str | None = None
    original_required: bool = False
    relation_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.source_kind).strip():
            raise ValueError("provenance.source_kind is required")
        if not SOURCE_REF_RE.fullmatch(str(self.source_ref)):
            raise ValueError("provenance.source_ref must be a URI")
        if any(int(unit) <= 0 for unit in self.source_units):
            raise ValueError("provenance.source_units must contain positive integers")
        if any(not SOURCE_REF_RE.fullmatch(str(ref)) for ref in self.relation_refs):
            raise ValueError("provenance.relation_refs must contain URIs")
        if self.workspace_path and any(part == ".." for part in str(self.workspace_path).split("/")):
            raise ValueError("provenance.workspace_path must not traverse parent directories")

    @property
    def has_identity(self) -> bool:
        return bool(self.document_id or self.evidence_id or self.evidence_ids or self.source_units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "document_id": self.document_id,
            "evidence_id": self.evidence_id,
            "evidence_ids": list(self.evidence_ids),
            "source_units": list(self.source_units),
            "drive_file_id": self.drive_file_id,
            "workspace_path": self.workspace_path,
            "original_required": bool(self.original_required),
            "relation_refs": list(self.relation_refs),
        }


@dataclass
class RetrievalCandidate:
    """Backend間で受け渡す検索候補。"""

    candidate_id: str
    source_kind: str
    source_ref: str
    document_id: str | None
    evidence_id: str | None
    heading: str
    summary: str
    content: str
    metadata: dict[str, Any]
    provenance: CandidateProvenance
    confidence: str = "unverified"
    review_status: str | None = None
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    fusion_score: float = 0.0
    rerank_score: float | None = None

    def __post_init__(self) -> None:
        if not str(self.candidate_id).strip():
            raise ValueError("candidate_id is required")
        if not str(self.summary or self.content).strip():
            raise ValueError("candidate text is required")

    @property
    def statement(self) -> str:
        return str(self.summary or self.content).strip()

    def searchable_text(self) -> str:
        values: list[str] = [
            self.candidate_id,
            self.source_kind,
            self.source_ref,
            self.document_id or "",
            self.evidence_id or "",
            self.heading,
            self.summary,
            self.content,
        ]
        for key, value in self.metadata.items():
            values.append(str(key))
            if isinstance(value, (list, tuple, set)):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
        return " ".join(value for value in values if value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "document_id": self.document_id,
            "evidence_id": self.evidence_id,
            "text": {
                "heading": self.heading,
                "summary": self.summary,
                "content": self.content,
            },
            "metadata": self.metadata,
            "provenance": self.provenance.to_dict(),
            "scores": {
                "lexical": round(float(self.lexical_score), 6),
                "semantic": round(float(self.semantic_score), 6),
                "fusion": round(float(self.fusion_score), 6),
                "rerank": None if self.rerank_score is None else round(float(self.rerank_score), 6),
            },
            "confidence": self.confidence,
            "review_status": self.review_status,
        }


@dataclass(frozen=True)
class GroundingBundle:
    """Provenance付きで Context へ handoff する bounded bundle。"""

    grounding_bundle_id: str
    request_id: str
    items: tuple[dict[str, Any], ...]
    diagnostics: dict[str, Any]
    status: str = "grounded"

    @property
    def reference(self) -> str:
        return f"rag://grounding/{self.grounding_bundle_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "grounding_bundle_id": self.grounding_bundle_id,
            "request_id": self.request_id,
            "items": list(self.items),
            "diagnostics": self.diagnostics,
            "status": self.status,
            "grounding_bundle_ref": self.reference,
        }


def deterministic_id(prefix: str, *parts: Any, length: int = 16) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"
