#!/usr/bin/env python3
"""新規所有Fixtureの2件C#修正を実workerで処理し、明示承認後に原Projectへ直列統合する。"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from jsonschema import Draft202012Validator, ValidationError

from unityagent.cli import _fingerprint
from unityagent.control_plane.csharp_fix import approve_csharp_fix, load_patch_plan
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.persistence.store.atomic_store import atomic_write_json, read_json
from unityagent.runtime.guardrails.csharp_patch import project_revision
from unityagent.runtime.sandbox.workspace_guard import snapshot_workspace_hashes
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'Packages/com.darumappap.unity-agent/Editor/Verification~/tests/unity/projects/parallel-csharp-fix'
GATES = {'static': ['static_review'], 'compile': ['compile_observation', 'current_compile_observation'],
         'editmode': ['test_execution', 'targeted_editmode_execution']}
CASES = {'left': ('Assets/Calculator.cs', 'CalculatorTests.AddReturnsSum', 'return a - b;', 'return a + b;'),
         'right': ('Assets/Multiplier.cs', 'MultiplierTests.Multiplies', 'return a + b;', 'return a * b;')}


def _identity(project):
    info = project.stat()
    return [info.st_dev, info.st_ino]


def _source_revision():
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain'))}


def _entry(project, name, *, verify=False):
    target, test, _, _ = CASES[name]
    operation = 'sum' if name == 'left' else 'product'
    intent = {'kind': 'csharp_local_fix', 'goal_or_confirmed_error': 'Confirmed incorrect ' + operation,
        'target_source': target, 'expected_behavior': 'Return the mathematically correct ' + operation,
        'allowed_changes': 'Replace only the existing method return expression; preserve declarations and other files',
        'expected_revision': project_revision(project),
        'editmode_tests': ['UnityAgent.AdaptiveFixture.Tests.' + test]}
    if verify:
        intent.update(verification_only=True,
            editmode_tests=['UnityAgent.AdaptiveFixture.Tests.' + item[1] for item in CASES.values()])
    return {'schema_version': '2.0', 'request_id': 'parallel-fixture-' + name,
            'entry_point': 'codex_plugin', 'project_root': str(project), 'intent': intent}


def _parameters(project, workspace, config):
    snapshot = discover_environment(str(project), mutation_allowed_paths=['Assets']).to_dict()
    native = NativeUnityEditorProvider(project, snapshot, temp_root=workspace / ('native-' + project.name))
    return {'environment_snapshot': snapshot, 'context': ResolutionContext(policy_allowed=True),
            'executors': {'file': FileProvider(project).execute, 'native_unity_editor': native.execute},
            'provider_arguments': {'native_unity_editor': {'timeout_seconds': config['timeout_seconds']}},
            'reasoning_model': config['model'], 'reasoning_timeout_seconds': config['timeout_seconds']}


def _execute(plane, project, workspace, config, entry):
    return plane.execute(entry, run_id='real-' + uuid.uuid4().hex,
                         definition_fingerprint=_fingerprint(), **_parameters(project, workspace, config))


def _baseline(plane, project, workspace, config):
    before = {target: (project / target).read_bytes() for target, *_ in CASES.values()}
    for _ in range(2):
        revision = project_revision(project)
        result = _execute(plane, project, workspace, config, _entry(project, 'left', verify=True))
        if any((project / target).read_bytes() != content for target, content in before.items()):
            raise ValueError('Original source changed during baseline import')
        tests = [item.get('provider_result', {}) for item in result['results'] if item.get('capability') == 'project.test']
        if tests or project_revision(project) == revision:
            break
    expected = {'UnityAgent.AdaptiveFixture.Tests.' + item[1] for item in CASES.values()}
    failures = {case['name'] for test in tests if test.get('failure_class') == 'observed_test_failure'
                for case in (test.get('test_result') or {}).get('test_cases', []) if case['result'] == 'Failed'}
    return {'status': 'baseline_failure_observed' if failures == expected else 'unavailable',
            'result': result, 'baseline_revision': project_revision(project)}


def _check_owner(workspace):
    owner = read_json(workspace / 'fixture-owner.json')
    if (owner.get('schema_version') != '1.0' or owner.get('fixture') != 'parallel-csharp-fix'
            or set(owner['projects']) not in ({'original'}, {'original', 'left', 'right'})):
        raise ValueError('Parallel fixture ownership is invalid')
    for name, identity in owner['projects'].items():
        project = workspace / name
        if project.resolve(strict=True) != project or _identity(project) != identity:
            raise ValueError('Owned Project identity changed')
        for path in project.rglob('*'):
            if (path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())
                    or (path.is_file() and path.stat().st_nlink != 1)):
                raise ValueError('Owned Project contains an alias')
    return owner


def _tasks(plane, workspace, config):
    report = read_json(workspace / 'workers.json')
    tasks, parameters = [], {}
    projects = {str(workspace / 'original'): {'read_set': ['.'], 'write_set': [item[0] for item in CASES.values()]}}
    for name, identifier in report['approved_plan_ids'].items():
        project = workspace / name
        plan = load_patch_plan(plane, identifier)
        entry = {'schema_version': '2.0', 'request_id': 'parallel-fixture-' + name,
                 'entry_point': 'codex_plugin', 'project_root': str(project), 'intent': {
                     **plan['intent'], 'patch_plan_id': identifier},
                 'approval_ref': report['approval_refs'][name]}
        tasks.append({'id': name, 'workspace': str(project), 'depends_on': [],
            'goal': plan['intent']['goal_or_confirmed_error'], 'read_set': ['.'], 'write_set': [CASES[name][0]],
            'resource_claims': [], 'parallel_safe': True, 'required_gates': GATES, 'entry_request': entry})
        parameters[name] = _parameters(project, workspace, config)
        projects[str(project)] = {'read_set': ['.'], 'write_set': [CASES[name][0]]}
    contract = {'goal': 'Correct both arithmetic errors and verify the final original revision',
        'project_root': str(workspace / 'original'), 'projects': projects, 'required_gates': GATES,
        'approval_conditions': ['existing_policy'], 'allowed_entry_kinds': ['csharp_local_fix']}
    return tasks, parameters, contract


def run(config):
    Draft202012Validator(json.loads(Path(__file__).with_suffix('.schema.json').read_text())).validate(config)
    workspace = Path(config['workspace_root']).absolute()
    if workspace.resolve() != workspace:
        raise ValueError('Fixture workspace must be unaliased')
    phase, started = config['phase'], time.monotonic_ns()
    original = workspace / 'original'
    if phase == 'prepare':
        workspace.mkdir(parents=True, exist_ok=False)
        shutil.copytree(FIXTURE, original)
        subprocess.run(['git', 'init', '--quiet', str(original)], check=True, capture_output=True, timeout=10)
        atomic_write_json(workspace / 'fixture-owner.json', {'schema_version': '1.0',
            'fixture': 'parallel-csharp-fix', 'projects': {'original': _identity(original)}})
    owner = _check_owner(workspace)
    plane = UnityAgentControlPlane(workspace / 'state')
    report = {'schema_version': '1.0', 'execution_kind': 'real', 'phase': phase,
        'source_revision': _source_revision(), 'unity_version': '6000.3.15f1', 'test_framework_version': '1.3.9',
        'model': config['model'], 'parallel_enabled': config['parallel_enabled'], 'status': 'blocked'}
    if phase == 'prepare':
        baseline = _baseline(plane, original, workspace, config)
        report.update(baseline)
        if baseline['status'] == 'baseline_failure_observed':
            for name in CASES:
                project = workspace / name
                project.mkdir()
                for child in ('Assets', 'Packages', 'ProjectSettings'):
                    shutil.copytree(original / child, project / child)
                subprocess.run(['git', 'init', '--quiet', str(project)], check=True, capture_output=True, timeout=10)
                owner['projects'][name] = _identity(project)
                if project_revision(project) != baseline['baseline_revision']:
                    raise ValueError('Worker copy differs from original baseline')
            atomic_write_json(workspace / 'fixture-owner.json', owner)
        atomic_write_json(workspace / 'baseline.json', report)
    else:
        baseline = read_json(workspace / 'baseline.json')
        if baseline['status'] != 'baseline_failure_observed' or set(owner['projects']) != {'original', 'left', 'right'}:
            raise ValueError('Real independent pre-fix failures and both owned workers are required')
        if phase == 'propose':
            if (workspace / 'proposal.json').exists():
                raise ValueError('Proposal already recorded; do not repeat model calls implicitly')
            proposals = {name: _execute(plane, workspace / name, workspace, config, _entry(workspace / name, name))
                         for name in CASES}
            report.update(status='approval_required' if all(item.get('patch_plan_id') for item in proposals.values())
                          else 'blocked', proposals=proposals, proposal_scheduling='serial')
            atomic_write_json(workspace / 'proposal.json', report)
        elif phase == 'workers':
            if (workspace / 'workers.json').exists():
                raise ValueError('Worker execution already started; reconcile instead of resending')
            proposals = read_json(workspace / 'proposal.json')['proposals']
            approvals = {}
            for name, identifier in config['approved_plan_ids'].items():
                plan = load_patch_plan(plane, identifier)
                target, _, before, after = CASES[name]
                if (proposals[name].get('patch_plan_id') != identifier or plan['intent'] != _entry(workspace / name, name)['intent']
                        or plan['patch']['expected_text'] != before or plan['patch']['replacement_text'] != after
                        or plan['expected_revision'] != baseline['baseline_revision'] or plan['intent']['target_source'] != target):
                    raise ValueError('Explicitly approved worker diff differs from the fixed scenario')
                approvals[name] = approve_csharp_fix(plane, identifier)['approval_ref']
            atomic_write_json(workspace / 'workers.json', {'approved_plan_ids': config['approved_plan_ids'],
                              'approval_refs': approvals, 'parallel_enabled': config['parallel_enabled']})
            tasks, parameters, contract = _tasks(plane, workspace, config)
            result = plane.execute_workspace_tasks(tasks, run_id='parallel-e2e', definition_fingerprint=_fingerprint(),
                task_parameters=parameters, root_contract=contract, parallel_enabled=config['parallel_enabled'],
                timeout_seconds=config['timeout_seconds'])
            if all(record['status'] == 'verified' for record in result['tasks'].values()):
                integration = plane.create_integration_plan(run_id='parallel-e2e')
                report.update(status='integration_approval_required', integration=integration)
            report['result'] = result
        else:
            worker_mode = read_json(workspace / 'workers.json')['parallel_enabled']
            if worker_mode != config['parallel_enabled']:
                raise ValueError('Parallel mode changed between workers and integration')
            staged = read_json(workspace / 'workers-report.json')['integration']
            if staged['integration_plan_id'] != config['approved_integration_plan_id']:
                raise ValueError('Approved integration Plan differs from staged union')
            approval = plane.approve_integration(integration_plan_id=config['approved_integration_plan_id'])
            before = {name: snapshot_workspace_hashes(original / name) for name in ('Assets', 'Packages', 'ProjectSettings')}
            result = plane.integrate_workspace_results(run_id='parallel-e2e',
                integration_plan_id=config['approved_integration_plan_id'], approval_ref=approval['approval_ref'],
                original_parameters=_parameters(original, workspace, config), timeout_seconds=config['timeout_seconds'])
            after = {name: snapshot_workspace_hashes(original / name) for name in before}
            changed = sorted(f'{name}/{path}' for name in before for path in set(before[name]) | set(after[name])
                             if before[name].get(path) != after[name].get(path))
            expected = sorted(item[0] for item in CASES.values())
            overlap = result.get('observed_worker_overlap_ns', 0)
            passed = (result['status'] == 'verified' and changed == expected
                      and project_revision(original) == staged['result_revision']
                      and (not config['parallel_enabled'] or overlap > 0))
            report.update(status='passed' if passed else 'blocked', result=result, changed_paths=changed)
    report['duration_ns'] = time.monotonic_ns() - started
    atomic_write_json(workspace / (phase + '-report.json'), report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='prepare→propose→workers→integrate。workersはapproved_plan_ids、integrateはapproved_integration_plan_idの明示を必要とする。既存workspaceをprepareで上書きせず、不確定実行を再送しない。実Unity6000.3.15f1/Test Framework1.3.9と実Codex接続が必要。')
    parser.add_argument('--input', type=Path, required=True, help='parallel_csharp_e2e.schema.jsonに従うJSON。各段階の報告とEvidenceはworkspace_rootへ保存')
    args = parser.parse_args(argv)
    try:
        report = run(json.loads(args.input.read_text()))
    except (OSError, ValueError, KeyError, ValidationError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] in {'passed', 'baseline_failure_observed', 'approval_required', 'integration_approval_required'} else 1


if __name__ == '__main__':
    sys.exit(main())
