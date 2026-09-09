"""Retrieval service and backend contracts."""

from RAG.Retrieval.backend import RetrievalBackend
from RAG.Retrieval.dense_retriever import LocalDenseBackend
from RAG.Retrieval.graph_expander import (
    GraphExpansionConfig,
    GraphExpansionResult,
    KnowledgeGraphExpander,
    expand_candidates,
)
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.query_planner import (
    PlannedRetrievalResult,
    PlannedSubquery,
    QueryPlan,
    SubqueryTrace,
    build_query_plan,
    execute_query_plan,
)
from RAG.Retrieval.retrieval_service import RetrievalService, build_default_service, retrieve_knowledge

__all__ = [
    "LocalDenseBackend",
    "LocalLexicalBackend",
    "RetrievalBackend",
    "RetrievalService",
    "build_default_service",
    "retrieve_knowledge",
    "GraphExpansionConfig",
    "GraphExpansionResult",
    "KnowledgeGraphExpander",
    "PlannedRetrievalResult",
    "PlannedSubquery",
    "QueryPlan",
    "SubqueryTrace",
    "build_query_plan",
    "execute_query_plan",
    "expand_candidates",
]
