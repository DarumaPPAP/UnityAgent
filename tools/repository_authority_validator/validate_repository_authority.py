#!/usr/bin/env python3
"""UnityAgentのRepository Authorityと重複Version宣言を検証する。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "src/unityagent/contracts/repository-authority-map.yaml"
EXPECTED_REPOSITORY = "DarumaPPAP/UnityAgent"
EXPECTED_HUB = "DarumaPPAP/UnitySubAgentHub"


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a mapping")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return value


def _pep440_version(version: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)(\d*))?", version)
    if match is None:
        raise ValueError(f"unsupported VERSION format: {version}")
    base, label, number = match.groups()
    if label is None:
        return base
    suffix = {"alpha": "a", "beta": "b", "rc": "rc"}[label]
    return f"{base}{suffix}{number or '0'}"


def _pyproject_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    if project_match is None:
        raise ValueError("pyproject.toml is missing [project]")
    version_match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project_match.group(1))
    if version_match is None:
        raise ValueError("pyproject.toml [project] is missing version")
    return version_match.group(1)


def _require_path(relative: str, errors: list[str]) -> None:
    path = ROOT / relative
    if not path.exists():
        errors.append(f"authority path does not exist: {relative}")


def validate_repository() -> list[str]:
    errors: list[str] = []

    try:
        authority = _load_yaml(MAP_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"cannot read src/unityagent/contracts/repository-authority-map.yaml: {exc}"]

    if authority.get("schema_version") != "1.0":
        errors.append("authority map schema_version must be 1.0")
    if authority.get("kind") != "repository_authority_map":
        errors.append("authority map kind must be repository_authority_map")
    if authority.get("repository") != EXPECTED_REPOSITORY:
        errors.append(f"authority map repository must be {EXPECTED_REPOSITORY}")

    authorities = authority.get("authorities")
    if not isinstance(authorities, dict):
        return errors + ["authority map authorities must be a mapping"]

    product_version = authorities.get("product_version")
    if not isinstance(product_version, dict):
        return errors + ["authorities.product_version must be a mapping"]

    source = product_version.get("source")
    mirrors = product_version.get("mirrors")
    if source != "VERSION":
        errors.append("VERSION must remain the canonical product version source")
    if not isinstance(mirrors, dict):
        return errors + ["authorities.product_version.mirrors must be a mapping"]

    path_keys = (
        "architecture_boundary",
        "policy",
        "routing_and_orchestration",
        "runtime_provider_registry",
        "consumer_subagent_catalog",
        "subagent_source_lock",
        "durable_state_and_evidence",
        "evaluation",
    )
    _require_path("VERSION", errors)
    for key in path_keys:
        value = authorities.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"authorities.{key} must be a repository-relative path")
            continue
        _require_path(value, errors)
    for name, value in mirrors.items():
        if not isinstance(value, str) or not value:
            errors.append(f"product version mirror {name} must be a repository-relative path")
            continue
        _require_path(value, errors)

    external = authority.get("external_authorities")
    optional_metadata = external.get("optional_subagent_metadata") if isinstance(external, dict) else None
    if not isinstance(optional_metadata, dict):
        errors.append("external_authorities.optional_subagent_metadata must be a mapping")
    else:
        if optional_metadata.get("repository") != EXPECTED_HUB:
            errors.append(f"optional SubAgent metadata authority must be {EXPECTED_HUB}")
        pinned_by = optional_metadata.get("pinned_by")
        if not isinstance(pinned_by, str) or not pinned_by:
            errors.append("optional SubAgent metadata must declare pinned_by")
        else:
            _require_path(pinned_by, errors)

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    try:
        expected_python = _pep440_version(version)
    except ValueError as exc:
        errors.append(str(exc))
        expected_python = ""

    try:
        python_version = _pyproject_version(ROOT / "pyproject.toml")
        if expected_python and python_version != expected_python:
            errors.append(f"pyproject.toml version {python_version!r} does not mirror VERSION {version!r}")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    json_version_paths = (
        "Packages/com.darumappap.unity-agent/package.json",
        ".agents/plugins/unity-agent/plugin.json",
        ".agents/plugins/unity-agent/.codex-plugin/plugin.json",
    )
    for relative in json_version_paths:
        try:
            declared = _read_json(ROOT / relative).get("version")
            if declared != version:
                errors.append(f"{relative} version {declared!r} does not mirror VERSION {version!r}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: {exc}")

    try:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        shield_version = version.replace("-", "--")
        expected_badge = f"img.shields.io/badge/version-{shield_version}-blue"
        if expected_badge not in readme:
            errors.append(f"README version badge does not mirror VERSION {version!r}")
        if f"#v{version}" not in readme:
            errors.append(f"README UPM install reference does not mirror VERSION {version!r}")
        if f"--ref v{version}" not in readme:
            errors.append(f"README Codex marketplace reference does not mirror VERSION {version!r}")
    except OSError as exc:
        errors.append(f"README.md: {exc}")

    lock_relative = authorities.get("subagent_source_lock")
    if isinstance(lock_relative, str):
        try:
            lock = _read_json(ROOT / lock_relative)
            hub = lock.get("hub")
            if not isinstance(hub, dict):
                errors.append(f"{lock_relative} hub must be an object")
            else:
                if hub.get("repository") != EXPECTED_HUB:
                    errors.append(f"{lock_relative} must pin {EXPECTED_HUB}")
                commit = hub.get("commit")
                if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
                    errors.append(f"{lock_relative} hub.commit must be a full commit SHA")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{lock_relative}: {exc}")

    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"Repository authority validation: {len(errors)} error(s)")
        return 1
    print("Repository authority validation: 0 error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
