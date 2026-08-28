#!/usr/bin/env python3
"""Validate the current UnityAgent bootstrap while preserving pre-Phase-2 route checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = Path(__file__).resolve().parent / "_legacy_validate_route_graph.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location("unityagent_legacy_route_graph_validator", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load route graph compatibility validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(root: Path) -> list[str]:
    engine = _load_engine()
    agents_path = root / "AGENTS.md"
    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""

    if "<!-- unityagent-bootstrap-map:v2 -->" in agents_text:
        engine.BOOTSTRAP_REQUIRED_MARKERS = (
            "<!-- unityagent-bootstrap-map:v2 -->",
            "bootstrap_map_only: true",
            "`Policy/User/user-policy.yaml`",
            "`Context/Selection/context-catalog.yaml`",
            "`Context/Compatibility/legacy-path-map.yaml`",
            "`.agents/skills/`",
            "`DarumaPPAP/Unity-Graph-Engineering`",
            "`DarumaPPAP/MyUnityMCP`",
            "詳細規約を複製せず",
            "Compatibilityはread-only",
        )
        engine.USER_POLICY_PATH = Path("Policy/User/user-policy.yaml")

    return engine.validate(root)


def main() -> int:
    errors = validate(ROOT)
    if errors:
        print("Route Graph validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Route Graph validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
