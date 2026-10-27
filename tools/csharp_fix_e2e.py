#!/usr/bin/env python3
"""所有Fixtureだけで実モデル・実Unityの限定C#経路を段階実行する。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
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
FIXTURE = ROOT / 'Packages/com.darumappap.unity-agent/Editor/Verification~/tests/unity/projects/csharp-local-fix'
TARGET = 'Assets/Calculator.cs'
TEST = 'UnityAgent.AdaptiveFixture.Tests.CalculatorTests.AddReturnsSum'


def _identity(project):
    info = project.stat()
    return {'device': info.st_dev, 'inode': info.st_ino}


def _source_revision():
    try:
        revision = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        dirty = bool(subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'],
            capture_output=True, text=True, check=True, timeout=5).stdout.strip())
        return {'commit': revision, 'dirty': dirty}
    except (OSError, subprocess.SubprocessError):
        return {'commit': None, 'dirty': None}


def _entry(project, *, verify=False):
    intent = {'kind': 'csharp_local_fix', 'goal_or_confirmed_error': 'Calculator.Add(3, 2) returns 1; the sum must be 5',
        'target_source': TARGET, 'expected_behavior': 'Return the sum for positive, negative and zero operands',
        'allowed_changes': 'Replace only the existing Add return expression; preserve declarations and every other file',
        'expected_revision': project_revision(project), 'editmode_tests': [TEST]}
    if verify:
        intent['verification_only'] = True
    return {'schema_version': '2.0', 'request_id': 'owned-csharp-fixture', 'entry_point': 'codex_plugin',
            'project_root': str(project), 'intent': intent}


def _run(plane, project, config, entry, workspace):
    snapshot = discover_environment(str(project), mutation_allowed_paths=[TARGET]).to_dict()
    native = NativeUnityEditorProvider(project, snapshot, temp_root=workspace / 'native-output')
    return plane.execute(entry, run_id='csharp-e2e-' + uuid.uuid4().hex,
        environment_snapshot=snapshot, context=ResolutionContext(policy_allowed=True),
        definition_fingerprint=_fingerprint(), reasoning_model=config['model'],
        reasoning_timeout_seconds=config['timeout_seconds'],
        executors={'file': FileProvider(project).execute, 'native_unity_editor': native.execute},
        provider_arguments={'native_unity_editor': {'timeout_seconds': config['timeout_seconds']}})


def run(config):
    schema = json.loads(Path(__file__).with_suffix('.schema.json').read_text())
    Draft202012Validator(schema).validate(config)
    workspace = Path(config['workspace_root']).absolute()
    if workspace.resolve() != workspace:
        raise ValueError('E2E workspace aliases are prohibited')
    project = workspace / 'project'
    marker = workspace / 'fixture-owner.json'
    phase = config['phase']
    if phase == 'prepare':
        # 既存Projectやユーザー変更へコピー・削除しない。
        workspace.mkdir(parents=True, exist_ok=False)
        shutil.copytree(FIXTURE, project)
        atomic_write_json(marker, {'schema_version': '1.0', 'fixture': 'csharp-local-fix',
                                  'project_root': str(project), 'project_identity': _identity(project)})
    if project.resolve(strict=True) != project:
        raise ValueError('E2E Project alias is prohibited')
    owner = read_json(marker)
    if owner != {'schema_version': '1.0', 'fixture': 'csharp-local-fix', 'project_root': str(project),
                 'project_identity': _identity(project)}:
        raise ValueError('E2E workspace ownership differs')
    for path in project.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
            raise ValueError('E2E Project contains a file or directory alias')
    plane = UnityAgentControlPlane(workspace / 'state')
    report = {'schema_version': '1.0', 'phase': phase, 'execution_kind': 'real',
              'source_revision': _source_revision(), 'unity_version': '6000.3.15f1',
              'test_framework_version': '1.3.9', 'model': config['model'], 'status': 'blocked'}
    if phase == 'prepare':
        initial_revision = project_revision(project)
        result = _run(plane, project, config, _entry(project, verify=True), workspace)
        # 初回importによるlockfile等の作成は所有Fixtureに限る。修正の再送はしない。
        if project_revision(project) != result.get('result_revision'):
            raise ValueError('Fixture changed after its verification receipt')
        if (project_revision(project) != initial_revision
                and not any(item.get('capability') == 'project.test' for item in result['results'])):
            if (project / TARGET).read_bytes() != (FIXTURE / TARGET).read_bytes():
                raise ValueError('Fixture source changed during import')
            result = _run(plane, project, config, _entry(project, verify=True), workspace)
        test_results = [item for item in result['results'] if item.get('capability') == 'project.test']
        observed_failure = bool(test_results) and test_results[0].get('provider_result', {}).get('failure_class') == 'observed_test_failure'
        report.update(status='baseline_failure_observed' if observed_failure else 'unavailable', result=result,
                      baseline_revision=project_revision(project))
        atomic_write_json(workspace / 'baseline.json', report)
    elif phase == 'propose':
        result = _run(plane, project, config, _entry(project), workspace)
        report.update(status='approval_required' if result.get('patch_plan_id') else 'blocked', result=result)
        atomic_write_json(workspace / 'proposal.json', report)
    else:
        baseline = read_json(workspace / 'baseline.json')
        if baseline['status'] != 'baseline_failure_observed':
            raise ValueError('A real independent pre-fix test failure is required before apply')
        plan = load_patch_plan(plane, config['approved_plan_id'])
        entry = _entry(project)
        if (plan['intent'] != entry['intent'] or plan['expected_revision'] != baseline['baseline_revision']
                or plan['patch']['expected_text'] != 'return a - b;'
                or plan['patch']['replacement_text'] != 'return a + b;'):
            raise ValueError('Approved fixture patch differs from its fixed expected diff')
        before = {name: snapshot_workspace_hashes(project / name) for name in ('Assets', 'Packages', 'ProjectSettings')}
        approval = approve_csharp_fix(plane, config['approved_plan_id'])
        entry['intent']['patch_plan_id'] = config['approved_plan_id']
        entry['approval_ref'] = approval['approval_ref']
        result = _run(plane, project, config, entry, workspace)
        after = {name: snapshot_workspace_hashes(project / name) for name in before}
        changed = [f'{name}/{path}' for name in before for path in set(before[name]) | set(after[name])
                   if before[name].get(path) != after[name].get(path)]
        passed = (result['status'] == 'completed' and changed == [TARGET]
                  and project_revision(project) == plan['result_revision'])
        report.update(status='passed' if passed else 'blocked', result=result, changed_paths=changed)
    atomic_write_json(workspace / (phase + '-report.json'), report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='prepare:新規専用Fixtureと修正前Test。propose:読取専用モデル提案。apply:確認済みapproved_plan_idを明示し固定期待差分のみ承認・適用。成功以外は非zero。既存workspaceはprepareで上書きしない。')
    parser.add_argument('--input', required=True, type=Path, help='csharp_fix_e2e.schema.jsonに従うJSON。結果とEvidenceはworkspace_root配下へ保存')
    args = parser.parse_args(argv)
    try:
        report = run(json.loads(args.input.read_text()))
    except (ValueError, OSError, KeyError, ValidationError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] in {'passed', 'baseline_failure_observed', 'approval_required'} else 1


if __name__ == '__main__':
    sys.exit(main())
