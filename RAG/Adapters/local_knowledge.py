"""Read-only adapter for UnityAgent's existing curated static Knowledge contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import yaml

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate


DEFAULT_INDEX = Path("Context/Retrieval/Knowledge/index.yaml")


@dataclass(frozen=True)
class StaticKnowledgeLoadResult:
    candidates: tuple[RetrievalCandidate, ...]
    source_id: str
    source_revision: str | None
    diagnostics: tuple[dict[str, str], ...]


class StaticKnowledgeAdapter:
    """Compatibility source during the staged Context/Retrieval → RAG migration."""

    source_id = "unityagent_static_knowledge"

    def __init__(self, root: str | Path = ".", index_path: str | Path = DEFAULT_INDEX) -> None:
        self.root = Path(root).resolve()
        self.index_path = Path(index_path)

    def load(self) -> StaticKnowledgeLoadResult:
        path = (self.root / self.index_path).resolve()
        if path != self.root and self.root not in path.parents:
            return StaticKnowledgeLoadResult((), self.source_id, None, ({"code": "path_escape", "message": str(path)},))
        try:
            raw = path.read_bytes()
            document = yaml.safe_load(raw.decode("utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            return StaticKnowledgeLoadResult(
                (), self.source_id, None, ({"code": "source_unavailable", "message": str(exc)},)
            )
        if not isinstance(document, dict) or not isinstance(document.get("knowledge"), dict):
            return StaticKnowledgeLoadResult(
                (), self.source_id, None,
                ({"code": "malformed_index", "message": "static Knowledge index must contain knowledge mapping"},),
            )
        revision = "sha256:" + hashlib.sha256(raw).hexdigest()
        candidates: list[RetrievalCandidate] = []
        diagnostics: list[dict[str, str]] = []
        for knowledge_id, entry in sorted(document["knowledge"].items()):
            if not isinstance(entry, dict) or not str(entry.get("path") or "").strip():
                diagnostics.append({"code": "malformed_record", "message": f"knowledge entry invalid: {knowledge_id}"})
                continue
            relative = Path(str(entry["path"]))
            source_path = (self.root / relative).resolve()
            if source_path != self.root and self.root not in source_path.parents:
                diagnostics.append({"code": "path_escape", "message": f"knowledge path escapes root: {knowledge_id}"})
                continue
            try:
                contract_raw = source_path.read_bytes()
                contract = yaml.safe_load(contract_raw.decode("utf-8")) or {}
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
                diagnostics.append({"code": "malformed_record", "message": f"{knowledge_id}: {exc}"})
                continue
            if not isinstance(contract, dict):
                diagnostics.append({"code": "malformed_record", "message": f"{knowledge_id}: contract is not a mapping"})
                continue
            candidates.append(self._candidate(str(knowledge_id), entry, contract, relative))
        return StaticKnowledgeLoadResult(tuple(candidates), self.source_id, revision, tuple(diagnostics))

    def candidates(self) -> list[RetrievalCandidate]:
        return list(self.load().candidates)

    @staticmethod
    def _candidate(knowledge_id: str, index_entry: dict[str, Any], contract: dict[str, Any], relative: Path) -> RetrievalCandidate:
        status = str(contract.get("status") or index_entry.get("status") or "unverified")
        summary_fields = (
            "use_when", "required_inputs", "implementation_contract", "prohibited", "required_evidence",
            "conditional_evidence", "failure_signatures", "stop_conditions", "related",
        )
        summary = yaml.safe_dump(
            {key: contract.get(key) for key in summary_fields if key in contract},
            sort_keys=True,
            allow_unicode=True,
        ).strip()
        domain = knowledge_id.split(".", 1)[0]
        source_ref = f"unityagent://knowledge/{knowledge_id}"
        provenance = CandidateProvenance(
            source_kind="unityagent_static_knowledge",
            source_ref=source_ref,
            document_id=knowledge_id,
            evidence_id=knowledge_id,
            workspace_path=relative.as_posix(),
            original_required=False,
        )
        return RetrievalCandidate(
            candidate_id=knowledge_id,
            source_kind="unityagent_static_knowledge",
            source_ref=source_ref,
            document_id=knowledge_id,
            evidence_id=knowledge_id,
            heading=knowledge_id,
            summary=summary,
            content=summary,
            metadata={
                "domains": [domain],
                "topics": [str(item) for item in contract.get("use_when", []) or []],
                "tags": [str(item) for item in contract.get("tags", []) or []],
                "status": status,
                "review_status": status,
                "source_path": relative.as_posix(),
                "human_reference": contract.get("human_reference"),
            },
            provenance=provenance,
            confidence="reviewed" if status.casefold() == "reviewed" else "unverified",
            review_status=status,
        )
