from pathlib import Path
from typing import Any
import yaml


class CanonicalReader:
    """Read canonical UnityAgent YAML sources without mutating them."""

    def __init__(self, root: str):
        self.root = Path(root)

    def read_yaml(self, path: str) -> dict[str, Any]:
        target = self.root / path
        if not target.exists():
            return {}

        with target.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def read_context(self) -> dict[str, Any]:
        return self.read_yaml(".ai/context-index.yaml")

    def read_harness(self) -> dict[str, Any]:
        return self.read_yaml(".ai/harness/quality-gates.yaml")

    def read_graph_contract(self) -> dict[str, Any]:
        return self.read_yaml(".ai/graph-contract.yaml")

    def read_golden_tasks(self) -> list[dict[str, Any]]:
        tasks = []
        folder = self.root / "Tests" / "GoldenTasks"
        if not folder.exists():
            return tasks

        for file in folder.rglob("*.yaml"):
            with file.open("r", encoding="utf-8") as stream:
                tasks.append(yaml.safe_load(stream) or {})

        return tasks
