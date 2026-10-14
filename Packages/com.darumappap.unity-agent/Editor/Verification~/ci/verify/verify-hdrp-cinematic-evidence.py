#!/usr/bin/env python3
"""Validate the checked-in Unity 6 HDRP Cinemachine/Timeline evidence contract."""
from __future__ import annotations

from pathlib import Path
import sys

import yaml

from historical_evidence import validate_historical_evidence


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "ci/evidence/artist/historical/unity6-hdrp-cinematic-evidence.yaml"


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    validate_historical_evidence(EVIDENCE)
    if not EVIDENCE.is_file():
        fail(f"missing evidence file: {EVIDENCE.relative_to(ROOT)}")
    data = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8")) or {}
    if data.get("product") != "UnityArtistCLI" or data.get("status") != "passed":
        fail("cinematic evidence must be a passed UnityArtistCLI result")
    if data.get("case") != "unity-6-hdrp-cinematic-timeline":
        fail("cinematic evidence case identifier drifted")
    if data.get("editor", {}).get("transport") != "official_unity_cli_pipeline":
        fail("cinematic evidence must use the official Unity CLI/Pipeline transport")
    if data.get("support", {}).get("compatibility_backend") != "hdrp_native_api":
        fail("cinematic evidence must use the HDRP native adapter")

    timeline = data.get("timeline", {})
    tracks = timeline.get("tracks", [])
    expected_tracks = {
        ("CinemachineShot01", "Main Camera"),
        ("CinemachineShot02", "Main Camera"),
        ("CinemachineShot03", "Main Camera"),
    }
    expected_cameras = {
        ("CinemachineShot01", "ShotCamera01"),
        ("CinemachineShot02", "ShotCamera02"),
        ("CinemachineShot03", "ShotCamera03"),
    }
    actual_tracks = {(row.get("name"), row.get("binding")) for row in tracks}
    actual_cameras = {(row.get("name"), row.get("shot_camera")) for row in tracks}
    if actual_tracks != expected_tracks or actual_cameras != expected_cameras:
        fail("cinematic evidence must contain three Brain bindings and three virtual-camera references")
    clips = {
        (row.get("track"), row.get("target"), row.get("clip_start"), row.get("clip_duration"))
        for row in data.get("operations", {}).get("shot_clips", [])
    }
    expected_clips = {
        ("CinemachineShot01", "ShotCamera01", 0.0, 0.5),
        ("CinemachineShot02", "ShotCamera02", 0.5, 0.5),
        ("CinemachineShot03", "ShotCamera03", 1.0, 0.5),
    }
    if clips != expected_clips:
        fail("cinematic evidence must contain exactly three timed Cinemachine shot clips")
    bindings = {(row.get("track"), row.get("target")) for row in data.get("operations", {}).get("brain_bindings", [])}
    if bindings != expected_tracks:
        fail("cinematic evidence must contain exactly three Main Camera CinemachineBrain bindings")
    if timeline.get("marker_track") != "Markers":
        fail("Timeline marker track evidence is missing")
    marker = timeline.get("marker_apply", {})
    required_marker_evidence = {"timeline_evidence", "timeline_marker", "mutation_evidence", "undo_registration", "save_not_performed"}
    if marker.get("status") != "passed" or not required_marker_evidence.issubset(marker.get("evidence", [])):
        fail("marker apply evidence is incomplete")
    for row in data.get("operations", {}).get("shot_clips", []) + data.get("operations", {}).get("brain_bindings", []):
        if row.get("apply") != "passed" or row.get("preview") != "passed" or row.get("approval_guard") != "passed":
            fail(f"cinematic lifecycle is incomplete: {row.get('track')}")
    if data.get("persistence", {}).get("fixture_save_command") != "save_all":
        fail("fixture persistence must use the official save_all command")
    print("Historical record validation only; current Editor: BLOCKED_NOT_RUN/not_observed")
    print("Historical Unity HDRP Cinemachine/Timeline evidence contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
