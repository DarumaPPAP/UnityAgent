"""Read-only source adapters used to populate RAG candidates."""

from RAG.Adapters.local_knowledge import StaticKnowledgeAdapter
from RAG.Adapters.memory.adapter import MemoryAdapter
from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter

__all__ = ["MemoryAdapter", "MyResourceCenterAdapter", "StaticKnowledgeAdapter"]
