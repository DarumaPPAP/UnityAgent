"""既存準備情報を一度だけ受け取り、実行前の受理とAcceptance確定を記録する。"""
from copy import deepcopy
import hashlib
from pathlib import Path

from unityagent.orchestration.graph.resource_planning import plan_task_batches
from unityagent.orchestration.routing.adaptive_execution import read_dag_decision
from unityagent.orchestration.routing.strategy_application import read_strategy_application, select_coordination, validate_preparation
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.persistence.state.strategy_application import save_application
from unityagent.persistence.store.atomic_store import relative_ref, sha256_json, write_immutable_json


def verify_boundary(plane, state, tasks, *, task_id=None, attempt=0):
    refs = state.get('dag_decision_refs', [])
    histories = {name: item['handoff_history'] for name, item in state['tasks'].items()}
    if not refs:
        if any(histories.values()):
            raise ValueError('Prior Acceptance boundary is missing')
        return None
    record = read_dag_decision(plane.state_store.layout.root, refs[-1], run_id=state['run_id'])
    boundary = decision_snapshot(plane.state_store.layout, record['state_ref'], state['run_id'], 'dag-boundary')
    if (record['contract_ref'] != state['contract_ref'] or record['definition_fingerprint'] != state['definition_fingerprint']
            or record['project_revisions'] != {sha256_json(p): r for p, r in state['project_revisions'].items()}):
        raise ValueError('Prior boundary contract, definition or Project revision differs')
    by_id = {task['id']: task for task in tasks}
    order = [name for batch in plan_task_batches(tasks)['batches'] for name in batch['task_ids']]
    for name, old in boundary['task_states'].items():
        current = state['tasks'][name]
        if ([x['run_id'] for x in histories[name]] != [x['run_id'] for x in old['handoff_history']]
                or current['gates'] != old['gates']
                or current.get('semantic_retries', 0) != old['semantic_retries'] + (1 if name == task_id and attempt else 0)
                or {k: current.get('semantic_decision', {}).get(k) for k in old['semantic_decision']} != old['semantic_decision']):
            raise ValueError('Current Task history, budget or Acceptance differs from boundary')
        expected = 'running' if name == task_id else old['status']
        if (old['status'] == 'pending' and name != task_id
                and (task_id is None or order.index(name) < order.index(task_id))
                and any(state['tasks'][dep]['status'] != 'verified' for dep in by_id[name].get('depends_on', []))):
            expected = 'blocked_dependency'
        if current['status'] != expected:
            raise ValueError('Current Task status differs from boundary')
        if histories[name]:
            candidates = [by_id[name]['entry_request'], *by_id[name].get('repair_candidates', [])]
            observations = current.get('strategy_observation_refs', [])
            if len(observations) != len(histories[name]):
                raise ValueError('Current Attempt observation history differs')
            for index, entry in enumerate(histories[name]):
                observed = decision_snapshot(plane.state_store.layout, observations[index], state['run_id'], 'strategy-observation')
                if (observed['task_id'] != name or observed['attempt'] != index or observed['result_run_id'] != entry['run_id']
                        or observed['orchestration_decision_ref'] != entry['decision_ref']
                        or entry['requested_subagent'] != candidates[index].get('requested_subagent')):
                    raise ValueError('Current Attempt descriptor differs from verified observation')
            if name != task_id:
                from unityagent.runtime.reference_implementation.authority import RuntimeBudgetLedger
                counts = {key: 0 for key in RuntimeBudgetLedger.COUNTERS}
                counts['global_replans'] = current['semantic_retries']
                if current.get('budget_counts') != counts:
                    raise ValueError('Current Task budget counters differ from fixed Attempts')
        if current.get('result'):
            sources = [source for source in record['sources'] if source['task_id'] == name]
            evidence_ids = {s['evidence_id'] for s in sources if s['kind'] == 'evidence'}
            result = current['result']
            if set(result.get('evidence_refs', [])) != evidence_ids or result['run_id'] != histories[name][-1]['run_id']:
                raise ValueError('Current child result Evidence set differs')
            observations = [decision_snapshot(plane.state_store.layout, s['ref'], s['run_id'], 'strategy-observation')
                            for s in sources if s['kind'] == 'strategy-observation']
            if (len(observations) != 1 or observations[0]['result_status'] != result['status']
                    or observations[0]['context_manifest_ref'] != result.get('context_manifest_ref')
                    or observations[0]['orchestration_decision_ref'] != result.get('orchestration_decision_ref')
                    or observations[0]['definition_fingerprint'] != result.get('handoff', {}).get('definition_fingerprint')):
                raise ValueError('Current child result status differs')
    prior = order[:order.index(task_id)] if task_id else order
    if state['execution_order'] != [name for name in prior if histories[name]]:
        raise ValueError('Fixed Task execution order differs')
    return record


