"""Retrieval service and backend contracts."""

from RAG.Retrieval.backend import RetrievalBackend
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.retrieval_service import RetrievalService, build_default_service, retrieve_knowledge

__all__ = ["LocalLexicalBackend", "RetrievalBackend", "RetrievalService", "build_default_service", "retrieve_knowledge"]
