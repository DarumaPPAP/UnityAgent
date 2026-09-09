"""UnityAgent の Retrieval-Augmented Grounding subsystem.

RAG は検索と Grounding 用の材料を担当し、Route 選択・Runtime 実行・永続 Memory
の書き込みは担当しない。
"""

from RAG.Retrieval.retrieval_service import retrieve_knowledge

__all__ = ["retrieve_knowledge"]
