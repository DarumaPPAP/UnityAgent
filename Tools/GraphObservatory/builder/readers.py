from pathlib import Path
from typing import Any
import yaml


class CanonicalReader:
    """Read canonical UnityAgent sources without mutating them."""

    def __init__(self, root: str):
        self.root = Path(root)

    def read_yaml(self, path: str) -> dict[str, Any]:
        target = self.root / path
        if not target.exists():
            return {}

        with target.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def read_context(self) -> dict[str, Any]:
        return self.read_yaml("Context/Selection/context-catalog.yaml")

    def read_harness(self) -> dict[str, Any]:
        return self.read_yaml("Policy/Evidence/quality-gates.yaml")

    def read_golden_tasks(self) -> list[dict[str, Any]]:
        document = self.read_yaml("Eval/Datasets/Golden/cases.yaml")
        cases = document.get("cases", [])
        return list(cases) if isinstance(cases, list) else []


def read_context(root: str = ".") -> dict[str, Any]:
    return CanonicalReader(root).read_context()


def read_harness(root: str = ".") -> dict[str, Any]:
    return CanonicalReader(root).read_harness()


def read_golden_tasks(root: str = ".") -> list[dict[str, Any]]:
    return CanonicalReader(root).read_golden_tasks()
