#!/usr/bin/env python3
"""Validate the UnityArtistCLI compatibility bucket and matrix contract."""
from __future__ import annotations

import re
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "Packages/com.darumappap.artist-subagent/Editor/Compatibility/ArtistCompatibility.cs"
COMPATIBILITY_TESTS = ROOT / "Packages/com.darumappap.artist-subagent/Tests/Editor/ArtistCompatibilityTests.cs"
SKILL = ROOT / ".agents/skills/unity-artist-unity-api-compatibility/SKILL.md"
SPEC = ROOT / "docs/references/unity-api-compatibility.md"
AGENTS = ROOT / "AGENTS.md"
MATRIX = ROOT / "ci/compatibility/support-matrix.yaml"
EXPECTED_BUCKETS = {"BASE", "UNITY_6000_4", "UNITY_6000_5", "UNITY_6000_7"}


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"missing compatibility artifact: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def main() -> int:
    source = read(COMPATIBILITY)
    tests = read(COMPATIBILITY_TESTS)
    skill = read(SKILL)
    spec = read(SPEC)
    agents = read(AGENTS)
    matrix = yaml.safe_load(read(MATRIX)) or {}

    for asset in (COMPATIBILITY, COMPATIBILITY_TESTS):
        if not Path(str(asset) + ".meta").is_file():
            fail(f"Unity package asset is missing .meta: {asset.relative_to(ROOT)}")

    if "BASE" not in source or "UNITY_6000_4" not in source or "UNITY_6000_5" not in source or "UNITY_6000_7" not in source:
        fail("compatibility source must document all four maintenance buckets")
    if re.search(r"UNITY_6000_6", source):
        fail("Unity 6.6 must roll into UNITY_6000_7; no 6000.6 bucket is allowed")
    if "2022.3." in source or "6000." not in source or "builtin" not in source or "urp" not in source or "hdrp" not in source:
        fail("compatibility source does not declare only the three Unity 6+ release cases")
    if "ReleaseMatrixAcceptsUnity6Pipelines" not in tests or "UnsupportedPipelineIsRejectedBeforeMutation" not in tests:
        fail("compatibility tests do not cover supported and pre-mutation rejection paths")
    if "name: unity-artist-unity-api-compatibility" not in skill:
        fail("current compatibility skill is missing")
    skill_lower = skill.casefold()
    if "immutable package asset rule" not in skill_lower or "scene identity rule" not in skill_lower:
        fail("compatibility skill must preserve package .meta and identity rules")
    if "BASE" not in spec or "UNITY_6000_7" not in spec:
        fail("compatibility spec is incomplete")
    if ".agents/skills/unity-artist-unity-api-compatibility/SKILL.md" not in agents:
        fail("AGENTS.md must require the current compatibility skill")

    actual = {(str(row.get("unity_version")), str(row.get("render_pipeline"))) for row in matrix.get("rows", []) if isinstance(row, dict)}
    expected = {
        ("Unity 6.x+", "builtin"),
        ("Unity 6.x+", "urp"),
        ("Unity 6.x+", "hdrp"),
    }
    if actual != expected:
        fail(f"release matrix drifted: {sorted(actual)}")
    print("Unity API compatibility static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
