"""親だけが追記するworker dispatch／barrier／受理の監査履歴。"""
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.persistence.state.plan import append_plan_audit, read_plan, read_plan_audit
from unityagent.persistence.store.atomic_store import relative_ref, sha256_json, write_immutable_json


def append_parallel_event(store, state, phase, **payload):
    refs = state.setdefault('parallel_execution_refs', [])
    event = {**payload, 'schema_version': '1.0', 'run_id': state['run_id'], 'phase': phase,
             'sequence': len(refs), 'previous_ref': refs[-1] if refs else None,
             'plan_ref': state['active_plan_ref'], 'mode_digest': sha256_json(state['parallel_execution'])}
    path = store.layout.snapshot(state['run_id'], 'parallel-execution', sha256_json(event))
    write_immutable_json(path, event)
    ref = relative_ref(store.layout.root, path)
    append_plan_audit(store, state, kind='parallel', ref=ref)
    refs.append(ref)
    store.save_task_state(state)
    return ref


def verify_parallel_history(plane, state):
    store, run_id = plane.state_store, state['run_id']
    audit = [event['ref'] for event in read_plan_audit(store, state) if event['kind'] == 'parallel']
    folder = store.layout.run_root(run_id) / 'snapshots/parallel-execution'
    persisted = {relative_ref(store.layout.root, path) for path in folder.glob('*.json')}
    if not audit and not persisted and 'parallel_execution' not in state:
        return
    mode = state.get('parallel_execution')
    refs = state.get('parallel_execution_refs')
    if (not isinstance(mode, dict) or mode.get('schema_version') != '1.0' or mode.get('max_workers') != 2
            or not isinstance(mode.get('enabled'), bool) or refs != audit or set(refs) != persisted
            or len(refs) % 3):
        raise ValueError('Parallel dispatch history is incomplete; reconciliation required')
    events = []
    for sequence, ref in enumerate(refs):
        event = decision_snapshot(store.layout, ref, run_id, 'parallel-execution')
        if (event.get('schema_version') != '1.0' or event['sequence'] != sequence
                or event.get('mode_digest') != sha256_json(mode)
                or event['previous_ref'] != (refs[sequence - 1] if sequence else None)):
            raise ValueError('Parallel dispatch chain differs')
        events.append(event)
    accepted = []
    for index in range(0, len(events), 3):
        dispatch, settled, receipt = events[index:index + 3]
        if ([value['phase'] for value in (dispatch, settled, receipt)] != ['dispatching', 'settled', 'accepted']
                or settled['dispatch_ref'] != refs[index] or receipt['dispatch_ref'] != refs[index]
                or receipt['settled_ref'] != refs[index + 1] or not settled['all_workers_stopped']
                or settled.get('timed_out') or settled.get('cancelled')):
            raise ValueError('Parallel worker barrier was not accepted')
        plan = read_plan(store.layout, dispatch['plan_ref'], run_id)
        outcomes = {item['task_id']: item for item in settled['outcomes']}
        if len(outcomes) != len(dispatch['jobs']) or len(dispatch['jobs']) not in (1, 2):
            raise ValueError('Parallel worker result coverage differs')
        for job in dispatch['jobs']:
            name = job['task_id']
            record = state['tasks'][name]
            outcome = outcomes[name]
            task = next(task for task in plan['tasks'] if task['id'] == name)
            if (name in accepted or job['attempt'] != 0 or job['child_run_id'] != f'{run_id}-{name}'
                    or job['plan_digest'] != sha256_json(plan)
                    or job['task_definition_digest'] != plan['task_digests'][name]
                    or record['accepted_plan_ref'] != dispatch['plan_ref']
                    or record['input_project_revisions'][task['workspace']] != job['input_revision']
                    or record['result']['run_id'] != job['child_run_id']
                    or outcome['result_digest'] != sha256_json(record['result'])
                    or receipt['task_receipt_refs'][name] != state['task_receipt_refs'][name]):
                raise ValueError('Parallel child, Plan, revision, or Acceptance binding differs')
            accepted.append(name)
    if accepted != state['execution_order']:
        raise ValueError('Parallel execution order differs from accepted barriers')
