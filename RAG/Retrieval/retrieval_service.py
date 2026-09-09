"""Top-level RAG retrieval orchestration.

This module owns query handling, source adapter composition, deterministic backend
execution, bounded grounding, and diagnostics. It does not select a tool/provider,
write Memory, or make the final answer-quality decision.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
from pathlib import Path
import time
from typing import Any

from RAG.Adapters.local_knowledge import StaticKnowledgeAdapter
from RAG.Adapters.memory.adapter import MemoryAdapter
from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Contracts.models import (
    DEFAULT_CANDIDATE_K,
    DEFAULT_MAX_CHARS,
    DEFAULT_TOP_K,
    RetrievalFilters,
    RetrievalRequest,
    deterministic_id,
)
from RAG.Grounding.context_projector import project_grounding_bundle
from RAG.Grounding.grounding_builder import build_grounding_bundle
from RAG.Observability.retrieval_trace import RetrievalTrace
from RAG.Query.classify_query import classify_query
from RAG.Query.extract_filters import extract_filters
from RAG.Query.rewrite_query import rewrite_query
from RAG.Retrieval.backend import RetrievalBackend
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend


SOURCE_ALIASES = {
    "mrc": "my_resource_center",
    "myresourcecenter": "my_resource_center",
    "my_resource_center": "my_resource_center",
    "memory": "project_memory",
    "project_memory": "project_memory",
    "persistence_memory": "project_memory",
    "static": "unityagent_static_knowledge",
    "knowledge": "unityagent_static_knowledge",
    "unityagent_static_knowledge": "unityagent_static_knowledge",
}


def _merge_filters(
    extracted: RetrievalFilters,
    explicit: RetrievalFilters | Mapping[str, Any] | None,
    *,
    repository: str | None,
    project_id: str | None,
    unity_version: str | None,
    render_pipeline: str | None,
    pipeline_version: str | None,
    platform: Iterable[str] | str | None,
    domains: Iterable[str] | None,
) -> RetrievalFilters:
    values = extracted.to_dict()
    if explicit is not None:
        values.update(explicit if isinstance(explicit, Mapping) else explicit.to_dict())
    for key, value in {
        "repository": repository,
        "project_id": project_id,
        "unity_version": unity_version,
        "render_pipeline": render_pipeline,
        "pipeline_version": pipeline_version,
    }.items():
        if value is not None:
            values[key] = value
    if platform is not None:
        values["platforms"] = [platform] if isinstance(platform, str) else list(platform)
    if domains is not None:
        values["domains"] = [domains] if isinstance(domains, str) else list(domains)
    if values.get("unity_version"):
        values["unity_version_major"] = str(values["unity_version"]).split(".", 1)[0]
    return RetrievalFilters.from_mapping(values)


def _source_names(
    sources: Iterable[str] | None,
    *,
    root: Path,
    my_resource_center_index: str | Path | None,
    memory_store_root: str | Path | None,
    custom_backend: bool,
) -> tuple[str, ...]:
    if sources is not None:
        source_values = [sources] if isinstance(sources, str) else list(sources)
        names = [SOURCE_ALIASES.get(str(item).casefold(), str(item).casefold()) for item in source_values]
    else:
        names = []
        if not custom_backend and (root / "Context/Retrieval/Knowledge/index.yaml").is_file():
            names.append("unityagent_static_knowledge")
    if my_resource_center_index is not None and "my_resource_center" not in names:
        names.append("my_resource_center")
    if memory_store_root is not None and "project_memory" not in names:
        names.append("project_memory")
    return tuple(dict.fromkeys(names))


def _load_candidates(
    source_names: Iterable[str],
    *,
    root: Path,
    my_resource_center_index: str | Path | None,
    memory_store_root: str | Path | None,
    execution_profile: str,
) -> tuple[list[Any], list[dict[str, Any]], list[str], dict[str, str]]:
    candidates: list[Any] = []
    failures: list[dict[str, Any]] = []
    methods: list[str] = []
    revisions: dict[str, str] = {}
    for source_name in source_names:
        if source_name == "unityagent_static_knowledge":
            result = StaticKnowledgeAdapter(root=root).load()
            methods.append("static_knowledge")
        elif source_name == "my_resource_center":
            index_path = Path(my_resource_center_index) if my_resource_center_index is not None else Path("catalog/search-index.json")
            if not index_path.is_absolute():
                index_path = root / index_path
            result = MyResourceCenterAdapter(index_path).load()
            methods.append("my_resource_center_search_index")
        elif source_name == "project_memory":
            if memory_store_root is None:
                failures.append({"source": source_name, "code": "source_unavailable", "message": "memory_store_root is required"})
                continue
            memory_path = Path(memory_store_root)
            if not memory_path.is_absolute():
                memory_path = root / memory_path
            result = MemoryAdapter(memory_path, execution_profile).load()
            methods.append("persistence_memory_read")
        else:
            failures.append({"source": source_name, "code": "unsupported_source", "message": f"unsupported RAG source: {source_name}"})
            continue
        candidates.extend(result.candidates)
        for diagnostic in result.diagnostics:
            failures.append({"source": result.source_id, **dict(diagnostic)})
        if result.source_revision:
            revisions[result.source_id] = result.source_revision
    return candidates, failures, methods, revisions


class RetrievalService:
    """Composable service used by the public function and offline evaluator."""

    def __init__(
        self,
        *,
        backend: RetrievalBackend | None = None,
        root: str | Path = ".",
        my_resource_center_index: str | Path | None = None,
        memory_store_root: str | Path | None = None,
    ) -> None:
        self.backend = backend
        self.root = Path(root).resolve()
        self.my_resource_center_index = my_resource_center_index
        self.memory_store_root = memory_store_root

    def retrieve(
        self,
        *,
        query: str,
        route_id: str,
        execution_profile: str,
        repository: str | None = None,
        unity_version: str | None = None,
        render_pipeline: str | None = None,
        pipeline_version: str | None = None,
        platform: list[str] | None = None,
        domains: Iterable[str] | None = None,
        project_id: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        max_chars: int = DEFAULT_MAX_CHARS,
        backend: RetrievalBackend | None = None,
        my_resource_center_index: str | Path | None = None,
        memory_store_root: str | Path | None = None,
        sources: Iterable[str] | None = None,
        filters: RetrievalFilters | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        normalized = rewrite_query(query)
        extracted = extract_filters(normalized)
        merged_filters = _merge_filters(
            extracted,
            filters,
            repository=repository,
            project_id=project_id,
            unity_version=unity_version,
            render_pipeline=render_pipeline,
            pipeline_version=pipeline_version,
            platform=platform,
            domains=domains,
        )
        selected_backend = backend or self.backend
        selected_mrc = my_resource_center_index if my_resource_center_index is not None else self.my_resource_center_index
        selected_memory = memory_store_root if memory_store_root is not None else self.memory_store_root
        source_names = _source_names(
            sources,
            root=self.root,
            my_resource_center_index=selected_mrc,
            memory_store_root=selected_memory,
            custom_backend=selected_backend is not None,
        )
        request_id = deterministic_id(
            "req",
            normalized.query_hash,
            route_id,
            execution_profile,
            merged_filters.to_dict(),
            source_names,
            top_k,
            candidate_k,
            max_chars,
        )
        request = RetrievalRequest(
            request_id=request_id,
            raw_query=normalized.raw,
            normalized_query=normalized.normalized,
            route_id=route_id,
            execution_profile=execution_profile,
            filters=merged_filters,
            top_k=top_k,
            candidate_k=candidate_k,
            max_chars=max_chars,
            sources=source_names,
            query_tokens=normalized.tokens,
            technical_tokens=normalized.technical_tokens,
        )
        source_candidates, source_failures, methods, revisions = _load_candidates(
            source_names,
            root=self.root,
            my_resource_center_index=selected_mrc,
            memory_store_root=selected_memory,
            execution_profile=execution_profile,
        )
        retrieval_backend = selected_backend or LocalLexicalBackend(source_candidates)
        backend_name = retrieval_backend.__class__.__name__
        backend_revision = str(getattr(retrieval_backend, "revision", "unknown"))
        diagnostics: list[dict[str, Any]] = [dict(item) for item in source_failures]
        try:
            ranked = list(retrieval_backend.retrieve(request))
        except Exception as exc:  # Backend failures are explicit; no fallback backend is invoked.
            ranked = []
            diagnostics.append({"code": "backend_failure", "backend": backend_name, "message": str(exc)})
        ranked = ranked[: request.candidate_k]
        bundle = build_grounding_bundle(
            request,
            ranked[: request.top_k],
            source_failures=diagnostics,
            max_items=request.top_k,
            max_chars=request.max_chars,
        )
        projection = project_grounding_bundle(bundle)
        status = bundle.status
        if diagnostics and status == "grounded":
            status = "partial"
        capabilities = set(retrieval_backend.capabilities()) if hasattr(retrieval_backend, "capabilities") else set()
        trace = RetrievalTrace(
            request_id=request.request_id,
            query_hash=normalized.query_hash,
            route_id=route_id,
            execution_profile=execution_profile,
            query_kind=str(classify_query(normalized)["kind"]),
            filters=merged_filters.to_dict(),
            backend=backend_name,
            backend_revision=backend_revision,
            retrieval_methods=methods + (["lexical"] if "lexical" in capabilities else []),
            candidate_count=len(source_candidates),
            returned_count=len(ranked[: request.top_k]),
            grounded_count=len(bundle.items),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            truncated=len(ranked) > request.top_k or (len(bundle.items) < len(ranked) and bool(ranked)),
            fallback_used=False,
            source_failures=diagnostics,
            top_source_refs=[str(item.get("provenance", {}).get("source_ref")) for item in bundle.items],
            diagnostics=list(bundle.diagnostics.get("skipped_candidates", [])),
        )
        index_revision = (
            "sha256:" + hashlib.sha256(
                "|".join(f"{key}:{value}" for key, value in sorted(revisions.items())).encode("utf-8")
            ).hexdigest()
            if revisions else "unbound"
        )
        return {
            "schema_version": "1.0",
            "result_id": deterministic_id("result", request.request_id, bundle.grounding_bundle_id),
            "request_id": request.request_id,
            "request": request.to_dict(),
            "status": status,
            "candidates": [item.to_dict() for item in ranked[: request.top_k]],
            "grounding_bundle": bundle.to_dict(),
            "context_projection": projection,
            "diagnostics": diagnostics + list(bundle.diagnostics.get("skipped_candidates", [])),
            "trace": trace.to_dict(),
            "revisions": {
                "backend": backend_revision,
                "index": index_revision,
                "sources": revisions,
                "ranking": "lexical-v1",
            },
        }


def build_default_service(**kwargs: Any) -> RetrievalService:
    return RetrievalService(**kwargs)


def retrieve_knowledge(
    *,
    query: str,
    route_id: str,
    execution_profile: str,
    repository: str | None = None,
    unity_version: str | None = None,
    render_pipeline: str | None = None,
    pipeline_version: str | None = None,
    platform: list[str] | None = None,
    domains: list[str] | None = None,
    project_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    max_chars: int = DEFAULT_MAX_CHARS,
    backend: RetrievalBackend | None = None,
    my_resource_center_index: str | Path | None = None,
    memory_store_root: str | Path | None = None,
    sources: Iterable[str] | None = None,
    filters: RetrievalFilters | Mapping[str, Any] | None = None,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Public RAG entrypoint matching the implementation specification."""

    return RetrievalService(
        backend=backend,
        root=root,
        my_resource_center_index=my_resource_center_index,
        memory_store_root=memory_store_root,
    ).retrieve(
        query=query,
        route_id=route_id,
        execution_profile=execution_profile,
        repository=repository,
        unity_version=unity_version,
        render_pipeline=render_pipeline,
        pipeline_version=pipeline_version,
        platform=platform,
        domains=domains,
        project_id=project_id,
        top_k=top_k,
        candidate_k=candidate_k,
        max_chars=max_chars,
        sources=sources,
        filters=filters,
    )


__all__ = ["RetrievalService", "build_default_service", "retrieve_knowledge"]
