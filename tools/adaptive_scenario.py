#!/usr/bin/env python3
"""固定比較用の所有Fixtureを実Control Planeへ渡し、構造化した測定結果だけを保存する。"""
import argparse
import importlib.util
from pathlib import Path
import json
import shutil
import subprocess
import time

from unityagent.cli import _fingerprint
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.persistence.store.atomic_store import read_json, sha256_json, write_immutable_json
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider

ROOT = Path(__file__).resolve().parents[1]


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(workspace, name):
    project = workspace / name
    shutil.copytree(ROOT / 'tests/unity/projects/parallel-csharp-fix', project)
    subprocess.run(['git', 'init', '--quiet', str(project)], check=True, capture_output=True, timeout=10)
    return project


def _inspection(workspace, kind, variant):
    workspace.mkdir(parents=True, exist_ok=False)
    first = _project(workspace, 'first')
    final = _project(workspace, 'followup') if kind == 'dynamic' else first
    plane, run_id = UnityAgentControlPlane(workspace / 'state'), 'comparison-' + kind
    gates = {'project': ['project_fact']}
    def task(name, project, dependencies):
        return {'id': name, 'workspace': str(project), 'depends_on': dependencies,
            'goal': 'Inspect the authorized ' + project.name + ' Project', 'read_set': ['.'], 'write_set': [],
            'parallel_safe': True, 'resource_claims': [], 'required_gates': gates,
            'entry_request': {'schema_version': '2.0', 'request_id': name, 'entry_point': 'codex_plugin',
                              'project_root': str(project), 'intent': {'kind': 'project_inspection'}}}
    first_task, followup = task('initial', first, []), task('followup', final, ['initial'])
    tasks = [first_task]
    parameters = {item['id']: {'environment_snapshot': discover_environment(item['workspace']).to_dict(),
        'context': ResolutionContext(policy_allowed=True),
        'executors': {'file': FileProvider(item['workspace']).execute}} for item in [first_task, followup]}
    root = {'goal': 'Inspect the final authorized Project after the initial inspection',
        'project_root': str(final), 'projects': {str(project): {'read_set': ['.'], 'write_set': []} for project in {first, final}},
        'required_gates': gates, 'approval_conditions': ['existing_policy'], 'allowed_entry_kinds': ['project_inspection']}
    if kind == 'fast':
        # 同一の単一Fast入口。並列flagはworker作成や余分な準備を発生させない。
        state = plane.execute_workspace_tasks(tasks, run_id=run_id, definition_fingerprint=_fingerprint(),
            task_parameters=parameters, root_contract=root, parallel_enabled=variant == 'C')
    elif variant == 'A':
        state = plane.execute_tasks(tasks, run_id=run_id, definition_fingerprint=_fingerprint(),
            task_parameters=parameters, root_contract=root)
    else:
        def propose(boundary):
            if boundary['completed_task_id'] != 'initial':
                return None
            # 最初のdurable Evidenceが得られた後だけ、固定Root内の追加調査を提案する。
            records = [plane.evidence_store.verify_record(ref) for ref in boundary['evidence_refs']]
            if not records or not all(record['verification_status'] == 'passed' for record in records):
                return None
            return {'base_digest': boundary['plan_digest'], 'tasks': [first_task, followup],
                    'reason': 'Inspect the authorized followup Project after confirmed initial inspection',
                    'evidence_refs': boundary['evidence_refs']}
        state = plane.execute_workspace_tasks(tasks, run_id=run_id, definition_fingerprint=_fingerprint(),
            task_parameters=parameters, root_contract=root, parallel_enabled=variant == 'C', plan_proposer=propose)
    return plane, run_id, state


def _parallel(workspace, variant, conditions):
    if conditions.get('authorize_owned_fixture_patches') is not True:
        raise ValueError('The frozen configuration must explicitly authorize the owned fixture arithmetic patches and their union')
    if conditions['model_settings'] != {'reasoning_effort': 'high'}:
        raise ValueError('This fixture adapter supports the fixed high reasoning setting only')
    if (conditions['unity_version'] != '6000.3.15f1'
            or conditions['packages'] != {'com.unity.test-framework': '1.3.9'}):
        raise ValueError('Frozen Unity and Package versions differ from the owned fixture')
    e2e = _tool('parallel_csharp_e2e')
    config = {'schema_version': '1.0', 'workspace_root': str(workspace), 'phase': 'prepare',
              'model': conditions['model'], 'timeout_seconds': conditions['timeout_seconds'], 'parallel_enabled': variant == 'C'}
    report = e2e.run(config)
    plane = UnityAgentControlPlane(workspace / 'state')
    if report['status'] != 'baseline_failure_observed':
        return plane, None, {'status': 'unavailable'}
    proposals = e2e.run({**config, 'phase': 'propose'})
    if proposals['status'] != 'approval_required':
        return plane, None, {'status': 'blocked'}
    identifiers = {name: proposal['patch_plan_id'] for name, proposal in proposals['proposals'].items()}
    # workersは固定expected diffとの一致を検証してから既存Approval APIを呼ぶ。
    workers = e2e.run({**config, 'phase': 'workers', 'approved_plan_ids': identifiers})
    if workers['status'] != 'integration_approval_required' or variant == 'A':
        # 固定経路Aは実行途中にTaskを追加せず、原ProjectのGate未達で安全に止まる。
        return plane, 'parallel-e2e', workers['result']
    integrated = e2e.run({**config, 'phase': 'integrate',
                          'approved_integration_plan_id': workers['integration']['integration_plan_id']})
    state = integrated['result']
    if integrated['status'] != 'passed':
        state = {**state, 'status': 'blocked'}
    return plane, 'parallel-e2e', state


