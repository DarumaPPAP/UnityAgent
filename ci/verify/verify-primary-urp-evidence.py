#!/usr/bin/env python3
"""Validate the checked-in Unity 6 URP primary visual evidence contract."""
from __future__ import annotations

from pathlib import Path
import re
import sys

import yaml

from historical_evidence import validate_historical_evidence


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "ci/evidence/artist/historical/unity6-urp-primary-visual-evidence.yaml"


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def require_status(node: dict, key: str, context: str) -> None:
    if node.get(key) != "passed":
        fail(f"{context}.{key} must be passed")


def main() -> int:
    validate_historical_evidence(EVIDENCE)
    if not EVIDENCE.is_file():
        fail(f"missing evidence file: {EVIDENCE.relative_to(ROOT)}")
    data = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8")) or {}
    if data.get("product") != "UnityArtistCLI" or data.get("case") != "unity-6-urp-primary-visual" or data.get("status") != "passed":
        fail("primary URP evidence identity/status is invalid")
    editor = data.get("editor", {})
    if editor.get("transport") != "official_unity_cli_pipeline" or data.get("support", {}).get("compatibility_backend") != "urp_native_api":
        fail("primary URP evidence must use Official Unity CLI/Pipeline and the URP native adapter")
    if data.get("fixture_authoring", {}).get("no_yaml_edit") is not True:
        fail("fixture authoring must explicitly record no Unity YAML edit")
    if data.get("fixture_authoring", {}).get("scene_save_command") != "save_all":
        fail("fixture persistence must use the official save_all command")

    flow = data.get("artist_flow", {})
    require_status(flow.get("inspect", {}), "status", "artist_flow.inspect")
    for name in ("initial_capture", "before_capture", "final_capture"):
        capture = flow.get(name, {})
        require_status(capture, "status", f"artist_flow.{name}")
        if capture.get("verified") is not True or capture.get("resolution") != "1920x1080":
            fail(f"{name} must be a verified 1920x1080 capture")
        if not re.fullmatch(r"[0-9a-f]{64}", str(capture.get("png_sha256", ""))):
            fail(f"{name} must contain a SHA-256 digest")
    if flow["before_capture"].get("capture_id") == flow["final_capture"].get("capture_id"):
        fail("before and final captures must be distinct")

    volume = flow.get("volume_lookdev", {})
    for key in ("plan_status", "preview_status", "approval_guard", "applied_status"):
        require_status(volume, key, "artist_flow.volume_lookdev")
    if volume.get("applied_verified") is not True or len(volume.get("exact_diff", [])) != 2:
        fail("URP Volume evidence must include two verified ColorAdjustments changes")
    profile = volume.get("profile_inspection", {})
    if profile.get("status") != "passed" or profile.get("component_type") != "ColorAdjustments" or profile.get("component_count") != 1:
        fail("URP Volume profile inspection is incomplete")

    direction = flow.get("direction", {})
    for key in ("plan_status", "preview_status", "approval_guard", "applied_status"):
        require_status(direction, key, "artist_flow.direction")
    if direction.get("applied_verified") is not True or len(direction.get("exact_diff", [])) != 2:
        fail("direction apply evidence must include two verified exact changes")

    refine = flow.get("refine", {})
    for key in ("plan_status", "preview_status", "approval_guard", "applied_status"):
        require_status(refine, key, "artist_flow.refine")
    if refine.get("exact_diff", {}).get("property") != "fieldOfView":
        fail("refine evidence must document the camera FOV change")

    review = flow.get("intermediate_review", {})
    if review.get("status") != "passed" or review.get("decision") != "needs_refine" or review.get("human_review") is not True:
        fail("intermediate visual review must be an explicit needs_refine decision")
    final_review = flow.get("final_review", {})
    if final_review.get("status") != "passed" or final_review.get("decision") != "accepted" or final_review.get("human_review") is not True:
        fail("final visual review must be an explicit accepted decision")
    timeline = flow.get("timeline", {})
    if timeline.get("status") != "passed" or timeline.get("tracks") != 3 or timeline.get("brain_bindings") != 3 or timeline.get("virtual_camera_references") != 3:
        fail("Timeline evidence must contain three tracks, Brain bindings, and virtual-camera references")
    print("Historical record validation only; current Editor: BLOCKED_NOT_RUN/not_observed")
    print("Historical Unity 6 URP primary visual evidence contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
