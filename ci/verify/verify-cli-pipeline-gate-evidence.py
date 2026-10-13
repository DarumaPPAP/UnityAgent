#!/usr/bin/env python3
"""Validate the exhaustive Unity 2022.3 Official Pipeline gate evidence."""
from __future__ import annotations

from pathlib import Path
import sys

import yaml

from historical_evidence import validate_historical_evidence


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "ci/evidence/artist/historical/cli-pipeline-gate-evidence.yaml"
EXPECTED_VERSIONS = {
    "0.6.0-exp.1",
    "0.5.0-exp.1",
    "0.4.0-exp.1",
    "0.3.1-exp.1",
    "0.3.0-exp.1",
    "0.2.0-exp.2",
}


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    validate_historical_evidence(EVIDENCE)
    if not EVIDENCE.is_file():
        fail(f"missing evidence file: {EVIDENCE.relative_to(ROOT)}")
    data = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8")) or {}
    if data.get("product") != "UnityArtistCLI" or data.get("case") != "unity-2022.3-builtin":
        fail("gate evidence identity is invalid")
    candidate = data.get("official_first_candidate", {})
    if candidate.get("transport") != "official_unity_cli_pipeline":
        fail("2022.3 gate must keep Official Unity CLI/Pipeline as first candidate")
    if candidate.get("cli", {}).get("identified_editor") != "2022.3.22f1":
        fail("gate evidence must identify the observed Unity 2022.3 editor")
    pipeline = candidate.get("pipeline", {})
    if pipeline.get("available_versions_status") != "passed":
        fail("available Official Pipeline versions must be observed")
    versions = set(pipeline.get("available_versions", []))
    if versions != EXPECTED_VERSIONS:
        fail(f"available Pipeline version set drifted: {sorted(versions)}")
    probe = pipeline.get("exhaustive_version_probe", {})
    if probe.get("status") != "all_available_versions_failed" or probe.get("project_version") != "2022.3.22f1":
        fail("2022.3 gate must record an exhaustive probe against the observed project version")
    results = probe.get("results", [])
    result_versions = {row.get("package_version") for row in results}
    if result_versions != EXPECTED_VERSIONS or len(results) != len(EXPECTED_VERSIONS):
        fail("exhaustive probe must contain exactly one result for every listed Pipeline version")
    for row in results:
        if row.get("status") != "failed" or row.get("error") != "Pipeline package requires Unity 6.0 or later":
            fail(f"unexpected 2022.3 probe result: {row}")
    fallback = data.get("fallback_evaluation", {})
    if fallback.get("selected") is not True or fallback.get("status") != "verified_bounded_non_mcp":
        fail("the bounded non-MCP fallback must be explicitly selected only after the concrete gate failure")
    if fallback.get("transport") != "official_unity_cli_bounded_batch_fallback":
        fail("the selected fallback transport is not explicit")
    if fallback.get("entrypoint") != "UnityArtist.UnityArtistBatchCommands.Dispatch":
        fail("the selected fallback entrypoint is not fixed")
    if data.get("terminal_state") != "verified_for_fixture":
        fail("the 2022.3 bounded fallback fixture must be verified")
    print("Historical record validation only; current Editor: BLOCKED_NOT_RUN/not_observed")
    print("Historical Unity 2022.3 Official Pipeline exhaustive gate and bounded fallback evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