def run(*, conditions_path, scenario_id, variant, workspace, report_path):
    frozen = read_json(conditions_path)
    conditions = frozen['config']
    if frozen['digest'] != sha256_json(conditions):
        raise ValueError('Frozen conditions digest differs')
    comparison = _tool('adaptive_comparison')
    from jsonschema import Draft202012Validator
    Draft202012Validator(comparison._schema()).validate(conditions)
    scenario = next(item for item in conditions['scenarios'] if item['id'] == scenario_id)
    if workspace != workspace.resolve() or workspace.exists() or variant not in 'ABC' or len(variant) != 1:
        raise ValueError('A new unaliased owned workspace and exact comparison variant are required')
    started = time.monotonic_ns()
    if scenario['kind'] == 'parallel':
        plane, run_id, state = _parallel(workspace, variant, conditions)
    else:
        plane, run_id, state = _inspection(workspace, scenario['kind'], variant)
    metrics_path = plane.state_store.layout.root / 'operations/metric.jsonl'
    metrics = [json.loads(line) for line in metrics_path.read_text().splitlines()] if metrics_path.exists() else []
    def total(*names):
        return sum(record['value'] for record in metrics if record['metric_name'] in names)
    provider_ns = int(total('adaptive.provider.duration', 'adaptive.gate.duration', 'adaptive.model.duration') * 1e6)
    elapsed = time.monotonic_ns() - started
    passed = state['status'] == 'verified'
    context_manifests = [read_json(path) for path in (workspace / 'state').glob('runs/*/snapshots/context-manifest/*.json')]
    context_preserved = bool(context_manifests) and all(
        manifest['budget_report']['decision'] == 'within_budget'
        and not manifest['materialized_context']['unresolved_bindings'] for manifest in context_manifests)
    report = {'schema_version': '1.0', 'execution_kind': 'real', 'conditions_digest': frozen['digest'],
        'scenario': scenario_id, 'variant': variant, 'adaptive_enabled': variant != 'A', 'parallel_enabled': variant == 'C',
        'status': 'passed' if passed else 'unavailable' if state['status'] == 'unavailable' else 'blocked',
        'quality_passed': passed, 'evidence_verified': False,
        'evidence': {'persistence_root': str(plane.state_store.layout.root), 'run_id': run_id} if run_id else None,
        'context_preserved': context_preserved, 'redundant_context_copies': 0,
        'coordination_ns': max(1, elapsed - provider_ns) if scenario['kind'] == 'fast' else max(1, int(total(
            'adaptive.preparation.duration', 'adaptive.context.duration', 'adaptive.coordination.duration', 'adaptive.lease.duration') * 1e6)),
        'safety_incidents': int(state.get('parallel_reconciliation_required', False)),
        'workers': 2 if state.get('observed_worker_overlap_ns', 0) > 0 else 0, 'worktrees': 0,
        'observed_worker_overlap_ns': state.get('observed_worker_overlap_ns', 0),
        'preparations': int(total('adaptive.preparation.calls')), 'project_scans': int(total('adaptive.project.scan.calls')),
        'model_calls': int(total('adaptive.model.calls')),
        'provider_calls': int(total('adaptive.provider.provider_calls', 'adaptive.gate.provider_calls')),
        'unnecessary_calls': 0, 'actual_usage': None}
    usage_path = plane.state_store.layout.root / 'operations/trace.jsonl'
    usage = [record['attributes'] for record in map(json.loads, usage_path.read_text().splitlines())
             if record.get('event_type') == 'adaptive.model_usage'] if usage_path.exists() else []
    if usage and len(usage) == report['model_calls'] and all(
            item.get('usage_source') == 'codex.turn.completed.usage'
            and item.get('configured_model') == conditions['model']
            and all(type(item.get(key)) is int for key in ('input_tokens', 'output_tokens')) for item in usage):
        report['actual_usage'] = {'source': 'codex.turn.completed.usage', 'model': conditions['model'], 'unit': 'tokens',
            **{key: sum(item[key] for item in usage) if all(type(item.get(key)) is int for item in usage) else None
               for key in ('input_tokens', 'output_tokens', 'cached_input_tokens')}}
    # 保存済み契約を再検証するcollectorが、成功の自己申告を上書きする。
    write_immutable_json(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='Fastは通常inspection、dynamicは初回Evidence後の許可Project追加調査、parallelは2件の限定C#修正。Aは途中更新なし、Bは適応直列、Cは並列opt-in。parallelには固定条件のauthorize_owned_fixture_patches:trueが必要。既存Projectを上書きしない。')
    parser.add_argument('--conditions', type=Path, required=True)
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--variant', choices=['A', 'B', 'C'], required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(conditions_path=args.conditions, scenario_id=args.scenario, variant=args.variant,
                     workspace=args.workspace.absolute(), report_path=args.report.absolute())
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError):
        # 詳細なProvider本文やモデル出力をbenchmark stdoutへ追加しない。
        print(json.dumps({'status': 'blocked', 'reason': 'Scenario failed; inspect owned workspace Evidence'}))
        return 1
    print(json.dumps({'status': report['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
