#!/usr/bin/env python3
"""測定条件を先に固定し、3 warmup＋30組のABCを順序交替で記録・判定する。"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import random
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time

from jsonschema import Draft202012Validator, ValidationError

from unityagent.persistence.store.atomic_store import PersistenceError, read_json, sha256_json, write_immutable_json
from unityagent.runtime.execution_control.process_runtime import run_streaming_process

ROOT = Path(__file__).resolve().parents[1]


def variant_order(round_id):
    return ('ABC', 'CBA')[round_id % 2]


def _p95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1]


def _bootstrap(ratios):
    generator = random.Random(20261021)
    medians = sorted(statistics.median(generator.choices(ratios, k=len(ratios))) for _ in range(10000))
    return [medians[249], medians[9749]]


def evaluate(rows, scenarios):
    diagnostics, parallel, fast, dynamic = [], {}, {}, {}
    expected = {(name, index, variant) for name in scenarios for index in range(33) for variant in 'ABC'}
    keys = [(row['scenario'], row['round'], row['variant']) for row in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        return {'status': 'invalid', 'diagnostics': ['incomplete_or_duplicate_pairs'], 'actual_tokens': None}
    measured = [row for row in rows if row['round'] >= 3]
    numeric = ('duration_ns', 'coordination_ns', 'safety_incidents', 'redundant_context_copies', 'workers',
               'worktrees', 'preparations', 'project_scans', 'model_calls', 'provider_calls', 'unnecessary_calls', 'observed_worker_overlap_ns')
    if any(type(row.get(key)) is not int or row[key] < 0 for row in rows for key in numeric):
        return {'status': 'invalid', 'diagnostics': ['missing_or_invalid_measurement'], 'actual_tokens': None}
    for row in rows:
        if row['position'] != variant_order(row['round']).index(row['variant']):
            diagnostics.append('variant_order_changed')
        if (type(row['duration_ns']) is not int or row['duration_ns'] <= time.get_clock_info('monotonic').resolution * 1e9
                or type(row['coordination_ns']) is not int or row['coordination_ns'] <= 0):
            diagnostics.append('clock_resolution_or_missing_duration')
        if row['safety_incidents'] != 0:
            diagnostics.append('safety_incident')
        if not row['context_preserved'] or row['redundant_context_copies'] != 0:
            diagnostics.append('context_constraints')
        if row['status'] == 'passed' and (not row['quality_passed'] or not row['evidence_verified']):
            diagnostics.append('unverified_quality_claim')
    for name, kind in scenarios.items():
        variants = {variant: sorted([row for row in measured if row['scenario'] == name and row['variant'] == variant],
                                   key=lambda row: row['round']) for variant in 'ABC'}
        succeeded = lambda row: row['status'] == 'passed' and row['quality_passed'] and row['evidence_verified']
        for a, b, c in zip(*(variants[key] for key in 'ABC')):
            if (succeeded(a) and (not succeeded(b) or not succeeded(c))) or (succeeded(b) and not succeeded(c)):
                diagnostics.append('candidate_quality_regression')
        if kind == 'parallel':
            b = [row['duration_ns'] for row in variants['B']]
            c = [row['duration_ns'] for row in variants['C']]
            if min(b + c) <= 0:
                diagnostics.append('invalid_parallel_duration')
                continue
            ratio = statistics.median(c) / statistics.median(b)
            interval = _bootstrap([candidate / baseline for baseline, candidate in zip(b, c)])
            passed = (all(succeeded(row) for variant in 'BC' for row in variants[variant])
                      and all(row['workers'] == 2 and row['observed_worker_overlap_ns'] > 0 for row in variants['C'])
                      and all(row['workers'] == 0 and row['observed_worker_overlap_ns'] == 0 for row in variants['B'])
                      and ratio <= .85 and _p95(c) <= _p95(b) and interval[1] < 1)
            parallel[name] = {'median_ratio_c_over_b': ratio, 'p95_b_ns': _p95(b), 'p95_c_ns': _p95(c),
                              'paired_ratio_ci95': interval, 'passed': passed}
            if not passed:
                diagnostics.append('parallel_value_not_demonstrated')
        elif kind == 'fast':
            base = _p95([row['coordination_ns'] for row in variants['A']])
            passed = base > 0 and all(succeeded(row) and row['workers'] == 0 and row['worktrees'] == 0
                for variant in 'ABC' for row in variants[variant])
            for variant in 'BC':
                passed = passed and _p95([row['coordination_ns'] for row in variants[variant]]) <= base * 1.05
                for baseline, candidate in zip(variants['A'], variants[variant]):
                    passed = passed and all(candidate[key] <= baseline[key] for key in
                        ('preparations', 'project_scans', 'model_calls', 'provider_calls', 'unnecessary_calls'))
            fast[name] = {'passed': passed}
            if not passed:
                diagnostics.append('fast_regression')
        elif kind == 'dynamic':
            counts = {variant: sum(succeeded(row) for row in variants[variant]) for variant in 'ABC'}
            calls = {variant: sum(row['unnecessary_calls'] for row in variants[variant]) for variant in 'ABC'}
            passed = all(counts[variant] > counts['A'] or (counts[variant] >= counts['A'] and calls[variant] < calls['A']) for variant in 'BC')
            dynamic[name] = {'successes': counts, 'unnecessary_calls': calls, 'passed': passed}
            if not passed:
                diagnostics.append('adaptive_value_not_demonstrated')
        else:
            diagnostics.append('unknown_scenario_kind')
    if set(scenarios.values()) != {'fast', 'dynamic', 'parallel'}:
        diagnostics.append('required_scenario_missing')
    return {'schema_version': '1.0', 'status': 'criteria_met' if not diagnostics else 'not_met',
            'measurement_scope': 'recorded_runs_only; independent_environment_and_safety_review_required',
            'diagnostics': sorted(set(diagnostics)), 'parallel': parallel, 'fast': fast, 'dynamic': dynamic,
            'actual_tokens': None, 'actual_usage_observed_runs': sum(row.get('actual_usage') is not None for row in measured),
            'sample_counts': {'warmup': len(rows) - len(measured), 'measured': len(measured)},
            'bootstrap': {'resamples': 10000, 'seed': 20261021, 'statistic': 'median_of_paired_c_over_b'}}


def _schema():
    return json.loads(Path(__file__).with_suffix('.schema.json').read_text())


def _host():
    return {'os': platform.platform(), 'machine': platform.machine(),
            'processor': platform.processor(), 'logical_cpu_count': os.cpu_count()}


def freeze(config, output):
    Draft202012Validator(_schema()).validate(config)
    if set(item['kind'] for item in config['scenarios']) != {'fast', 'dynamic', 'parallel'}:
        raise ValueError('All three scenario kinds must be fixed before measurement')
    if len({item['id'] for item in config['scenarios']}) != len(config['scenarios']):
        raise ValueError('Scenario identifiers must be unique')
    if output.absolute() != output.resolve():
        raise ValueError('Measurement output must be absolute and unaliased')
    for item in config['scenarios']:
        _validate_command(item)
    output.mkdir(parents=True, exist_ok=False)
    write_immutable_json(output / 'conditions.json', {'config': config, 'digest': sha256_json(config), 'observed_host': _host()})


def _validate_command(scenario):
    command = scenario['command']
    expected = ['--conditions', '{conditions}', '--scenario', scenario['id'], '--variant', '{variant}',
                '--workspace', '{workspace}', '--report', '{report}']
    if (len(command) != 12 or command[2:] != expected
            or Path(command[0]).resolve() != Path(sys.executable).resolve()
            or (ROOT / command[1]).resolve() != ROOT / 'tools/adaptive_scenario.py'):
        raise ValueError('Comparison requires the frozen canonical adaptive_scenario.py adapter')


def _assert_source(config):
    revision = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], check=True,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'], check=True,
                           capture_output=True, text=True, timeout=5).stdout.strip()
    if revision != config['source_sha'] or dirty:
        raise ValueError('Measurement requires the frozen clean Source SHA; REBASELINE_REQUIRED')


def _verify_evidence(report, source_revision, workspace, kind, conditions):
    if not isinstance(report.get('evidence'), dict):
        return False
    spec = importlib.util.spec_from_file_location('adaptive_baseline_reader', ROOT / 'tools/adaptive_baseline.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    try:
        root = Path(report['evidence']['persistence_root'])
        expected_run = 'parallel-e2e' if kind == 'parallel' else 'comparison-' + kind
        if root != workspace / 'state' or root != root.resolve() or report['evidence']['run_id'] != expected_run:
            return False
        baseline = reader.build_adaptive_baseline(Path(report['evidence']['persistence_root']),
            [report['evidence']['run_id']], source_revision=source_revision)
        from unityagent.persistence.state.state_store import StateStore
        store = StateStore(report['evidence']['persistence_root'])
        run_id = report['evidence']['run_id']
        task_state = store.layout.run_root(run_id) / 'current/task-state.json'
        if task_state.exists():
            state = read_json(task_state)
            if state['status'] != 'verified':
                return False
            from unityagent.persistence.state.plan import read_active_plan
            active = read_active_plan(store, state)
            root_contract = active['root_contract']
            expected_project = workspace / ('original' if kind == 'parallel' else 'followup' if kind == 'dynamic' else 'first')
            expected_gates = {'project': ['project_fact']}
            if kind == 'parallel':
                from unityagent.control_plane.csharp_fix import load_patch_plan
                from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
                from unityagent.persistence.evidence.evidence_store import EvidenceStore
                expected_gates = {'static': ['static_review'], 'compile': ['compile_observation', 'current_compile_observation'],
                                  'editmode': ['test_execution', 'targeted_editmode_execution']}
                if (state.get('parallel_execution', {}).get('enabled') != report['parallel_enabled']
                        or state.get('observed_worker_overlap_ns') != report['observed_worker_overlap_ns']
                        or report['workers'] != (2 if state.get('observed_worker_overlap_ns', 0) > 0 else 0)
                        or state['tasks'].get('integration-final', {}).get('status') != 'verified'):
                    return False
                final_task = next(task for task in active['tasks'] if task['id'] == 'integration-final')
                expected_tests = {'UnityAgent.AdaptiveFixture.Tests.CalculatorTests.AddReturnsSum',
                                  'UnityAgent.AdaptiveFixture.Tests.MultiplierTests.Multiplies'}
                if set(final_task['entry_request']['intent']['editmode_tests']) != expected_tests:
                    return False
                records = [EvidenceStore(root).verify_record(ref) for ref in state['tasks']['integration-final']['result']['evidence_refs']]
                if not all(any(record.get('capability') == capability and record.get('provider_ref') == 'native_unity_editor'
                               and record.get('completion') == 'verified' for record in records)
                           for capability in ('compile.observe', 'project.test')):
                    return False
                plane = UnityAgentControlPlane(root)
                for name in ('left', 'right'):
                    identifier = state['tasks'][name]['result']['patch_plan_id']
                    patch = load_patch_plan(plane, identifier)
                    if patch['model'] != conditions['model'] or Path(patch['project_root']) != workspace / name:
                        return False
            if root_contract['project_root'] != str(expected_project) or root_contract['required_gates'] != expected_gates:
                return False
            if state.get('schema_version') == '2.0':
                from unityagent.control_plane.plan_execution import verify_final_gates
                from unityagent.persistence.state.plan import read_active_plan
                from types import SimpleNamespace
                plane = SimpleNamespace(state_store=store)
                expected = state.get('final_gates')
                verify_final_gates(plane, state, read_active_plan(store, state)['tasks'])
                if state['status'] != 'verified' or state['final_gates'] != expected:
                    return False
        return (bool(baseline['groups']) and baseline['observation_completeness'] == 'complete'
                and all(group['quality']['total'] > 0 and group['quality']['succeeded'] == group['quality']['total']
                        for group in baseline['groups']))
    except (ValueError, OSError, KeyError, TypeError, StopIteration, PersistenceError):
        return False


def collect(output):
    frozen = read_json(output / 'conditions.json')
    config = frozen['config']
    Draft202012Validator(_schema()).validate(config)
    if sha256_json(config) != frozen['digest']:
        raise ValueError('Frozen measurement conditions changed')
    if frozen.get('observed_host') != _host():
        raise ValueError('Observed measurement host differs from frozen conditions')
    for scenario in config['scenarios']:
        _validate_command(scenario)
    _assert_source(config)
    samples = output / 'samples'
    samples.mkdir(exist_ok=False)  # 中断後の自動再送と成功Runだけの再測定を禁止する。
    cancellation = threading.Event()
    previous_handler = signal.signal(signal.SIGINT, lambda *_: cancellation.set())
    try:
        for scenario in config['scenarios']:
            for index in range(33):
                for position, variant in enumerate(variant_order(index)):
                    _assert_source(config)
                    name = f"{scenario['id']}-{index:02d}-{variant}"
                    report_path, workspace = output / (name + '.json'), output / name
                    values = {'{workspace}': str(workspace), '{report}': str(report_path),
                              '{conditions}': str(output / 'conditions.json'), '{variant}': variant}
                    command = [values.get(argument, argument) for argument in scenario['command']]
                    started = time.monotonic_ns()
                    with tempfile.TemporaryDirectory(prefix='unityagent-benchmark-') as temporary:
                        process = run_streaming_process(command, cwd=ROOT, timeout_seconds=config['timeout_seconds'],
                            stdout_path=Path(temporary) / 'stdout', stderr_path=Path(temporary) / 'stderr', cancel_event=cancellation)
                    elapsed = time.monotonic_ns() - started
                    try:
                        report = read_json(report_path)
                        Draft202012Validator(_schema()['$defs']['report']).validate(report)
                        if (report['conditions_digest'] != frozen['digest'] or report['variant'] != variant
                                or report['scenario'] != scenario['id'] or report['execution_kind'] != 'real'
                                or report['adaptive_enabled'] != (variant != 'A')
                                or report['parallel_enabled'] != (variant == 'C')):
                            raise ValueError('Report differs from fixed comparison conditions')
                        # 任意commandの自己申告boolでは品質PASSを採用しない。
                        report['evidence_verified'] = _verify_evidence(report, config['source_sha'], workspace,
                                                                     scenario['kind'], config)
                        row = {key: report[key] for key in _schema()['$defs']['report']['properties'] if key in report}
                    except (OSError, ValueError, KeyError, ValidationError, PersistenceError):
                        row = {'status': 'unavailable', 'quality_passed': False, 'evidence_verified': False,
                               'coordination_ns': None, 'safety_incidents': None, 'context_preserved': False,
                               'redundant_context_copies': None, 'workers': None, 'worktrees': None,
                               'preparations': None, 'project_scans': None, 'model_calls': None,
                               'provider_calls': None, 'unnecessary_calls': None, 'actual_usage': None,
                               'observed_worker_overlap_ns': None}
                    if process.timed_out or process.cancelled or process.returncode != 0:
                        row.update(status='timeout' if process.timed_out else 'cancelled' if process.cancelled else 'failed', quality_passed=False)
                    row.update(scenario=scenario['id'], variant=variant, round=index, position=position, duration_ns=elapsed,
                               process_cleanup=process.process_tree_cleanup, remaining_processes=process.remaining_processes)
                    try:
                        _assert_source(config)
                        source_valid = True
                    except ValueError:
                        source_valid = False
                        row.update(status='failed', quality_passed=False, source_changed=True)
                    write_immutable_json(samples / (name + '-' + sha256_json(row).split(':')[1] + '.json'), row)
                    if not source_valid:
                        raise ValueError('Source changed during measurement; REBASELINE_REQUIRED')
                    if cancellation.is_set() or process.remaining_processes:
                        raise ValueError('Measurement interrupted; reconciliation required, no automatic replay')
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    _assert_source(config)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='freezeは新規ディレクトリへ条件を固定。collectは固定した同一commandへvariantだけを渡し、workspace作成から最終Gateまでの総時間を計測。各commandはSchemaのreportを保存する。evaluateは全失敗と欠測を残して判定し、既存Frozen Baselineを変更しない。')
    parser.add_argument('phase', choices=['freeze', 'collect', 'evaluate'])
    parser.add_argument('--output', required=True, type=Path, help='新規測定artifactディレクトリ')
    parser.add_argument('--input', type=Path, help='freeze時のみ。adaptive_comparison.schema.jsonに従う条件JSON')
    args = parser.parse_args(argv)
    try:
        output = args.output.absolute()
        if args.phase == 'freeze':
            if args.input is None:
                raise ValueError('freeze needs --input')
            freeze(read_json(args.input), output)
            result = {'status': 'frozen'}
        elif args.phase == 'collect':
            collect(output)
            result = {'status': 'recorded'}
        else:
            frozen = read_json(output / 'conditions.json')
            Draft202012Validator(_schema()).validate(frozen['config'])
            if sha256_json(frozen['config']) != frozen['digest']:
                raise ValueError('Measurement conditions changed')
            _assert_source(frozen['config'])
            rows = []
            kinds = {item['id']: item['kind'] for item in frozen['config']['scenarios']}
            for path in sorted((output / 'samples').glob('*.json')):
                row = read_json(path)
                name = f"{row['scenario']}-{row['round']:02d}-{row['variant']}"
                if path.name != name + '-' + sha256_json(row).split(':')[1] + '.json':
                    raise ValueError('Measurement artifact digest differs')
                if row.get('status') == 'passed':
                    workspace = output / name
                    if not _verify_evidence(row, frozen['config']['source_sha'], workspace, kinds[row['scenario']], frozen['config']):
                        row = {**row, 'evidence_verified': False}
                rows.append(row)
            result = evaluate(rows, {item['id']: item['kind'] for item in frozen['config']['scenarios']})
            write_immutable_json(output / 'evaluation.json', result)
    except (ValueError, OSError, KeyError, TypeError, ValidationError, PersistenceError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'frozen', 'recorded', 'criteria_met'} else 1


if __name__ == '__main__':
    sys.exit(main())
