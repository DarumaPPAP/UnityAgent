"""Unity Editor log と Test XML を限定的に正規化する。"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_COMPILER_RE = re.compile(
    r"(?P<path>[^:\r\n]+?\.cs)\((?P<line>\d+),(?P<column>\d+)\):\s*"
    r"(?P<severity>error|warning)\s+(?P<code>[A-Za-z]+\d+):\s*(?P<message>.*)",
    re.IGNORECASE,
)
_GENERIC_COMPILER_ERROR_RE = re.compile(r"\berror\s+(?P<code>CS\d+):\s*(?P<message>.+)", re.IGNORECASE)


@dataclass(frozen=True)
class CompilerDiagnostic:
    path: str | None
    line: int | None
    column: int | None
    severity: str
    code: str
    message: str


def parse_compiler_diagnostics(log_text: str) -> list[CompilerDiagnostic]:
    diagnostics: list[CompilerDiagnostic] = []
    seen: set[tuple[Any, ...]] = set()
    for raw_line in log_text.splitlines():
        match = _COMPILER_RE.search(raw_line)
        if match:
            value = CompilerDiagnostic(
                path=match.group("path").strip(),
                line=int(match.group("line")),
                column=int(match.group("column")),
                severity=match.group("severity").casefold(),
                code=match.group("code"),
                message=match.group("message").strip(),
            )
        else:
            generic = _GENERIC_COMPILER_ERROR_RE.search(raw_line)
            if not generic:
                continue
            value = CompilerDiagnostic(
                path=None,
                line=None,
                column=None,
                severity="error",
                code=generic.group("code"),
                message=generic.group("message").strip(),
            )
        key = (value.path, value.line, value.column, value.severity, value.code, value.message)
        if key not in seen:
            seen.add(key)
            diagnostics.append(value)
    return diagnostics


def normalize_compile_result(*, exit_code: int, log_text: str) -> dict[str, Any]:
    diagnostics = parse_compiler_diagnostics(log_text)
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        return {
            "status": "failed",
            "failure_class": "execution_failed",
            "reason": "compiler diagnostics contain errors",
            "diagnostics": [asdict(item) for item in diagnostics],
            "evidence": ["compile_observation"],
        }
    if exit_code != 0:
        return {
            "status": "failed",
            "failure_class": "execution_failed",
            "reason": f"Unity Editor exited with code {exit_code}",
            "diagnostics": [asdict(item) for item in diagnostics],
            "evidence": ["compile_observation"],
        }
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "diagnostics": [asdict(item) for item in diagnostics],
        "evidence": ["compile_observation"],
    }


def _int_attr(root: ET.Element, name: str) -> int:
    raw = root.attrib.get(name)
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0


def read_test_results(test_results_path: Path) -> dict[str, Any] | None:
    if not test_results_path.is_file():
        return None
    try:
        root = ET.parse(test_results_path).getroot()
    except (ET.ParseError, OSError):
        return None
    return {
        "result": str(root.attrib.get("result") or "Unknown"),
        "start_time": root.attrib.get('start-time'),
        "end_time": root.attrib.get('end-time'),
        "test_cases": [{'name': item.attrib.get('fullname'), 'result': item.attrib.get('result')}
                       for item in root.iter('test-case')],
        "total": _int_attr(root, "total") or _int_attr(root, "testcasecount"),
        "passed": _int_attr(root, "passed"),
        "failed": _int_attr(root, "failed"),
        "skipped": _int_attr(root, "skipped"),
        "inconclusive": _int_attr(root, "inconclusive"),
    }


def normalize_test_result(
    *,
    exit_code: int,
    log_text: str,
    test_results_path: Path,
    expected_test_names: list[str] | None = None,
    not_before_ns: int | None = None,
) -> dict[str, Any]:
    compile_result = normalize_compile_result(exit_code=0, log_text=log_text)
    if compile_result["status"] != "passed":
        return {
            **compile_result,
            "reason": "test run could not produce trustworthy results because compilation failed",
            "evidence": [],
        }

    test_result = read_test_results(test_results_path)
    if test_result is not None:
        valid = test_result['total'] > 0
        if expected_test_names is not None:
            cases = test_result['test_cases']
            observed_names = {item['name'] for item in cases}
            valid = (valid and bool(expected_test_names) and set(expected_test_names) <= observed_names
                     and test_result['total'] == len(cases)
                     and test_result['passed'] == sum(item['result'] == 'Passed' for item in cases)
                     and test_result['failed'] == sum(item['result'] == 'Failed' for item in cases)
                     and all(item['result'] in {'Passed', 'Failed'} for item in cases))
        if not_before_ns is not None:
            try:
                start = datetime.fromisoformat(test_result['start_time'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(test_result['end_time'].replace('Z', '+00:00'))
                valid = (valid and start.tzinfo is not None and end.tzinfo is not None
                         and start.timestamp() >= not_before_ns / 1e9 - 1.0 and end >= start)
            except (TypeError, ValueError, AttributeError):
                valid = False
        if not valid:
            return {'status': 'failed', 'failure_class': 'not_observed',
                    'reason': 'Current non-empty target EditMode results were not observed',
                    'test_result': test_result, 'evidence': []}
        result_name = test_result["result"].casefold()
        if test_result["failed"] > 0 or result_name in {"failed", "failure"}:
            return {
                "status": "failed",
                "failure_class": "observed_test_failure",
                "reason": "Unity Test Framework observed failing tests",
                "test_result": test_result,
                "evidence": ["test_execution"],
            }
        if exit_code != 0:
            return {
                "status": "failed",
                "failure_class": "execution_failed",
                "reason": f"Unity Editor exited with code {exit_code} despite structured test results",
                "test_result": test_result,
                "evidence": ["test_execution"],
            }
        if result_name in {"passed", "pass", "success"}:
            return {
                "status": "passed",
                "failure_class": None,
                "reason": None,
                "test_result": test_result,
                "evidence": ["test_execution"],
            }

    if exit_code != 0:
        return {
            "status": "failed",
            "failure_class": "execution_failed",
            "reason": f"Unity Editor exited with code {exit_code} before trustworthy test XML was observed",
            "test_result": None,
            "evidence": [],
        }
    return {
        "status": "failed",
        "failure_class": "not_observed",
        "reason": "Unity Test Framework result XML was not observed",
        "test_result": None,
        "evidence": [],
    }


def normalize_build_result(
    *,
    exit_code: int,
    log_text: str,
    build_output_path: Path,
) -> dict[str, Any]:
    compile_result = normalize_compile_result(exit_code=exit_code, log_text=log_text)
    if compile_result["status"] != "passed":
        return {
            **compile_result,
            "reason": "build did not complete because compile/execution errors were observed",
            "evidence": [],
        }
    if not build_output_path.exists():
        return {
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "Unity exited successfully but build output was not observed",
            "diagnostics": compile_result["diagnostics"],
            "evidence": [],
        }
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "diagnostics": compile_result["diagnostics"],
        "build_output": str(build_output_path),
        "evidence": ["build_execution"],
    }
