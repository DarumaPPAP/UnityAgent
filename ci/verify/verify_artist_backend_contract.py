#!/usr/bin/env python3
"""Canonical static contract gate for the co-located ArtistSubAgent backend source."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

from historical_evidence import validate_historical_evidence

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PATH = ROOT / "Packages/com.darumappap.artist-subagent/package.json"
CLI_PROJECT = ROOT / "cli/artist/UnityArtist.Cli.csproj"
CLI_SOURCE = ROOT / "cli/artist/Program.cs"
EDITOR_ROOT = ROOT / "Packages/com.darumappap.artist-subagent/Editor"
MATRIX_PATH = ROOT / "ci/compatibility/support-matrix.yaml"
GATE_EVIDENCE_PATH = ROOT / "ci/evidence/artist/historical/cli-pipeline-gate-evidence.yaml"
CLI_REFERENCE_AUDIT_PATH = ROOT / "ci/evidence/artist/historical/unity-cli-reference-audit.yaml"
MANIFEST_PATH = ROOT / "Hub/SubAgents/artist_subagent/manifest.yaml"
SURFACE_PATH = ROOT / "Hub/SubAgents/artist_subagent/contracts/backend-surface-contract.yaml"
BACKEND_CONTRACT_PATH = ROOT / "cli/artist/artist-backend-contract.yaml"
REPO_SKILLS_ROOT = ROOT / ".agents/skills"
LEGACY_PLUGIN_ROOT = ROOT / ".agents/plugins/unity-artist"

REQUIRED_COMMANDS = {
    "help", "version", "doctor", "capabilities", "install", "inspect", "plan",
    "preview", "apply", "capture", "evaluate", "refine", "history", "cinematic",
}
FORBIDDEN_SOURCE_TOKENS = (
    "com.coplaydev.unity-mcp",
    "McpForUnityTool",
    "MCPForUnity",
    "using Unity.MCP",
    "AutoRegister",
)
EXPECTED_ROWS = {
    ("Unity 6.x+", "builtin"),
    ("Unity 6.x+", "urp"),
    ("Unity 6.x+", "hdrp"),
}


def error(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"[ERROR] {message}")


def read_json(errors: list[str], path: Path) -> dict:
    if not path.is_file():
        error(errors, f"missing JSON file: {path.relative_to(ROOT)}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        error(errors, f"invalid JSON {path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(value, dict):
        error(errors, f"JSON root must be an object: {path.relative_to(ROOT)}")
        return {}
    return value


def read_yaml(errors: list[str], path: Path) -> dict:
    if not path.is_file():
        error(errors, f"missing YAML file: {path.relative_to(ROOT)}")
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        error(errors, f"invalid YAML {path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(value, dict):
        error(errors, f"YAML root must be a mapping: {path.relative_to(ROOT)}")
        return {}
    return value


def check_identity(errors: list[str]) -> None:
    package = read_json(errors, PACKAGE_PATH)
    version = str(package.get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        error(errors, f"Artist backend package version must be semantic, got {version!r}")
    if package.get("name") != "com.darumappap.artist-subagent":
        error(errors, "current package name is not com.darumappap.artist-subagent")
    dependencies = package.get("dependencies") or {}
    if dependencies:
        error(errors, f"current package dependencies must be empty; Pipeline is an explicit setup dependency, got {sorted(dependencies)}")
    if package.get("unity") != "6000.0":
        error(errors, "package minimum Unity version must be 6000.0")


def check_cli_surface(errors: list[str]) -> None:
    source = CLI_SOURCE.read_text(encoding="utf-8") if CLI_SOURCE.is_file() else ""
    command_block = re.search(r"SupportedCommands.*?\{(?P<body>.*?)\};", source, re.DOTALL)
    commands = set(re.findall(r'"([a-z]+)"', command_block.group("body") if command_block else ""))
    missing = sorted(REQUIRED_COMMANDS - commands)
    if missing:
        error(errors, f"CLI is missing commands: {missing}")
    if '"official_unity_cli_pipeline"' not in source:
        error(errors, "CLI does not declare official_unity_cli_pipeline transport")
    if '"pipeline", "install"' not in source or '"command"' not in source:
        error(errors, "CLI does not expose install and official Pipeline command delegation")
    if not CLI_PROJECT.is_file():
        error(errors, "CLI project file is missing")
    else:
        project = CLI_PROJECT.read_text(encoding="utf-8")
        package = read_json(errors, PACKAGE_PATH)
        version = str(package.get("version") or "")
        if f"<Version>{version}</Version>" not in project:
            error(errors, "CLI project version disagrees with Artist backend package version")
    package = read_json(errors, PACKAGE_PATH)
    version = str(package.get("version") or "")
    if f'private const string Version = "{version}";' not in source:
        error(errors, "CLI Version constant disagrees with Artist backend package version")
    if f'private const string SemanticVersion = "{version}";' not in source:
        error(errors, "CLI SemanticVersion constant disagrees with Artist backend package version")


def check_editor_surface(errors: list[str]) -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in EDITOR_ROOT.rglob("*.cs")) if EDITOR_ROOT.is_dir() else ""
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token in sources:
            error(errors, f"forbidden legacy/MCP token remains in current Editor source: {token}")
    if "CliCommand" not in sources or "Unity.Pipeline.Commands" not in sources:
        error(errors, "current Editor package does not expose official Pipeline CliCommand registrations")
    for command in ("artist.inspect", "artist.plan", "artist.preview", "artist.apply", "artist.capture", "artist.evaluate", "artist.refine", "artist.cinematic", "artist.history"):
        if command not in sources:
            error(errors, f"missing Pipeline command registration: {command}")
    for token in ("CinematicRequest", "InspectCinematicDirector", "CreateTrack", "CreateMarker", "SetGenericBinding", "Undo.RecordObject", "depth_channel", "object_id_channel"):
        if token not in sources:
            error(errors, f"current Editor source is missing bounded Artist/Cinematic contract token: {token}")
    compatibility = EDITOR_ROOT / "Compatibility/ArtistCompatibility.cs"
    compatibility_tests = ROOT / "Packages/com.darumappap.artist-subagent/Tests/Editor/ArtistCompatibilityTests.cs"
    for path in (compatibility, compatibility_tests):
        if not path.is_file() or not Path(str(path) + ".meta").is_file():
            error(errors, f"compatibility asset or .meta is missing: {path.relative_to(ROOT)}")


def check_matrix(errors: list[str]) -> None:
    matrix = read_yaml(errors, MATRIX_PATH)
    rows = matrix.get("rows") or []
    actual = {(str(row.get("unity_version")), str(row.get("render_pipeline"))) for row in rows if isinstance(row, dict)}
    if actual != EXPECTED_ROWS:
        error(errors, f"formal support matrix drifted: {sorted(actual)}")
    if matrix.get("transport") != "official_unity_cli_pipeline":
        error(errors, "matrix transport must remain official_unity_cli_pipeline")
    if matrix.get("verification_contract", {}).get("unsupported_result_before_mutation") is not True:
        error(errors, "unsupported result before mutation is not required")


def check_cli_pipeline_gate_evidence(errors: list[str]) -> None:
    evidence = read_yaml(errors, GATE_EVIDENCE_PATH)
    if evidence.get("case") != "unity-2022.3-builtin":
        error(errors, "CLI/Pipeline gate evidence must cover the 2022.3 Built-in case")
    candidate = evidence.get("official_first_candidate") or {}
    if candidate.get("transport") != "official_unity_cli_pipeline":
        error(errors, "2022.3 gate evidence must record Official Unity CLI + Pipeline as first candidate")
    pipeline = candidate.get("pipeline") or {}
    if pipeline.get("failure_class") != "concrete_cli_pipeline_gate_failure":
        error(errors, "2022.3 gate evidence must preserve a concrete Pipeline gate failure")
    plugin = evidence.get("artist_plugin") or {}
    if plugin.get("version_status") != "passed" or plugin.get("help_status") != "passed":
        error(errors, "Artist plugin version/help command evidence is incomplete")
    if plugin.get("global_help_status") != "blocked_by_official_cli_global_parser":
        error(errors, "global unity artist --help behavior must remain explicitly recorded")
    fallback = evidence.get("fallback_evaluation") or {}
    if fallback.get("selected") is not True or fallback.get("status") != "verified_bounded_non_mcp":
        error(errors, "2022.3 bounded fallback selection/evidence is incomplete")


def check_cli_reference_audit(errors: list[str]) -> None:
    audit = read_yaml(errors, CLI_REFERENCE_AUDIT_PATH)
    if audit.get("schema_version") != "1.0":
        error(errors, "Unity CLI reference audit schema version must be 1.0")
    if audit.get("documented_release") != "1.0.0-beta.10":
        error(errors, "Unity CLI reference audit must record the current documented release")
    observation = audit.get("runtime_observation") or {}
    if observation.get("status") != "not_observed" or observation.get("historical_evidence_preserved") is not True:
        error(errors, "Unity CLI reference audit must distinguish documentation from runtime observation")
    required_urls = {
        "https://docs.unity.com/en-us/unity-cli",
        "https://docs.unity.com/en-us/unity-cli/unity-cli-reference",
        "https://docs.unity.com/en-us/unity-cli/release-notes",
        "https://docs.unity.com/en-us/unity-production-pipeline/local-tools-cli/unity-pipeline-package",
    }
    actual_urls = {
        str(source.get("url"))
        for source in audit.get("sources", [])
        if isinstance(source, dict)
    }
    missing_urls = sorted(required_urls - actual_urls)
    if missing_urls:
        error(errors, f"Unity CLI reference audit is missing official sources: {missing_urls}")
    scope = audit.get("audit_scope") or {}
    forbidden_hub_ownership = {"runtime_execution", "resolver", "installer", "environment_observation", "automatic_installation"}
    if not forbidden_hub_ownership.issubset(set(scope.get("hub_does_not_own") or [])):
        error(errors, "Unity CLI reference audit weakens the Hub boundary")
    if "1.0.0-beta.8" not in set(scope.get("historical_versions_to_preserve") or []):
        error(errors, "historical beta.8 evidence must remain explicitly preserved")


def check_catalog(errors: list[str]) -> None:
    manifest = read_yaml(errors, MANIFEST_PATH)
    surface = read_yaml(errors, SURFACE_PATH)
    backend_contract = read_yaml(errors, BACKEND_CONTRACT_PATH)
    identity = manifest.get("identity") or {}
    if manifest.get("kind") != "subagent_manifest" or identity.get("name") != "ArtistSubAgent":
        error(errors, "canonical ArtistSubAgent manifest identity is invalid")
    package = read_json(errors, PACKAGE_PATH)
    version = str(package.get("version") or "")
    if identity.get("id") != "artist_subagent" or str(identity.get("version")) != version:
        error(errors, "canonical SubAgent id or version disagrees with Artist backend package version")
    if manifest.get("lifecycle") != "active":
        error(errors, "ArtistSubAgent manifest must remain active")
    install = manifest.get("installation") or {}
    if install.get("mode") != "optional" or install.get("required") is not False or install.get("auto_install") is not False:
        error(errors, "ArtistSubAgent must remain optional and no-auto-install")
    activation = manifest.get("activation") or {}
    if activation.get("false_behavior") != "exclude_from_resolution" or activation.get("unknown_behavior") != "exclude_from_resolution":
        error(errors, "false or unknown ArtistSubAgent activation must be excluded from resolution")
    compatibility = manifest.get("compatibility") or {}
    targets = compatibility.get("supported_targets") or []
    actual_targets = {
        (str(target.get("unity_version")), str(target.get("render_pipeline")))
        for target in targets if isinstance(target, dict)
    }
    if actual_targets != EXPECTED_ROWS:
        error(errors, "manifest supported version/pipeline pairs disagree with the Artist support matrix")
    backends = manifest.get("backends") or []
    backend_ids = [backend.get("id") for backend in backends if isinstance(backend, dict)]
    if "unity_artist_cli" not in backend_ids or identity.get("id") in backend_ids:
        error(errors, "unity_artist_cli must remain a backend id distinct from the specialist")
    if surface.get("kind") != "specialist_backend_interface" or surface.get("backend_identity") != "unity_artist_cli":
        error(errors, "Artist backend interface identity is invalid")
    if surface.get("execution_boundary") != "unity_agent_tool_broker":
        error(errors, "Artist backend must execute through UnityAgent ToolBroker")
    if set(surface.get("forbidden_authority") or []) != {"global_routing", "policy", "approval", "provider_resolution", "retry_control", "persistence"}:
        error(errors, "Artist backend interface must not own Control Plane authority")
    if surface.get("context_receipt") != ["generated", "transported", "received"]:
        error(errors, "Artist backend interface must declare the context receipt lifecycle")
    if set(backend_contract.get("backend_commands") or []) != REQUIRED_COMMANDS:
        error(errors, "backend command set disagrees with CLI contract")
    forbidden = set(backend_contract.get("forbidden_surface") or [])
    if not {"mcp_transport", "generic_gameobject_crud", "generic_hierarchy_crud", "arbitrary_eval"}.issubset(forbidden):
        error(errors, "backend contract must continue to forbid MCP and generic CRUD/eval")
    if backend_contract.get("automatic_save") is not False or backend_contract.get("arbitrary_eval") is not False:
        error(errors, "Artist backend contract must disable automatic save and arbitrary eval")

def check_agent_distribution(errors: list[str]) -> None:
    if LEGACY_PLUGIN_ROOT.exists():
        error(errors, "standalone .agents/plugins/unity-artist surface must be removed")
    expected = {
        "artist-subagent-cinematic-evidence",
        "artist-subagent-lookdev-refine",
        "artist-subagent-backend-setup",
    }
    actual = {
        path.parent.name
        for path in REPO_SKILLS_ROOT.rglob("SKILL.md")
        if path.parent.name.startswith("artist-subagent-")
    } if REPO_SKILLS_ROOT.is_dir() else set()
    missing = sorted(expected - actual)
    if missing:
        error(errors, f"repo-scoped ArtistSubAgent skills are missing: {missing}")
    production_roots = [
        ROOT / ".agents",
        ROOT / "Hub",
        ROOT / "docs",
        ROOT / "Packages",
        ROOT / "cli",
    ]
    if any(
        path.name == ".mcp.json"
        for production_root in production_roots
        if production_root.exists()
        for path in production_root.rglob("*")
    ):
        error(errors, "ArtistSubAgent production surface must not contain .mcp.json")


def check_legacy_anchor(errors: list[str]) -> None:
    fixture_root = ROOT / "tests/fixtures/legacy/MyUnityMCP-v1.1.1"
    package = read_json(errors, fixture_root / "package-metadata.json")
    provenance = read_json(errors, fixture_root / "provenance.json")
    package_value = package.get("package") if isinstance(package, dict) else {}
    if not isinstance(package_value, dict) or package_value.get("version") != "1.1.1":
        error(errors, "frozen Legacy package metadata must remain MyUnityMCP v1.1.1")
    if provenance.get("release") != "v1.1.1":
        error(errors, "frozen Legacy provenance release must remain v1.1.1")
    if provenance.get("release_commit_sha") != "ea437f11bcf5b46b6a7575f9d2f9b81a9c02da7c":
        error(errors, "frozen Legacy release commit drifted")
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/tags/v1.1.1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error(errors, "immutable v1.1.1 tag is not present locally")


def main() -> int:
    validate_historical_evidence()
    errors: list[str] = []
    check_identity(errors)
    check_cli_surface(errors)
    check_editor_surface(errors)
    check_matrix(errors)
    check_cli_pipeline_gate_evidence(errors)
    check_cli_reference_audit(errors)
    check_catalog(errors)
    check_agent_distribution(errors)
    check_legacy_anchor(errors)
    print(f"ArtistSubAgent backend contract: {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
