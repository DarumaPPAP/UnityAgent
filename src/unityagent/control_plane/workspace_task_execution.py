"""別Projectの子Runだけを並列化し、親がbarrier後のAcceptanceとPlanを所有する。"""
from copy import deepcopy
from pathlib import Path
import threading
import time

from unityagent.control_plane.measurement import measured_call, measurement_binding
from unityagent.control_plane.dag_observation import observe_dag_boundary
from unityagent.control_plane.plan_execution import initialize_plan, restore_plan, update_plan, validate_dynamic_preparation, verify_final_gates
from unityagent.control_plane.task_execution import _acceptance, project_revision, validate_tasks
from unityagent.orchestration.graph.resource_planning import plan_ready_batch
from unityagent.orchestration.loop.semantic_loop import decide_semantic_loop
from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.persistence.state.parallel_execution import append_parallel_event, verify_parallel_history
from unityagent.persistence.state.plan import read_active_plan
from unityagent.persistence.store.atomic_store import relative_ref, safe_id, sha256_json, write_immutable_json
from unityagent.runtime.reference_implementation.authority import RuntimeBudgetLedger
from unityagent.runtime.sandbox.parallel_workspaces import verify_worker_workspaces, observe_project_identities

WORKSPACE_DISPATCH_TOKEN = object()


def verify_project_bindings(state):
    expected = state['parallel_execution']['project_identities']
    if set(expected) != set(state['project_revisions']) or observe_project_identities(expected) != expected:
        raise ValueError('Physical Project identity changed since the initial Root binding')

def _observations(plane, tasks, parameters, original, run_id):
    workers = []
    for task in tasks:
        native = parameters[task['id']]['executors'].get('native_unity_editor')
        owner = getattr(native, '__self__', None)
        if native is not None:
            from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider
            if not isinstance(owner, NativeUnityEditorProvider):
                return {'status': 'blocked', 'reason': 'native_output_not_observed', 'workspaces': {}}
        output = owner.temp_root if native is not None else None
        if task['workspace'] == original:
            if output is not None:
                resolved = Path(output).absolute()
                if resolved != resolved.resolve() or resolved == Path(original) or Path(original) in resolved.parents:
                    raise ValueError('Original Editor output must be unaliased and outside the Project')
            continue
        snapshot = parameters[task['id']]['environment_snapshot']
        workers.append({'task_id': task['id'], 'workspace': task['workspace'], 'output_root': str(Path(output).absolute()) if output is not None else None,
                        'environment_snapshot': snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot})
    return verify_worker_workspaces(original, workers)