def prepare_application(plane, state, tasks, *, task_id, attempt, candidate, preparation, project_revision):
    """Route/Contextを共有し、通常のProject走査を送信直前へ集約する。"""
    from unityagent.runtime.execution_control import strategy
    layout = plane.state_store.layout
    task = next(task for task in tasks if task['id'] == task_id)
    contract = decision_snapshot(layout, state['contract_ref'], state['run_id'], 'task-contract')
    if contract != {'tasks': tasks, 'definition_fingerprint': state['definition_fingerprint']}:
        raise ValueError('Fixed Task contract differs')
    prepared = {'run_id': state['run_id'], 'task_id': task_id, 'attempt': attempt,
        'result_run_id': preparation['handoff']['run_id'], 'entry_digest': sha256_json(candidate),
        'proof_ref': preparation['proof_ref'], 'manifest_ref': preparation['manifest_ref'],
        'handoff': deepcopy(preparation['handoff']), 'selection_inputs': deepcopy(preparation['selection_inputs']),
        'project_facts': deepcopy(preparation['project_facts']), 'project_revisions': dict(state['project_revisions'])}
    validate_preparation(layout, prepared, contract)
    # 必須の状態照合はFastにも適用する。深い出所監査はRuntime側のモードが選択する。
    prior_ref = state.get('dag_decision_refs', [None])[-1]
    prior = read_dag_decision(layout.root, prior_ref, run_id=state['run_id']) if attempt else None
    decision = select_coordination(prepared, task, current_path=state.get('coordination_path'), boundary=prior)
    path = layout.snapshot(state['run_id'], 'strategy-preparation', sha256_json(prepared))
    write_immutable_json(path, prepared)
    payload = {'task_id': task_id, 'attempt': attempt, 'contract_ref': state['contract_ref'],
        'preparation_ref': relative_ref(layout.root, path), 'prior_boundary_ref': prior_ref,
        'decision': decision, 'phase': 'prepared', 'applied': False, 'receipt': None}
    save_application(plane, state, payload)

    def verify_prepared():
        stored = decision_snapshot(layout, payload['preparation_ref'], state['run_id'], 'strategy-preparation')
        if sha256_json(stored) != sha256_json(prepared) or state['project_revisions'] != prepared['project_revisions']:
            raise ValueError('Prepared dispatch identity changed')
        validate_preparation(layout, stored, contract)
        durable = plane.state_store.load_task_state(state['run_id'])
        for key in ('tasks', 'execution_order', 'contract_ref', 'definition_fingerprint', 'project_revisions', 'coordination_path'):
            if durable[key] != state[key]:
                raise ValueError('Prepared Task state changed before dispatch')
        # Contextが実際に読んだファイルだけを再照合する。全Projectの走査は増やさない。
        project = Path(task['workspace']).resolve()
        for fact in stored['project_facts']:
            source = Path(fact['source_path']).resolve(strict=True)
            if project not in source.parents or fact['freshness']['status'] != 'current' or (
                    'sha256:' + hashlib.sha256(source.read_bytes()).hexdigest()) != fact['revision']:
                raise ValueError('Prepared Project Fact is stale')
        expected = task['entry_request'] if attempt == 0 else task['repair_candidates'][attempt - 1]
        if sha256_json(candidate) != sha256_json(expected):
            raise ValueError('Prepared Task contract changed')

    def audit_boundary():
        return verify_boundary(plane, state, tasks, task_id=task_id, attempt=attempt)

    def audit_dag():
        current_contract = decision_snapshot(layout, state['contract_ref'], state['run_id'], 'task-contract')
        if current_contract != contract:
            raise ValueError('Fixed DAG changed')
        plan_task_batches(current_contract['tasks'])
        if any(state['tasks'][dep]['status'] != 'verified' for dep in task.get('depends_on', [])):
            raise ValueError('Fixed DAG dependency Acceptance is not verified')
        writes = prepared['handoff']['mutation_scope'].get('allowed_paths', [])
        declared = task.get('write_set', [])
        if any(not any(value == scope or value.startswith(scope.rstrip('/') + '/') for scope in declared) for value in writes):
            raise ValueError('Prepared mutation Scope is outside the fixed DAG write set')

    try:
        receipt = strategy.consume_strategy(decision, prepared, verify_prepared=verify_prepared,
            verify_boundary=audit_boundary, verify_dag=audit_dag)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        save_application(plane, state, {**payload, 'phase': 'rejected', 'error_type': type(exc).__name__})
        return None
    payload = {**payload, 'phase': 'accepted', 'applied': True, 'receipt': receipt}
    state['coordination_path'] = decision['path']
    save_application(plane, state, payload)
    # 受理の永続化後にも、保存中に変わった束縛を確認する。失敗時はdispatchしない。
    verify_prepared()
    save_application(plane, state, {**payload, 'phase': 'dispatching'})
    verify_prepared()
    # 従来のTask開始時走査をこの境界へ移し、準備・永続化中のAsset変更も送信前に拒否する。
    if {project: project_revision(project) for project in prepared['project_revisions']} != prepared['project_revisions']:
        raise ValueError('Project revision changed before Task dispatch')
    return payload


