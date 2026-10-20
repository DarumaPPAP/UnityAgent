#!/usr/bin/env python3
"""明示した保存済みRunだけを読む。Production実行やFrozen Baselineの更新は行わない。"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import yaml

from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.persistence.store.atomic_store import PersistenceError, read_json, relative_ref, resolve_ref, safe_id, sha256_json
from unityagent.persistence.store.layout import PersistenceLayout
from unityagent.resources import resource_root

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(layout, ref, owner, kind, records):
    path = resolve_ref(layout.root, ref)
    value = read_json(path)
    digest = sha256_json(value)
    expected = layout.snapshot(owner, kind, digest)
    if ref != relative_ref(layout.root, expected) or path != expected.resolve():
        raise ValueError('snapshot digest or Run binding differs')
    records.append({'ref': ref, 'digest': digest, 'kind': kind})
    return value


def _number(value):
    valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    return value if valid else None


def _sample(layout, *, owner, child, task_id, attempt, refs, status, definition, gates,
            diagnostics, latency_ms, state_record, schema, expected_attempts):
    records = [state_record]
    missing = [d['code'] for d in diagnostics if isinstance(d, dict) and isinstance(d.get('code'), str)]
    observed = []
    for ref in refs:
        try:
            record = _snapshot(layout, ref, owner, 'strategy-observation', records)
            schema.validate(record)
            validate_definition_fingerprint(record['definition_fingerprint'])
            if record['run_id'] != owner or record.get('task_id') != task_id:
                raise ValueError('observation Run or Task differs')
            inputs = {key: record[key] for key in ('selection_inputs', 'failure_class', 'uncertain_side_effects')}
            if record['input_digest'] != sha256_json({'current_path': record['current_path'], **inputs}):
                raise ValueError('observation input digest differs')
            if task_id is not None and record['attempt'] not in expected_attempts:
                raise ValueError('unknown attempt')
            if record.get('attempt') == attempt:
                if record['result_run_id'] != child:
                    raise ValueError('observation result Run differs')
                if definition and any(record['definition_fingerprint'].get(k) != v for k, v in definition.items()
                                      if k not in {'policy_revision', 'context_revision'}):
                    raise ValueError('observation definition differs')
                observed.append(record)
        except (OSError, PersistenceError, ValueError, TypeError, KeyError, ValidationError):
            missing.append('invalid_observation_reference')
    if len(refs) != len(set(refs)):
        missing.append('duplicate_observation_reference')
    if len(observed) != 1:
        missing.append('missing_or_duplicate_boundary_observation')
    observation = observed[0] if len(observed) == 1 else None
    if observation:
        for evidence_ref in observation['evidence_refs']:
            try:
                evidence = read_json(layout.evidence(safe_id(evidence_ref, 'evidence_id')))
                if evidence.get('run_id') != child or evidence.get('evidence_id') != evidence_ref or evidence.get('definition_fingerprint') != observation['definition_fingerprint']:
                    raise ValueError('Evidence binding differs')
                records.append({'ref': relative_ref(layout.root, layout.evidence(evidence_ref)),
                                'digest': sha256_json(evidence), 'kind':'evidence'})
            except (OSError, PersistenceError, ValueError, TypeError):
                missing.append('invalid_evidence_reference')
        definition = observation['definition_fingerprint']
        status = observation['result_status']
        gates = observation['gates']
        for kind, field in (('context-manifest', 'context_manifest_ref'), ('orchestration-decision', 'orchestration_decision_ref')):
            try:
                value = _snapshot(layout, observation[field], child, kind, records)
                if kind == 'context-manifest' and value.get('run_id') != child:
                    raise ValueError('manifest Run differs')
                if kind == 'orchestration-decision' and value['execution_plan']['path'] != observation['current_path']:
                    raise ValueError('initial path differs')
            except (OSError, PersistenceError, ValueError, TypeError, KeyError):
                missing.append('invalid_' + kind.replace('-', '_') + '_reference')
    estimate = None
    if observation and observation.get('context_manifest_ref'):
        try:
            manifest = read_json(resolve_ref(layout.root, observation['context_manifest_ref']))
            estimate = _number(manifest['budget_report']['estimated_tokens'])
            if not isinstance(estimate, int):
                estimate = None
        except (OSError, PersistenceError, KeyError, TypeError):
            missing.append('context_estimate_not_observed')
    failure = observation['failure_class'] if observation else None
    unavailable = failure in {'unavailable', 'unknown', 'unhealthy', 'ambiguous_binding', 'unsupported', 'backend_not_implemented', 'timeout'}
    unavailable = unavailable or status in {'unavailable', 'not_observed'} or bool(failure and any(
        word in failure for word in ('environment', 'unavailable', 'not_observed')))
    unavailable = unavailable or any(g not in {'passed', 'failed'} for g in gates.values())
    outcome = 'unavailable' if unavailable else 'failed' if status == 'failed' or 'failed' in gates.values() else 'completed' if status in {'completed', 'verified'} else 'blocked'
    # Gateだけの成功でRuntime blockedを品質成功へ昇格させない。
    evaluable = bool(gates) and not missing and not unavailable and (not failure or failure in {'execution_failed', 'observed_test_failure'})
    evaluable = evaluable and (status in {'completed', 'verified', 'failed'} or 'failed' in gates.values())
    quality = 'passed' if evaluable and status in {'completed', 'verified'} and all(g == 'passed' for g in gates.values()) else 'failed' if evaluable else 'not_evaluated'
    return {'id': f'{owner}/{task_id}/{attempt}' if task_id else owner, 'run_id': owner,
        'result_run_id': child, 'task_id': task_id, 'attempt': attempt, 'execution_status': status,
        'outcome': outcome, 'quality': quality, 'gates': gates,
        'current_path': observation['current_path'] if observation and not missing else None,
        'recommendation': observation['recommendation'] if observation and not missing else None,
        'context_estimated_tokens': estimate if not missing else None,
        'latency_ms': _number(latency_ms), 'latency_scope': 'task_total' if latency_ms is not None else 'not_observed',
        'missing_observations': sorted(set(missing)), 'records': records}, definition


def build_adaptive_baseline(persistence_root: Path, run_ids: list[str], *, source_revision: str) -> dict[str, Any]:
    """異なる定義・revisionを分離し、欠測を分母に残す読み取り専用の集計。"""
    if not isinstance(source_revision, str) or not source_revision.strip() or not run_ids:
        raise ValueError('explicit source revision and Run ids are required')
    layout = PersistenceLayout(persistence_root)
    schema = Draft202012Validator(yaml.safe_load((resource_root() /
        'src/unityagent/orchestration/contracts/strategy-observation.schema.yaml').read_text(encoding='utf-8')))
    groups = {}
    requested = list(dict.fromkeys(safe_id(run, 'run_id') for run in run_ids))
    for run in requested:
        task_path = layout.run_root(run) / 'current/task-state.json'
        path = task_path if task_path.exists() else layout.execution_state(run)
        state_digest = None
        try:
            state = read_json(path)
            state_digest = sha256_json(state)
            if state.get('run_id') != run:
                raise ValueError('state Run binding differs')
        except (OSError, PersistenceError, ValueError):
            state = {'run_id': run, 'status': 'unavailable', 'strategy_observation_diagnostics': [{'code':'run_state_unavailable'}]}
        state_record = {'ref': relative_ref(layout.root, path), 'digest': state_digest, 'kind':'task-state' if path == task_path else 'execution-state'}
        revision = state.get('source_revision', source_revision)
        targets = []
        if 'tasks' in state:
            for task_id, task in state['tasks'].items():
                history = task.get('handoff_history', [])
                for attempt, entry in enumerate(history or [{'run_id': f'{run}-{task_id}'}]):
                    final = attempt == len(history) - 1
                    targets.append(dict(owner=run, child=entry['run_id'], task_id=task_id, attempt=attempt,
                        refs=task.get('strategy_observation_refs', []), status=task['status'],
                        definition=task.get('result', {}).get('handoff', {}).get('definition_fingerprint', state.get('definition_fingerprint')),
                        gates=task.get('gates', {}) if final else {},
                        diagnostics=task.get('strategy_observation_diagnostics', []) + (task.get('result', {}).get('strategy_observation_diagnostics', []) if final else []),
                        latency_ms=task.get('latency_ms') if final else None, expected_attempts=set(range(len(history)))))
        else:
            targets.append(dict(owner=run, child=run, task_id=None, attempt=None, refs=state.get('strategy_observation_refs', []),
                status=state.get('status', 'unavailable'), definition=state.get('definition_fingerprint'), gates={},
                diagnostics=state.get('strategy_observation_diagnostics', []), latency_ms=None, expected_attempts=set()))
        for target in targets:
            sample, definition = _sample(layout, **target, state_record=state_record, schema=schema)
            key = sha256_json({'source_revision':revision, 'definition_fingerprint':definition})
            group = groups.setdefault(key, {'source_revision': revision, 'definition_fingerprint': definition, 'samples': []})
            group['samples'].append(sample)
    for group in groups.values():
        samples = group['samples']
        total = len(samples)
        evaluable = sum(s['quality'] != 'not_evaluated' for s in samples)
        succeeded = sum(s['quality'] == 'passed' for s in samples)
        group.update(path_distribution=dict(Counter(s['current_path'] for s in samples if s['current_path'])),
            recommendation_distribution=dict(Counter(s['recommendation'] for s in samples if s['recommendation'])),
            outcomes={key: sum(s['outcome'] == key for s in samples) for key in ('completed','failed','blocked','unavailable')},
            quality={'total':total, 'evaluable':evaluable, 'succeeded':succeeded, 'not_evaluated':total-evaluable,
                     'success_rate':succeeded/evaluable if evaluable else None},
            completion={'total':total, 'completed':sum(s['execution_status'] in {'completed','verified'} for s in samples)},
            model_usage={'status':'not_observed','total_tokens':None})
    result = {'schema_version':'1.0', 'declared_source_revision':source_revision, 'source_revision_provenance':'caller_declared_unless_persisted',
        'requested_run_ids':requested, 'observation_completeness':'failed' if any(
            s['missing_observations'] for g in groups.values() for s in g['samples']) else 'complete',
        'measurement_scope':'saved_run_records_only', 'groups':list(groups.values())}
    Draft202012Validator(yaml.safe_load((ROOT / 'eval/regression/adaptive-baseline.schema.yaml').read_text(encoding='utf-8'))).validate(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--persistence-root', type=Path, required=True)
    parser.add_argument('--run-id', action='append', required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.resolve().is_relative_to(args.persistence_root.resolve()):
            raise ValueError('output must be outside source Persistence')
        value = build_adaptive_baseline(args.persistence_root, args.run_id, source_revision=args.source_revision)
        # 既存Frozen Baselineを含め、指定先の既存ファイルは上書きしない。
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    except (OSError, PersistenceError, ValueError) as exc:
        parser.exit(2, f'Baseline集計失敗: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
