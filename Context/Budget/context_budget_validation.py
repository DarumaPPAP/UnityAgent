#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

path = HERE / "_compat_validation.py"
spec = importlib.util.spec_from_file_location("phase2_context_budget_validation", path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load migrated Context Budget validation engine")
_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_module)

validate_budget_integrity = _module.validate_budget_integrity
