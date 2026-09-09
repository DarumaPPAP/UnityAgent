"""Read-only source adapters used to populate RAG candidates."""

from RAG.Adapters.local_knowledge import StaticKnowledgeAdapter
from RAG.Adapters.memory.adapter import MemoryAdapter
from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Adapters.qdrant import QdrantBackend

__all__ = ["MemoryAdapter", "MyResourceCenterAdapter", "QdrantBackend", "StaticKnowledgeAdapter"]
