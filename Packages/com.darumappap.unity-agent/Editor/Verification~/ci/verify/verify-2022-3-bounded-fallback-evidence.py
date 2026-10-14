#!/usr/bin/env python3
"""Validate the bounded Unity 2022.3 Built-in fallback evidence contract."""
from __future__ import annotations

from pathlib import Path
import re
import sys

import yaml

from historical_evidence import validate_historical_evidence


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "ci/evidence/artist/historical/unity2022-3-builtin-bounded-fallback-evidence.yaml"


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def passed(node: dict, name: str) -> None:
    if node.get("status") != "passed":
        fail(f"{name}.status must be passed")


def main() -> int:
    validate_historical_evidence(EVIDENCE)
    if not EVIDENCE.is_file():
        fail(f"missing evidence file: {EVIDENCE.relative_to(ROOT)}")
    data = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8")) or {}
    if data.get("product") != "UnityArtistCLI" or data.get("case") != "unity-2022.3-builtin-bounded-fallback" or data.get("status") != "passed":
        fail("bounded fallback evidence identity/status is invalid")
    support = data.get("support", {})
    if support.get("unity_version") != "2022.3.22f1" or support.get("render_pipeline") != "builtin":
        fail("fallback evidence must be for Unity 2022.3 Built-in")
    if support.get("transport") != "official_unity_cli_bounded_batch_fallback":
        fail("fallback transport is not explicit")
    candidate = data.get("official_first_candidate", {})
    if candidate.get("transport") != "official_unity_cli_pipeline" or candidate.get("gate_status") != "failed_concrete" or candidate.get("fallback_allowed_after_gate") is not True:
        fail("Official Pipeline first-candidate failure is not preserved")
    fallback = data.get("fallback", {})
    if fallback.get("selected") is not True or fallback.get("status") != "verified_bounded_non_mcp":
        fail("bounded non-MCP fallback was not verified")
    if fallback.get("fixed_editor_method") != "UnityArtist.UnityArtistBatchCommands.Dispatch":
        fail("fallback entrypoint is not fixed")
    forbidden = set(fallback.get("forbidden", []))
    if not {"dynamic_code_execution", "raw_yaml_mutation", "mcp_transport", "automatic_scene_save"}.issubset(forbidden):
        fail("fallback forbidden-surface contract is incomplete")
    if data.get("editor", {}).get("compile_error_count") != 0:
        fail("fallback editor evidence must record zero compile errors")

    flow = data.get("artist_flow", {})
    for name in ("inspect", "plan", "preview", "approval_guard", "apply", "capture", "evaluate", "refine", "refine_apply", "history"):
        passed(flow.get(name, {}), f"artist_flow.{name}")
    if flow["approval_guard"].get("no_token_status") != "blocked" or flow["approval_guard"].get("no_token_error") != "APPROVAL_REQUIRED":
        fail("approval guard evidence is incomplete")
    apply = flow["apply"]
    if apply.get("verified") is not True or apply.get("save_performed") is not False or apply.get("undo_available") is not True:
        fail("apply must be verified, undoable, and non-saving")
    capture = flow["capture"]
    if capture.get("verified") is not True or capture.get("resolution") != "1920x1080":
        fail("fallback capture must be a verified 1920x1080 image")
    if not re.fullmatch(r"[0-9a-f]{64}", str(capture.get("png_sha256", ""))):
        fail("fallback capture must contain a SHA-256 digest")
    if flow["evaluate"].get("decision") != "accepted" or flow["evaluate"].get("human_review") is not True:
        fail("fallback capture must have an explicit accepted human review")
    if data.get("terminal_state") != "verified_for_fixture":
        fail("fallback terminal state must be verified_for_fixture")
    print("Historical record validation only; current Editor: BLOCKED_NOT_RUN/not_observed")
    print("Historical Unity 2022.3 Built-in bounded fallback evidence contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
