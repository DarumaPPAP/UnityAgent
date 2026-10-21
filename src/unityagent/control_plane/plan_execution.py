"""確定境界でだけ動的Planを更新し、既存Task実行へ現在の定義を渡す。"""
from copy import deepcopy

from jsonschema import ValidationError

from unityagent.control_plane.measurement import measured_call, record_counters
from unityagent.orchestration.graph.plan import create_plan, revise_plan
from unityagent.persistence.state.plan import append_plan_audit, commit_plan, read_active_plan, read_plan, read_plan_audit, stage_plan
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.persistence.store.atomic_store import relative_ref, sha256_json, write_immutable_json


def initialize_plan(plane, state, tasks, root):
    value = create_plan(run_id=state['run_id'], root_contract=root,
        definition_fingerprint=state['definition_fingerprint'], tasks=tasks,
        project_revisions=state['project_revisions'])
    state.update(schema_version='2.0', initial_contract_digest=state['contract_digest'],
        plan_event_refs=[], plan_proposal_refs=[], plan_proposals_consumed=0,
        plan_boundary_task_ids=[], cancelled_tasks={}, task_receipt_refs={}, plan_audit_refs=[])
    commit_plan(plane.state_store, state, stage_plan(plane.state_store.layout, value), expected_ref=None)


def _task_receipt(plane, state, name):
    record = state['tasks'][name]
    payload = {'run_id': state['run_id'], 'task_id': name, 'record_digest': sha256_json(record),
               'plan_ref': record['accepted_plan_ref'], 'definition_digest': record['task_definition_digest']}
    path = plane.state_store.layout.snapshot(state['run_id'], 'plan-task', sha256_json(payload))
    write_immutable_json(path, payload)
    ref = relative_ref(plane.state_store.layout.root, path)
    append_plan_audit(plane.state_store, state, kind='task', ref=ref)
    state['task_receipt_refs'][name] = ref


def verify_task_receipts(plane, state, tasks):
    layout, run_id = plane.state_store.layout, state['run_id']
    executed = {name for name, record in state['tasks'].items() if record['handoff_history']}
    refs = state.get('task_receipt_refs', {})
    if set(refs) != executed or set(state['execution_order']) != executed or len(state['execution_order']) != len(executed):
        raise ValueError('Dynamic Task Attempt history coverage differs')
    persisted = {relative_ref(layout.root, p) for p in (layout.run_root(run_id) / 'snapshots/plan-task').glob('*.json')}
    if persisted != set(refs.values()):
        raise ValueError('Dynamic Task receipt history differs')
    by_id = {t['id']: t for t in tasks}
    for name, ref in refs.items():
        payload = decision_snapshot(layout, ref, run_id, 'plan-task')
        record = state['tasks'][name]
        if payload != {'run_id': run_id, 'task_id': name, 'record_digest': sha256_json(record),
                       'plan_ref': record['accepted_plan_ref'], 'definition_digest': sha256_json(by_id[name])}:
            raise ValueError('Dynamic Task state differs from immutable Acceptance')
        accepted = read_plan(layout, payload['plan_ref'], run_id)
        if accepted['task_digests'].get(name) != payload['definition_digest']:
            raise ValueError('Dynamic Attempt Plan or definition differs')
        from unityagent.control_plane.task_execution import _acceptance
        expected = _acceptance(plane, record['result'], by_id[name]['required_gates'], state['definition_fingerprint'], verify=True)
        if expected != record['gates'] or record['status'] != ('verified' if record['result']['status'] == 'completed'
                and all(v == 'passed' for v in expected.values()) else 'blocked'):
            raise ValueError('Dynamic Task Acceptance differs from Evidence')


