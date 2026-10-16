#!/usr/bin/env python3
"""Fail-closed P9 qualification of GitHub Actions evidence before publishing a beta tag."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

EDITOR = "6000.3.12f1"
FIXTURE = "p9-lts-urp"
WORKFLOW = "UnityAgent P9 Release Verification"
REQUIRED = ("editor.log", "results.xml", "packages-lock.json", "pipeline-smoke.png",
            "graphics-device.json", "editor-version.txt")


def verify(evidence_directory: Path, run_metadata: dict, source_sha: str, repo: str, run_id: int):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Release candidate source SHA must be full length")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Private evidence repository must be owner/name")
    if run_id < 1:
        raise ValueError("P9 run ID must be positive")
    if (run_metadata.get("id") != run_id
            or (run_metadata.get("repository") or {}).get("full_name") != repo
            or run_metadata.get("name") != WORKFLOW
            or run_metadata.get("event") != "workflow_dispatch"
            or run_metadata.get("head_branch") != "main"
            or run_metadata.get("conclusion") != "success"
            or run_metadata.get("status") != "completed"
            or "/.github/workflows/p9-release-verification.yml@" not in run_metadata.get("path", "")):
        raise ValueError("P9 evidence is not from an approved, completed private workflow_dispatch on main")
    report_path = evidence_directory / "evidence.json"
    if not report_path.is_file():
        raise ValueError("Missing measured Unity Editor evidence")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("status") != "PASS" or report.get("observation") != "observed"
            or report.get("fixture") != FIXTURE or report.get("pipeline") != "urp"
            or report.get("requested_editor") != EDITOR
            or report.get("observed_editor") != EDITOR
            or report.get("editor_test_process_started") is not True
            or report.get("source_changed_during_execution") is not False
            or report.get("run_id") != str(run_id)
            or report.get("source_identity", {}).get("commit") != source_sha):
        raise ValueError("P9 evidence is missing, blocked or belongs to a different revision/run")
    if not isinstance(report.get("tests_passed"), int) or report["tests_passed"] <= 0:
        raise ValueError("No successful Unity Editor tests observed")
    observation = report.get("graphics_observation")
    if (not isinstance(observation, dict) or observation.get("editorVersion") != EDITOR
            or not observation.get("deviceType") or observation["deviceType"] == "Null"
            or float(observation.get("pixelVariation", 0)) <= 0.1):
        raise ValueError("Measured URP graphics evidence is missing")
    hashes = report.get("artifact_hashes")
    if not isinstance(hashes, dict):
        raise ValueError("Evidence lacks output hash inventory")
    for filename in REQUIRED:
        path = evidence_directory / filename
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Required measured evidence missing: " + filename)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes.get(filename) != actual:
            raise ValueError("Evidence hash mismatch: " + filename)
    if not (evidence_directory / "pipeline-smoke.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("GPU capture is not a PNG")
    test_run = ET.parse(evidence_directory / "results.xml").getroot()
    if test_run.tag != "test-run" or test_run.get("result") != "Passed":
        raise ValueError("NUnit suite was not successful")
    cases = test_run.findall(".//test-case")
    if len(cases) != report["tests_passed"] or not all(c.get("result") == "Passed" for c in cases):
        raise ValueError("NUnit test count/result disagrees with measured evidence")
    packages = json.loads((evidence_directory / "packages-lock.json").read_text(encoding="utf-8"))
    package_version = packages.get("dependencies", {}).get("com.unity.render-pipelines.universal", {}).get("version")
    if package_version != "17.3.0":
        raise ValueError("P9 URP package version does not match G1-compatible LTS baseline")
    if report.get("resolved_packages", {}).get("com.unity.render-pipelines.universal", {}).get("version") != package_version:
        raise ValueError("Reported and locked URP versions disagree")
    return {"source_sha": source_sha, "editor": EDITOR, "fixture": FIXTURE,
            "p9_run_id": run_id, "p9_private_repo": repo, "tests_passed": len(cases),
            "status": "P9_EDITOR_VERIFIED", "g1_status": "BLOCKED_NOT_RUN"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args()
    try:
        result = verify(args.evidence, json.loads(args.run_metadata.read_text(encoding="utf-8")),
                        args.source_sha, args.repository, args.run_id)
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as error:
        print("P9 RELEASE BLOCKED: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
