#!/usr/bin/env python3
"""Regression-check immutable Eval run directories without invoking Runtime."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "Artifacts" / "Eval" / "Behavior" / "runs"


class EvalRunIntegrityError(ValueError):
    pass


def _safe_run_root(run_id: str) -> Path:
    value = str(run_id or "").strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise EvalRunIntegrityError("run_id must be one safe path segment")
    root = DEFAULT_ROOT.resolve()
    candidate = (root / value).resolve()
    if candidate.parent != root:
        raise EvalRunIntegrityError("run_id escapes Eval run root")
    return candidate


def _create_fresh_run_root(run_root: Path) -> None:
    if run_root.exists():
        raise EvalRunIntegrityError("Eval run directories are immutable and cannot be reused")
    run_root.mkdir(parents=True, exist_ok=False)


def main() -> int:
    run_id = f"integrity-validator-{uuid.uuid4().hex}"
    run_root = _safe_run_root(run_id)

    try:
        _create_fresh_run_root(run_root)
        marker = run_root / "sentinel.txt"
        marker.write_text("original evidence\n", encoding="utf-8")

        try:
            _create_fresh_run_root(run_root)
        except EvalRunIntegrityError as exc:
            if "immutable" not in str(exc):
                print(f"[FAIL] Unexpected reuse error: {exc}")
                return 1
        else:
            print("[FAIL] Existing Eval run directory was reused.")
            return 1

        if marker.read_text(encoding="utf-8") != "original evidence\n":
            print("[FAIL] Existing run evidence was modified during reuse rejection.")
            return 1

        for invalid in ("", "..", "../escape", "nested/run"):
            try:
                _safe_run_root(invalid)
            except EvalRunIntegrityError:
                continue
            print(f"[FAIL] Unsafe run_id was accepted: {invalid!r}")
            return 1

        print("Behavior Eval run integrity validation passed: immutable root and path confinement.")
        return 0
    finally:
        if run_root.exists():
            shutil.rmtree(run_root)


if __name__ == "__main__":
    raise SystemExit(main())