def restore_plan(plane, state, initial_tasks, root):
    current = read_active_plan(plane.state_store, state)
    audit = read_plan_audit(plane.state_store, state)
    if ('parallel_execution' in state or any(event['kind'] == 'parallel' for event in audit)
            or (plane.state_store.layout.run_root(state['run_id']) / 'snapshots/parallel-execution').exists()):
        from unityagent.persistence.state.parallel_execution import verify_parallel_history
        verify_parallel_history(plane, state)
    if ([event['ref'] for event in audit if event['kind'] == 'proposal'] != state['plan_proposal_refs']
            or [event['ref'] for event in audit if event['kind'] == 'task'] != [
                state['task_receipt_refs'][name] for name in state['execution_order']]):
        raise ValueError('Plan audit journal coverage differs')
    if (state['initial_contract_digest'] != sha256_json(initial_tasks) or current['root_contract'] != root
            or current['definition_fingerprint'] != state['definition_fingerprint']):
        raise ValueError('Initial Task or immutable Root contract changed during resume')
    if set(state['tasks']) != {task['id'] for task in current['tasks']}:
        raise ValueError('Active Plan Task state set differs')
    contract = decision_snapshot(plane.state_store.layout, state['contract_ref'], state['run_id'], 'task-contract')
    if contract != {'tasks': current['tasks'], 'definition_fingerprint': state['definition_fingerprint']}:
        raise ValueError('Active Plan contract snapshot differs')
    if state.get('plan_proposal_in_progress'):
        raise ValueError('Plan proposal was interrupted; reconciliation required')
    refs = state['plan_proposal_refs']
    folder = plane.state_store.layout.run_root(state['run_id']) / 'snapshots/plan-proposal'
    if state['plan_proposals_consumed'] != len(refs) or set(refs) != {
            relative_ref(plane.state_store.layout.root, p) for p in folder.glob('*.json')}:
        raise ValueError('Plan proposal budget history differs')
    validated = []
    for sequence, ref in enumerate(refs):
        proposal = decision_snapshot(plane.state_store.layout, ref, state['run_id'], 'plan-proposal')
        if proposal['sequence'] != sequence or proposal['previous_ref'] != (refs[sequence - 1] if sequence else None):
            raise ValueError('Plan proposal chain differs')
        base = read_plan(plane.state_store.layout, proposal['base_ref'], state['run_id'])
        try:
            revised = revise_plan(base, proposal['proposal'], task_states=proposal['task_states'],
                evidence_refs=proposal['evidence_refs'], proposals_consumed=sequence + 1, project_revisions=proposal['project_revisions'])
            from unityagent.control_plane.task_execution import validate_tasks
            validate_tasks(plane, revised['tasks'], state['run_id'],
                {name: dict.fromkeys(keys) for name, keys in proposal['parameter_keys'].items()})
        except (ValueError, KeyError, TypeError, ValidationError):
            if proposal['outcome'] != 'rejected':
                raise ValueError('Plan proposal rejection differs')
        else:
            if proposal['outcome'] != 'validated' or sha256_json(revised) != proposal['result_digest']:
                raise ValueError('Plan validation receipt differs')
            validated.append(proposal['result_digest'])
    if current['revision'] != len(validated) or (validated and validated[-1] != sha256_json(current)):
        raise ValueError('Validated Plan activation history is incomplete')
    if state['contract_digest'] != sha256_json(current['tasks']):
        raise ValueError('Active Plan Task contract differs')
    verify_task_receipts(plane, state, current['tasks'])
    evidence_history = []
    for name in state['execution_order']:
        record = state['tasks'][name]
        observations = record.get('strategy_observation_refs', [])
        if len(observations) != len(record['handoff_history']):
            raise ValueError('Dynamic Evidence history has a missing Attempt observation')
        for attempt, ref in enumerate(observations):
            observed = decision_snapshot(plane.state_store.layout, ref, state['run_id'], 'strategy-observation')
            child = record['handoff_history'][attempt]['run_id']
            if (observed['run_id'] != state['run_id'] or observed['task_id'] != name
                    or observed['attempt'] != attempt or observed['result_run_id'] != child):
                raise ValueError('Dynamic Evidence history Attempt binding differs')
            for evidence_id in observed['evidence_refs']:
                plane.evidence_store.verify_record(evidence_id, expected_run_id=child)
            evidence_history.extend(observed['evidence_refs'])
    if state['evidence_refs'] != evidence_history:
        raise ValueError('Dynamic Evidence history differs from executed Attempts')
    return deepcopy(current['tasks'])