def finalize_application(plane, state, payload, *, task_id, attempt):
    if payload is None:
        return
    refs = state.get('dag_decision_refs', [])
    if not refs:
        raise ValueError('Result Acceptance boundary unavailable')
    boundary = read_dag_decision(plane.state_store.layout.root, refs[-1], run_id=state['run_id'])
    if (boundary['boundary']['task_id'], boundary['boundary']['attempt']) != (task_id, attempt):
        raise ValueError('Result Acceptance boundary differs')
    save_application(plane, state, {**payload, 'phase': 'finalized', 'boundary_ref': refs[-1],
        'gates': dict(state['tasks'][task_id]['gates'])})


def verify_application_state(plane, state, tasks):
    refs = state.get('strategy_application_refs', [])
    folder = plane.state_store.layout.run_root(state['run_id']) / 'snapshots/strategy-application'
    persisted = {relative_ref(plane.state_store.layout.root, path) for path in folder.glob('*.json')}
    if set(refs) != persisted:
        raise ValueError('Application history differs from immutable records; reconciliation required')
    if not refs:
        if any(item['handoff_history'] for item in state['tasks'].values()):
            raise ValueError('Application history is missing')
        return
    final = read_strategy_application(plane.state_store.layout.root, refs[-1], run_id=state['run_id'])
    if final['sequence'] != len(refs) - 1 or final['phase'] not in {'finalized', 'rejected'}:
        raise ValueError('Application result is incomplete; reconciliation required')
    expected_path = final['decision']['path'] if final['applied'] else final['decision']['current_path']
    if state.get('coordination_path') != expected_path:
        raise ValueError('Current coordination mode differs from accepted application')
    cursor = refs[-1]
    finalized = set()
    for expected in reversed(refs):
        if cursor != expected:
            raise ValueError('Application history order differs')
        value = decision_snapshot(plane.state_store.layout, cursor, state['run_id'], 'strategy-application')
        if value['phase'] == 'finalized':
            finalized.add((value['task_id'], value['attempt']))
        cursor = value['previous_ref']
    if cursor:
        raise ValueError('Application history was truncated')
    executed = {(name, attempt) for name, item in state['tasks'].items() for attempt in range(len(item['handoff_history']))}
    boundaries = state.get('dag_decision_refs', [])
    if finalized != executed or final.get('boundary_ref') != (boundaries[-1] if boundaries else None):
        raise ValueError('Application history differs from executed Attempts or latest Acceptance')
    verify_boundary(plane, state, tasks)