def execute_workspace_dag(plane, tasks, *, run_id, definition_fingerprint, task_parameters,
                          root_contract, parallel_enabled=False, resume=False, plan_proposer=None,
                          timeout_seconds=300.0, cancel_event=None):
    if not isinstance(parallel_enabled, bool) or timeout_seconds <= 0:
        raise ValueError('Workspace execution needs a boolean mode and a bounded timeout')
    if root_contract is None:
        raise ValueError('Workspace execution requires an immutable Root contract')
    safe_id(run_id, 'run_id')
    deadline = time.monotonic() + timeout_seconds
    definition = deepcopy(dict(definition_fingerprint))
    validate_definition_fingerprint(definition)
    initial_tasks, tasks = deepcopy(tasks), deepcopy(tasks)
    original = root_contract['project_root']
    state_path = plane.state_store.layout.run_root(run_id) / 'current/task-state.json'
    if resume:
        state = plane.state_store.load_task_state(run_id)
        expected_mode = {'schema_version': '1.0', 'enabled': parallel_enabled, 'max_workers': 2,
                         'original_project': original}
        mode = state.get('parallel_execution', {})
        if (any(mode.get(key) != value for key, value in expected_mode.items())
                or state['definition_fingerprint'] != definition):
            raise ValueError('Workspace execution mode or definition changed during Resume')
        verify_project_bindings(state)
        tasks = restore_plan(plane, state, initial_tasks, root_contract)
        verify_parallel_history(plane, state)
        if any(record['status'] == 'running' for record in state['tasks'].values()):
            raise ValueError('Uncertain worker effects require reconciliation before Resume')
    elif state_path.exists():
        raise ValueError('Workspace Run already exists; explicit Resume is required')
    by_id = validate_tasks(plane, tasks, run_id, task_parameters)
    if any(task.get('repair_candidates') or task['entry_request']['intent']['kind'] not in
           {'project_inspection', 'csharp_local_fix'} for task in tasks):
        raise ValueError('Isolated workers support bounded C# and inspection tasks without implicit repair')
    projects = sorted(root_contract['projects'])
    revisions = {project: project_revision(project) for project in projects}
    if resume:
        if state['project_revisions'] != revisions:
            raise ValueError('Workspace Project revision changed during Resume')
    else:
        digest = sha256_json(tasks)
        contract_path = plane.state_store.layout.snapshot(run_id, 'task-contract', digest)
        write_immutable_json(contract_path, {'tasks': tasks, 'definition_fingerprint': definition})
        state = {'schema_version': '2.0', 'run_id': run_id, 'status': 'running', 'contract_digest': digest,
            'contract_ref': relative_ref(plane.state_store.layout.root, contract_path), 'definition_fingerprint': definition,
            'project_revisions': revisions, 'execution_order': [], 'evidence_refs': [],
            'parallel_execution': {'schema_version': '1.0', 'enabled': parallel_enabled, 'max_workers': 2,
                                   'original_project': original,
                                   'project_identities': observe_project_identities(root_contract['projects'])}, 'parallel_execution_refs': [],
            'observed_worker_overlap_ns': 0, 'scheduling': 'isolated_workspaces',
            'tasks': {name: {'status': 'pending', 'gates': {gate: 'not_observed' for gate in task['required_gates']},
                             'handoff_history': [], 'semantic_retries': 0} for name, task in by_id.items()}}
        initialize_plan(plane, state, tasks, root_contract)
    plane.state_store.save_task_state(state)
    while True:
        verify_project_bindings(state)
        if (cancel_event is not None and cancel_event.is_set()) or time.monotonic() >= deadline:
            state['cancelled'] = bool(cancel_event and cancel_event.is_set())
            state['timed_out'] = time.monotonic() >= deadline
            break
        if any(task.get('repair_candidates') or task['entry_request']['intent']['kind'] not in
               {'project_inspection', 'csharp_local_fix'} for task in tasks):
            raise ValueError('Current workspace Plan contains an unsupported worker kind or repair')
        verified = {name for name, record in state['tasks'].items() if record['status'] == 'verified'}
        pending = {name for name, record in state['tasks'].items() if record['status'] == 'pending'}
        if not pending:
            break
        selected = measured_call(plane, run_id, 'coordination', plan_ready_batch, tasks, verified_task_ids=verified, pending_task_ids=pending,
            parallel_enabled=parallel_enabled, workspace_status='verified')
        # 元Projectの呼出しは、workerと同時に実行しない。
        if (any(by_id[name]['workspace'] == original for name in selected)
                or len({by_id[name]['workspace'] for name in selected}) < len(selected)):
            selected = selected[:1]
        if not selected:
            for name in pending:
                state['tasks'][name]['status'] = 'blocked_dependency'
            break
        selected_tasks = [by_id[name] for name in selected]
        observation = measured_call(plane, run_id, 'coordination', _observations, plane, selected_tasks, task_parameters, original, run_id)
        if observation['status'] == 'blocked':
            raise ValueError('Native output isolation is not observed')
        if len(selected) == 2 and observation['status'] != 'verified':
            selected = selected[:1]
            selected_tasks = [by_id[selected[0]]]
            observation = measured_call(plane, run_id, 'coordination', _observations, plane, selected_tasks, task_parameters, original, run_id)
        dispatch_revisions = dict(state['project_revisions'])
        if {project: project_revision(project) for project in projects} != dispatch_revisions:
            raise ValueError('Project changed before workspace dispatch')
        plan = read_active_plan(plane.state_store, state)
        accepted_plan_ref = state['active_plan_ref']
        jobs = [{'task_id': name, 'child_run_id': f'{run_id}-{name}', 'attempt': 0,
                 'plan_digest': sha256_json(plan), 'task_definition_digest': sha256_json(by_id[name]),
                 'input_revision': dispatch_revisions[by_id[name]['workspace']]} for name in selected]
        for name in selected:
            state['tasks'][name]['status'] = 'running'
        dispatch_ref = append_parallel_event(plane.state_store, state, 'dispatching', jobs=jobs,
            worker_count=2 if len(jobs) == 2 else 0, workspace_observation=observation)

        def prepare(job, preparation):
            verify_project_bindings(state)
            task = by_id[job['task_id']]
            current_observation = measured_call(plane, run_id, 'coordination', _observations, plane, selected_tasks, task_parameters, original, run_id)
            if (current_observation.get('original_identity') != observation.get('original_identity')
                    or current_observation['workspaces'] != observation['workspaces']):
                raise ValueError('Physical worker or output identity changed before dispatch')
            return validate_dynamic_preparation(plane, state, task, task['entry_request'], preparation, attempt=0)

        def execute(job, consume, cancellation):
            task = by_id[job['task_id']]
            parameters = dict(task_parameters[task['id']])
            parameters.update(_strategy_consumer=consume, cancel_event=cancellation,
                              _host_resource_claims=task.get('resource_claims', []), _execution_deadline=deadline,
                              _workspace_dispatch_token=WORKSPACE_DISPATCH_TOKEN)
            with measurement_binding({**job, 'parent_run_id': run_id}):
                return plane.execute(task['entry_request'], run_id=job['child_run_id'],
                                     definition_fingerprint=definition, **parameters)

        if len(jobs) == 2:
            from unityagent.runtime.execution_control.isolated_worker_batch import run_isolated_batch
            batch = run_isolated_batch(jobs, execute=execute, prepare=prepare,
                                      timeout_seconds=max(.001, deadline - time.monotonic()), cancel_event=cancel_event)
        else:
            job = jobs[0]
            started = time.monotonic_ns()
            result = execute(job, lambda value: prepare(job, value), cancel_event or threading.Event())
            batch = {'all_workers_stopped': True, 'timed_out': time.monotonic() >= deadline, 'cancelled': bool(cancel_event and cancel_event.is_set()),
                'overlap_ns': 0, 'results': [{**job, 'started_ns': started, 'dispatch_started_ns': started,
                                             'finished_ns': time.monotonic_ns(), 'result': result}]}
        outcomes = [{key: value for key, value in envelope.items() if key != 'result'} |
                    {'result_digest': sha256_json(envelope['result']) if 'result' in envelope else None}
                    for envelope in batch['results']]
        settled_ref = append_parallel_event(plane.state_store, state, 'settled', dispatch_ref=dispatch_ref,
            outcomes=outcomes, all_workers_stopped=batch['all_workers_stopped'],
            timed_out=batch['timed_out'], cancelled=batch['cancelled'], overlap_ns=batch['overlap_ns'])
        if (not batch['all_workers_stopped'] or batch['timed_out'] or batch['cancelled']
                or len(outcomes) != len(jobs) or any('error_type' in item for item in outcomes)):
            state.update(status='blocked', parallel_reconciliation_required=True,
                         final_gates={gate: 'not_observed' for gate in root_contract['required_gates']})
            plane.state_store.save_task_state(state)
            return state
        results = {item['task_id']: item['result'] for item in batch['results']}
        if any(results[job['task_id']]['run_id'] != job['child_run_id'] for job in jobs):
            raise ValueError('Workspace result child identity differs')
        final_revisions = {project: project_revision(project) for project in projects}
        if all(by_id[name]['workspace'] != original for name in selected) and final_revisions[original] != dispatch_revisions[original]:
            raise ValueError('Original Project changed during isolated worker execution')
        state['observed_worker_overlap_ns'] += batch['overlap_ns']
        for name in selected:
            task, record, result = by_id[name], state['tasks'][name], results[name]
            record.update(result=result, accepted_plan_ref=accepted_plan_ref,
                task_definition_digest=sha256_json(task), input_project_revisions=dispatch_revisions,
                result_project_revisions=final_revisions)
            record['gates'] = measured_call(plane, run_id, 'evidence', _acceptance, plane, result, task['required_gates'], definition, verify=True)
            record['status'] = 'verified' if result['status'] == 'completed' and all(
                value == 'passed' for value in record['gates'].values()) else 'blocked'
            record['semantic_decision'] = decide_semantic_loop(
                {'id': name, 'continue_on': [], 'replan_on': [], 'exit_on': ['passed']},
                outcome='passed' if record['status'] == 'verified' else 'validation_failed',
                semantic_attempt=0, progress_marker=None, blocked=record['status'] != 'verified')
            record['budget_counts'] = RuntimeBudgetLedger({}).snapshot()
            observed = plane._observe_strategy(result, observation_run_id=run_id, task_id=name, attempt=0,
                                               gates=record['gates'])
            record['strategy_observation_refs'] = observed['strategy_observation_refs']
            record['handoff_history'].append({'run_id': result['run_id'],
                'decision_ref': result.get('orchestration_decision_ref'),
                'requested_subagent': task['entry_request'].get('requested_subagent')})
            state['evidence_refs'].extend(result.get('evidence_refs', []))
            state['project_revisions'] = dict(final_revisions)
            # P2はAcceptanceの直列prefixを読む。実dispatchは別のbarrier履歴が保持する。
            projection = deepcopy(state)
            for waiting in selected[selected.index(name) + 1:]:
                projection['tasks'][waiting]['status'] = 'pending'
            observe_dag_boundary(plane, tasks, projection, task_id=name, attempt=0,
                                 dispatch_revisions=dispatch_revisions)
            for key in ('dag_decision_refs', 'dag_decision_diagnostics'):
                if key in projection:
                    state[key] = projection[key]
            state['execution_order'].append(name)
            update_plan(plane, state, tasks, by_id, task_parameters, name, None)
        append_parallel_event(plane.state_store, state, 'accepted', dispatch_ref=dispatch_ref,
            settled_ref=settled_ref, task_receipt_refs={name: state['task_receipt_refs'][name] for name in selected})
        # workerはすべて停止し、両結果のreceiptを保存した後だけPlanを更新する。
        if plan_proposer is not None:
            for name in selected:
                update_plan(plane, state, tasks, by_id, task_parameters, name, plan_proposer, record_boundary=False)
    state['status'] = 'verified' if all(record['status'] == 'verified' for record in state['tasks'].values()) else 'blocked'
    verify_final_gates(plane, state, tasks)
    plane.state_store.save_task_state(state)
    return state
