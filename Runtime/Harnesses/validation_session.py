"""Bound repeated command validation to one explicitly fingerprinted task session.

The caller supplies the complete input/environment fingerprint, including uncommitted
changes. This is not a persistent cache or a semantic completion decision.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import yaml


class ValidationSession:
    def __init__(self, risk_level: str):
        policy = yaml.safe_load((Path(__file__).resolve().parents[2] / 'Policy/Risk/risk-levels.yaml').read_text(encoding='utf-8'))
        if risk_level not in policy['levels']:
            raise ValueError('unknown risk level')
        self.allowed_scopes = policy['levels'][risk_level]['validation_scopes']
        self._passed: dict[tuple, dict] = {}
        self.events: list[dict] = []

    def run(self, *, command: list[str], cwd: str | Path, timeout_seconds: float,
            input_fingerprint: str, scope: str = 'targeted', reason: str = '',
            expect_json: bool = False) -> dict:
        from Runtime.Harnesses.command_harness import run_command_harness

        if not isinstance(input_fingerprint, str) or not input_fingerprint.strip():
            raise ValueError('complete input/environment fingerprint required')
        if scope not in {'targeted', 'regression', 'integration', 'behavior', 'full'}:
            raise ValueError('unknown validation scope')
        if not isinstance(reason, str):
            raise ValueError('reason must be text')
        if scope not in self.allowed_scopes and not reason.strip():
            raise ValueError('broader validation requires a mandatory gate or concrete risk reason')
        key = (tuple(command), str(Path(cwd).resolve()), input_fingerprint, expect_json, scope)
        if key in self._passed and not reason.strip():
            result = deepcopy(self._passed[key])
            result['reused'] = True
            self.events.append({'effect': 'reuse_pass', 'input_fingerprint': input_fingerprint, 'scope': scope})
            return result
        result = run_command_harness(harness_id='test', command=command, cwd=cwd,
                                     timeout_seconds=timeout_seconds, expect_json=expect_json)
        self.events.append({'effect': 'validation', 'input_fingerprint': input_fingerprint,
                            'scope': scope, 'reason': reason, 'status': result['status']})
        # Failed revalidation invalidates an earlier PASS for the same inputs.
        self._passed.pop(key, None)
        if result['status'] == 'passed':
            self._passed[key] = deepcopy(result)
        return {**result, 'reused': False}
