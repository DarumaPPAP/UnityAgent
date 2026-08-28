#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def _load_resolver():
    path = ROOT / "Context/Compatibility/path_resolver.py"
    spec = importlib.util.spec_from_file_location("phase2_policy_path_resolver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load compatibility path resolver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(root: Path = ROOT) -> list[str]:
    resolver = _load_resolver()
    errors: list[str] = []
    pairs = (
        ("compatibility://migration-source/user-policy", "Policy/User/user-policy.yaml", "user policy"),
        ("compatibility://migration-source/risk-levels", "Policy/Risk/risk-levels.yaml", "risk policy"),
    )
    for legacy_ref, canonical_ref, label in pairs:
        legacy = resolver.resolve_for_read(legacy_ref, root)
        canonical = root / canonical_ref
        if not legacy.is_file():
            errors.append(f"missing migration source for {label}: {legacy_ref}")
            continue
        if not canonical.is_file():
            errors.append(f"missing canonical {label}: {canonical_ref}")
            continue
        if legacy.read_bytes() != canonical.read_bytes():
            errors.append(f"{label} is not lossless: source={sha(legacy)} canonical={sha(canonical)}")
    return errors

if __name__ == "__main__":
    failures = validate()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Policy migration equivalence: OK")
