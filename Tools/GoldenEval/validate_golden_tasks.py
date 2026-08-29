#!/usr/bin/env python3
"""Phase-6 compatibility shim to canonical Eval/Golden implementation."""
from __future__ import annotations
import importlib.util
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "Eval" / "Golden" / Path(__file__).name
for path in (ROOT, TARGET.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
if not TARGET.is_file():
    raise RuntimeError(f"canonical Eval target is missing: {TARGET}")

if __name__ == "__main__":
    runpy.run_path(str(TARGET), run_name="__main__")
else:
    spec = importlib.util.spec_from_file_location(f"_unityagent_eval_golden_{TARGET.stem}", TARGET)
    if spec is None or spec.loader is None:
        raise ImportError(str(TARGET))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in dir(module):
        if not name.startswith("_"):
            globals()[name] = getattr(module, name)
