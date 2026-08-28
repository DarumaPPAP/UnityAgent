#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE / "_compat_engine.py"
CANONICAL_BUDGET_CONTRACT_PATH = Path("Context/Budget/context-budget.yaml")

spec = importlib.util.spec_from_file_location("phase2_context_budget_engine", ENGINE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load migrated Context Budget engine")
_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_engine)
_engine.BUDGET_CONTRACT_PATH = CANONICAL_BUDGET_CONTRACT_PATH

BUDGET_CONTRACT_PATH = CANONICAL_BUDGET_CONTRACT_PATH
BudgetError = _engine.BudgetError
ROLE_PRIORITY = _engine.ROLE_PRIORITY
load_yaml = _engine.load_yaml
estimate_tokens = _engine.estimate_tokens
expected_artifacts = _engine.expected_artifacts
build_budget_report = _engine.build_budget_report
validate_budget_report = _engine.validate_budget_report
