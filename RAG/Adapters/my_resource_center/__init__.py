"""MyResourceCenter Search Index bridge."""

from RAG.Adapters.my_resource_center.adapter import MyResourceCenterAdapter
from RAG.Adapters.my_resource_center.search_index_reader import read_search_index

__all__ = ["MyResourceCenterAdapter", "read_search_index"]
