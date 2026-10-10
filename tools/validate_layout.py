#!/usr/bin/env python3
"""Enforce repository layout ownership; domain authority remains a separate contract."""
from __future__ import annotations
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def validate(root: Path = ROOT, tracked_paths: list[str] | None = None) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    try:
        config = json.loads((root / 'repository-layout.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [f'cannot read layout contract: {exc}']
    if config.get('schema_version') != '1.0':
        errors.append('layout schema_version must be 1.0')
    allowed = config.get('allowed_roots')
    canonical = config.get('canonical_paths')
    if not isinstance(allowed, dict) or not isinstance(canonical, dict):
        return errors + ['allowed_roots and canonical_paths must map paths to owners']
    for section in (allowed, canonical):
        for relative, owner in section.items():
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in relative:
                errors.append(f'layout path must be repository confined: {relative}')
            if not isinstance(owner, str) or not owner.strip():
                errors.append(f'layout path needs an owner: {relative}')
    authority = config.get('authority_map')
    if not isinstance(authority, str) or authority == 'repository-layout.json' or authority not in canonical:
        errors.append('domain authority_map must be a separate canonical path')
    for relative in canonical:
        path = root / relative
        if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
            errors.append(f'canonical path must be repository confined: {relative}')
        elif not path.exists():
            errors.append(f'canonical path missing: {relative}')
    forbidden_roots = config.get('forbidden_roots', [])
    for name in forbidden_roots:
        if (root / name).exists():
            errors.append(f'forbidden root exists: {name}')
    if tracked_paths is None:
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], capture_output=True, text=True)
        if result.returncode:
            return errors + ['Git inventory unavailable: layout validation cannot be skipped']
        tracked_paths = result.stdout.split('\0')
    forbidden_names = set(config.get('forbidden_directory_names', []))
    generated = {'.git', 'Library', 'Temp', 'bin', 'obj', 'node_modules', '__pycache__', 'build', 'dist', '.venv'}
    for directory, children, _ in os.walk(root):
        for name in children:
            if name in forbidden_names:
                errors.append(f'forbidden directory exists: {(Path(directory) / name).relative_to(root)}')
        children[:] = [name for name in children if name not in generated and name not in forbidden_names]
    for relative in sorted(set(tracked_paths)):
        if not relative:
            continue
        path = PurePosixPath(relative)
        authored = root / relative
        if not authored.resolve().is_relative_to(root):
            errors.append(f'authored path must be repository confined: {relative}')
        if authored.is_symlink() and not authored.exists():
            errors.append(f'dangling authored symlink: {relative}')
        if path.parts[0] not in allowed:
            errors.append(f'unknown root: {path.parts[0]} ({relative})')
        if path.parts[0] in forbidden_roots:
            errors.append(f'forbidden root in Git inventory: {relative}')
        if any(part in forbidden_names for part in path.parts[:-1]):
            errors.append(f'forbidden directory in Git inventory: {relative}')
    return errors

if __name__ == '__main__':
    errors = validate()
    for error in errors:
        print(error, file=sys.stderr)
    print('Repository layout: ' + ('FAIL' if errors else 'PASS'))
    raise SystemExit(bool(errors))
