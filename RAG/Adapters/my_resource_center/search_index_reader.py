"""Read and minimally validate MyResourceCenter's rebuildable Search Index."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


class SearchIndexError(ValueError):
    """Invalid or unavailable external Search Index."""

    def __init__(self, message: str, *, code: str = "source_unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SearchIndexSnapshot:
    path: str
    revision: str
    schema_version: str
    chunks: tuple[dict[str, Any], ...]
    diagnostics: tuple[dict[str, str], ...] = ()


def _safe_path(path: str | Path) -> Path:
    raw = str(path)
    if not raw.strip():
        raise SearchIndexError("Search Index path is required", code="source_unavailable")
    # An explicit ``..`` component is rejected even when resolve() would land
    # inside the intended directory. The adapter is a read-only boundary and
    # should never turn a user-controlled path into traversal.
    if ".." in Path(raw).parts:
        raise SearchIndexError("Search Index path traversal is forbidden", code="path_traversal")
    return Path(raw).expanduser()


def read_search_index(path: str | Path) -> SearchIndexSnapshot:
    index_path = _safe_path(path)
    try:
        raw = index_path.read_bytes()
    except OSError as exc:
        raise SearchIndexError(f"cannot read Search Index: {index_path}", code="source_unavailable") from exc
    revision = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SearchIndexError(f"malformed Search Index: {index_path}", code="malformed_search_index") from exc
    if not isinstance(document, dict):
        raise SearchIndexError("Search Index root must be an object", code="malformed_search_index")
    if document.get("schemaVersion") != "2.0.0":
        raise SearchIndexError("Search Index schemaVersion must be 2.0.0", code="malformed_search_index")
    if document.get("kind") != "rebuildable-evidence-search-index":
        raise SearchIndexError("unsupported Search Index kind", code="malformed_search_index")
    chunks = document.get("chunks")
    if not isinstance(chunks, list):
        raise SearchIndexError("Search Index chunks must be an array", code="malformed_search_index")

    valid: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            diagnostics.append({"code": "malformed_record", "message": f"chunks[{index}] is not an object"})
            continue
        chunk_id = str(chunk.get("chunkId") or "").strip()
        document_id = str(chunk.get("documentId") or "").strip()
        summary = str(chunk.get("summary") or "").strip()
        if not chunk_id or not document_id or not summary:
            diagnostics.append({
                "code": "malformed_record",
                "message": f"chunks[{index}] requires chunkId, documentId and summary",
            })
            continue
        valid.append(chunk)
    return SearchIndexSnapshot(
        path=str(index_path),
        revision=revision,
        schema_version=str(document["schemaVersion"]),
        chunks=tuple(valid),
        diagnostics=tuple(diagnostics),
    )