def update_plan(plane, state, tasks, by_id, parameters, completed, proposer, *, record_boundary=True):
    if record_boundary:
        _task_receipt(plane, state, completed)
        state['plan_boundary_task_ids'].append(completed)
        plane.state_store.save_task_state(state)
    elif completed not in state['task_receipt_refs']:
        raise ValueError('Plan update requires a settled Task receipt')
    if proposer is None or state['plan_proposals_consumed'] >= 4:
        return
    current = read_active_plan(plane.state_store, state)
    state['plan_proposal_in_progress'] = completed
    plane.state_store.save_task_state(state)
    proposal = measured_call(plane, state['run_id'], 'coordination', proposer, {'plan_digest': sha256_json(current), 'plan': deepcopy(current),
        'completed_task_id': completed, 'project_revisions': dict(state['project_revisions']), 'evidence_refs': list(state['tasks'][completed]['result'].get('evidence_refs', []))})
    state.pop('plan_proposal_in_progress')
    if proposal is None:
        plane.state_store.save_task_state(state)
        return
    count = state['plan_proposals_consumed'] + 1
    payload = {'run_id': state['run_id'], 'sequence': count - 1,
        'previous_ref': state['plan_proposal_refs'][-1] if state['plan_proposal_refs'] else None,
        'base_ref': state['active_plan_ref'], 'proposal': deepcopy(proposal),
        'task_states': {name: {'status': record['status']} for name, record in state['tasks'].items()},
        'evidence_refs': list(state['evidence_refs']), 'outcome': 'rejected', 'result_digest': None,
        'parameter_keys': {name: sorted(value) for name, value in parameters.items()},
        'project_revisions': dict(state['project_revisions'])}
    revised = None
    try:
        for ref in proposal.get('evidence_refs', []):
            plane.evidence_store.verify_record(ref)
        candidate = revise_plan(current, proposal, task_states=payload['task_states'],
            evidence_refs=state['evidence_refs'], proposals_consumed=count, project_revisions=state['project_revisions'])
        from unityagent.control_plane.task_execution import validate_tasks
        validate_tasks(plane, candidate['tasks'], state['run_id'], parameters)
        revised = candidate
        payload.update(outcome='validated', result_digest=sha256_json(revised))
    except (ValueError, KeyError, TypeError, ValidationError):
        pass
    record_counters(plane, state['run_id'], 'coordination', plan_proposals=1, plan_rejections=int(revised is None))
    path = plane.state_store.layout.snapshot(state['run_id'], 'plan-proposal', sha256_json(payload))
    write_immutable_json(path, payload)
    ref = relative_ref(plane.state_store.layout.root, path)
    append_plan_audit(plane.state_store, state, kind='proposal', ref=ref)
    state['plan_proposal_refs'].append(ref)
    state['plan_proposals_consumed'] = count
    plane.state_store.save_task_state(state)
    if revised is None:
        return
    # active参照とTask集合は一度のatomic state更新で切り替える。
    new_state = deepcopy(state)
    new_tasks = {task['id']: task for task in revised['tasks']}
    for name in set(by_id) - set(new_tasks):
        new_state['cancelled_tasks'][name] = {'definition': by_id[name], 'record': new_state['tasks'].pop(name)}
    for name, task in new_tasks.items():
        if name not in new_state['tasks']:
            new_state['tasks'][name] = {'status': 'pending', 'gates': {g: 'not_observed' for g in task['required_gates']},
                                      'handoff_history': [], 'semantic_retries': 0}
        elif by_id[name] != task:
            new_state['tasks'][name]['gates'] = {g: 'not_observed' for g in task['required_gates']}
    contract_digest = sha256_json(revised['tasks'])
    contract_path = plane.state_store.layout.snapshot(state['run_id'], 'task-contract', contract_digest)
    write_immutable_json(contract_path, {'tasks': revised['tasks'], 'definition_fingerprint': state['definition_fingerprint']})
    new_state.update(contract_digest=contract_digest, contract_ref=relative_ref(plane.state_store.layout.root, contract_path))
    commit_plan(plane.state_store, new_state, stage_plan(plane.state_store.layout, revised), expected_ref=state['active_plan_ref'])
    state.clear()
    state.update(new_state)
    tasks[:] = deepcopy(revised['tasks'])
    by_id.clear()
    by_id.update(new_tasks)


