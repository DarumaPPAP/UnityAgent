#!/usr/bin/env python3
"""Artist manifest / CLI / UPM version, GUID and identity contract."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors: list[str] = []
    manifest = yaml.safe_load((ROOT / "subagent/artist_subagent/manifest.yaml").read_text(encoding="utf-8"))
    version = manifest["identity"]["version"]
    if manifest["identity"]["id"] != "artist_subagent" or manifest["execution"]["kind"] != "provider_backed":
        errors.append("Artist manifest identity/execution kind changed")
    if manifest["installation"].get("auto_install") or manifest["installation"].get("required"):
        errors.append("Artist must not auto-install or become mandatory")
    package_root = ROOT / "subagent/artist_subagent/tools/editor"
    package = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "com.darumappap.artist-subagent" or package.get("version") != version or package.get("unity") != "6000.0":
        errors.append("Artist UPM identity/version/unity mismatch")
    csproj = (ROOT / "subagent/artist_subagent/tools/host/UnityArtist.Tools.csproj").read_text(encoding="utf-8")
    if f"<Version>{version}</Version>" not in csproj or "<AssemblyName>unity-artist</AssemblyName>" not in csproj:
        errors.append("Artist CLI csproj identity/version mismatch")
    program = (ROOT / "subagent/artist_subagent/tools/host/Program.cs").read_text(encoding="utf-8")
    constants = re.findall(r'private const string (?:Version|SemanticVersion) = "([^"]+)";', program)
    if constants != [version, version]:
        errors.append("Artist Program.Version and SemanticVersion must match the manifest")
    for child in package_root.rglob("*"):
        if child.suffix not in {".cs", ".asmdef", ".json"} or child.name.endswith(".meta"):
            continue
        # Only authored Unity assets need their meta. Non-Unity configuration does not.
        if child.name in {"package.json"}:
            pass
        if not Path(str(child) + ".meta").is_file():
            errors.append(f"Missing .meta: {child.relative_to(ROOT)}")
    required_guids = {}
    for path in package_root.rglob("*.meta"):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^guid: ([0-9a-f]{32})$", text)
        if not match:
            errors.append(f"Bad Unity meta GUID: {path.relative_to(ROOT)}")
            continue
        if match.group(1) in required_guids:
            errors.append(f"Duplicate Unity meta GUID: {path.relative_to(ROOT)}")
        required_guids[match.group(1)] = path
    return errors


if __name__ == "__main__":
    problems = validate()
    for issue in problems:
        print(issue, file=sys.stderr)
    print("Artist co-located backend identity: " + ("PASS" if not problems else "FAIL"))
    raise SystemExit(bool(problems))
