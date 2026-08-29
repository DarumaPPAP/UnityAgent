"""Canonical Persistence filesystem layout."""
from __future__ import annotations
from pathlib import Path

from Persistence.Store.atomic_store import safe_id


class PersistenceLayout:
    def __init__(self, root) -> None:
        self.root = Path(root).expanduser().resolve()

    def run_root(self, run_id: str) -> Path:
        return self.root / "runs" / safe_id(run_id, "run_id")

    def execution_state(self, run_id: str) -> Path:
        return self.run_root(run_id) / "current" / "execution-state.json"

    def workflow_state(self, run_id: str) -> Path:
        return self.run_root(run_id) / "current" / "workflow-state.json"

    def loop_state(self, run_id: str, loop_id: str) -> Path:
        return self.run_root(run_id) / "current" / "loops" / f"{safe_id(loop_id, 'loop_id')}.json"

    def snapshot(self, run_id: str, kind: str, digest: str, identity: str | None = None) -> Path:
        token = digest.replace("sha256:", "")
        name = f"{safe_id(identity, 'identity')}-{token}.json" if identity else f"{token}.json"
        return self.run_root(run_id) / "snapshots" / safe_id(kind, "snapshot kind") / name

    def checkpoint(self, run_id: str, checkpoint_id: str) -> Path:
        return self.run_root(run_id) / "checkpoints" / f"{safe_id(checkpoint_id, 'checkpoint_id')}.json"

    def session(self, session_id: str) -> Path:
        return self.root / "sessions" / f"{safe_id(session_id, 'session_id')}.json"

    def memory(self, memory_id: str) -> Path:
        return self.root / "memory" / "records" / f"{safe_id(memory_id, 'memory_id')}.json"

    def memory_safe_index(self) -> Path:
        return self.root / "memory" / "safe-index.jsonl"

    def memory_events(self) -> Path:
        return self.root / "memory" / "events.jsonl"

    def evidence(self, evidence_id: str) -> Path:
        return self.root / "evidence" / "records" / f"{safe_id(evidence_id, 'evidence_id')}.json"

    def evidence_events(self) -> Path:
        return self.root / "evidence" / "events.jsonl"

    def checkpoint_events(self) -> Path:
        return self.root / "migration" / "checkpoint-events.jsonl"

    def migration_events(self) -> Path:
        return self.root / "migration" / "checkpoint-migrations.jsonl"