def verify_final_gates(plane, state, tasks):
    root = read_active_plan(plane.state_store, state)['root_contract']
    from unityagent.control_plane.task_execution import project_revision
    current = {project: project_revision(project) for project in root['projects']}
    state['project_revisions'] = current
    state['evidence_validity'] = {name: 'current' if record.get('result_project_revisions') == current else 'stale'
                                  for name, record in state['tasks'].items() if record.get('result')}
    observed = set()
    by_id = {task['id']: task for task in tasks}
    integration_final = {task['id'] for task in tasks if task['workspace'] == root['project_root']
        and task['entry_request']['intent'].get('verification_only')
        and task['entry_request']['intent'].get('integration_plan_id')}
    for name, record in state['tasks'].items():
        if by_id[name]['workspace'] != root['project_root']:
            continue
        if integration_final and name not in integration_final:
            continue
        if (record['status'] == 'verified' or name in integration_final) and record.get('result_project_revisions') == current:
            for gate, value in record['gates'].items():
                if value == 'passed':
                    observed.add(gate)
    state['final_gates'] = {gate: 'passed' if gate in observed else 'not_observed' for gate in root['required_gates']}
    if any(value != 'passed' for value in state['final_gates'].values()):
        state['status'] = 'blocked'


def verify_dynamic_boundary(plane, state, tasks, *, task_id=None, attempt=0):
    current = read_active_plan(plane.state_store, state)
    if current['tasks'] != tasks or current['definition_fingerprint'] != state['definition_fingerprint']:
        raise ValueError('Dynamic Plan contract differs')
    # 現在の修復Attemptだけを除き、確定済みTaskを保存時の定義・Evidenceへ戻す。
    settled = deepcopy(state)
    if task_id is not None:
        settled['tasks'][task_id] = {**settled['tasks'][task_id], 'handoff_history': []}
        settled['task_receipt_refs'].pop(task_id, None)
        settled['execution_order'] = [name for name in settled['execution_order'] if name != task_id]
    verify_task_receipts(plane, settled, tasks)
    refs = state.get('dag_decision_refs', [])
    if not refs:
        if state['execution_order'] or attempt:
            raise ValueError('Dynamic Acceptance boundary is missing')
        return None
    from unityagent.orchestration.routing.adaptive_execution import read_dag_decision
    record = read_dag_decision(plane.state_store.layout.root, refs[-1], run_id=state['run_id'])
    if record['schema_version'] != '2.0' or record['definition_fingerprint'] != state['definition_fingerprint']:
        raise ValueError('Dynamic boundary version or definition differs')
    if record['project_revisions'] != {sha256_json(p): r for p, r in state['project_revisions'].items()}:
        raise ValueError('Dynamic boundary Project revision differs')
    if attempt and (record['boundary']['task_id'] != task_id or record['boundary']['attempt'] != attempt - 1):
        raise ValueError('Dynamic repair boundary differs')
    return record


def validate_dynamic_preparation(plane, state, task, candidate, preparation, *, attempt):
    from unityagent.orchestration.routing.strategy_application import validate_preparation
    from unityagent.control_plane.task_execution import project_revision
    contract = decision_snapshot(plane.state_store.layout, state['contract_ref'], state['run_id'], 'task-contract')
    prepared = {'run_id': state['run_id'], 'task_id': task['id'], 'attempt': attempt,
        'result_run_id': preparation['handoff']['run_id'], 'entry_digest': sha256_json(candidate),
        'proof_ref': preparation['proof_ref'], 'manifest_ref': preparation['manifest_ref'],
        'handoff': preparation['handoff'], 'selection_inputs': preparation['selection_inputs'],
        'project_facts': preparation['project_facts'], 'project_revisions': state['project_revisions'],
        'plan_ref': state['active_plan_ref']}
    validate_preparation(plane.state_store.layout, prepared, contract)
    if {project: project_revision(project) for project in state['project_revisions']} != state['project_revisions']:
        raise ValueError('Dynamic preparation Project revision changed')
    return True
