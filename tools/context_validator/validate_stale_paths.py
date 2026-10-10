#!/usr/bin/env python3
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path

CANONICAL_SCAN_ROOTS = (
    Path("AGENTS.md"), Path("src/unityagent/policy"), Path("src/unityagent/context/assembly"), Path("src/unityagent/context/budget"),
    Path("src/unityagent/context/compression"), Path("src/unityagent/context/contracts"), Path("src/unityagent/context/manifest"),
    Path("src/unityagent/context/selection"), Path("src/unityagent/context/validators"), Path("tests/context"),
    Path("src/unityagent/runtime/permissions"),
)
REFERENCE_EXEMPT_PREFIXES = (
    "src/unityagent/context/compatibility/",
    "src/unityagent/context/packs/",
    "src/unityagent/context/retrieval/knowledge/",
    "eval/compatibility/",
    "eval/datasets/",
    "docs/migration/",
)
REFERENCE_EXEMPT_FILES = {
    "src/unityagent/context/budget/_compat_engine.py",
    "src/unityagent/context/budget/_compat_validation.py",
}
LEGACY_MARKER = "." + "ai/"
LEGACY_WRITE_RE = re.compile(r"(write_text|write_bytes|open\s*\(|unlink|rename|replace)")


def _iter_files(root: Path):
    for target in CANONICAL_SCAN_ROOTS:
        path = root / target
        if path.is_file():
            yield path
        elif path.is_dir():
            for item in path.rglob("*"):
                if item.is_file() and item.suffix.lower() in {".py", ".yaml", ".yml", ".md", ".json"}:
                    yield item


def _reference_exempt(rel: str) -> bool:
    return rel in REFERENCE_EXEMPT_FILES or rel.startswith(REFERENCE_EXEMPT_PREFIXES)


def validate_static(root: Path = Path(".")) -> list[str]:
    errors: list[str] = []
    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        if _reference_exempt(rel):
            continue
        text = path.read_text(encoding="utf-8")
        if LEGACY_MARKER in text:
            errors.append(f"direct legacy path in canonical surface: {rel}")
    return errors


def validate_added_lines(root: Path = Path("."), base_ref: str | None = None) -> list[str]:
    errors: list[str] = []
    if not (root / ".git").exists():
        return errors
    base_ref = base_ref or os.environ.get("CUTOVER_BASE_REF") or "HEAD^"
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--unified=0", base_ref, "HEAD", "--"],
            cwd=root,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        return errors

    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        if LEGACY_MARKER not in added:
            continue

        if not current.startswith(LEGACY_MARKER) and not _reference_exempt(current):
            errors.append(f"new direct legacy path reference: {current}: {added.strip()}")

        # Historical/compatibility data may retain legacy provenance for replay,
        # but no new code path may write through a legacy reference.
        if not current.startswith(LEGACY_MARKER) and LEGACY_WRITE_RE.search(added):
            errors.append(f"new legacy write operation: {current}: {added.strip()}")
    return errors


if __name__ == "__main__":
    failures = validate_static() + validate_added_lines()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Stale legacy path guard: OK")
