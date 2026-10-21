"""既存Control Plane実行をDAGの成功依存と固定Acceptanceへ接続する。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time

from unityagent.control_plane.dag_observation import observe_dag_boundary
from unityagent.orchestration.graph.resource_planning import plan_task_batches
from unityagent.persistence.checkpoint.checkpoint_store import CheckpointStore
from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.persistence.store.atomic_store import safe_id, sha256_json, write_immutable_json, relative_ref
from unityagent.persistence.store.measurement import observed
from unityagent.runtime.sandbox.workspace_guard import snapshot_workspace_hashes


@observed('project.scan')
def project_revision(project: str | Path) -> str:
    project = Path(project).resolve(strict=True)
    return sha256_json({name: snapshot_workspace_hashes(project / name)
                        for name in ('Assets', 'Packages', 'ProjectSettings')})


def _acceptance(plane, result, gates, definition, *, verify=False):
    effective = result.get('handoff', {}).get('definition_fingerprint', definition)
    if any(effective.get(k) != v for k, v in definition.items() if k not in {'policy_revision', 'context_revision'}):
        raise ValueError('Runtime definition revision differs')
    from unityagent.orchestration.qa.task_acceptance import assess_task
    records = [plane.evidence_store.verify_record(ref, expected_run_id=result['run_id']) if verify else plane.evidence_store.get(ref)
               for ref in result.get('evidence_refs', [])]
    prior_context = None
    if result.get('orchestration_decision_ref'):
        from unityagent.persistence.state.dag_decision import decision_snapshot
        layout = plane.state_store.layout
        proof = decision_snapshot(layout, result['orchestration_decision_ref'], result['run_id'], 'orchestration-decision')
        if proof.get('previous_context_manifest_ref'):
            previous = decision_snapshot(layout, proof['previous_context_manifest_ref'], result['run_id'], 'context-manifest')
            if previous['run_id'] != result['run_id'] or proof['context_manifest_ref'] != result['context_manifest_ref']:
                raise ValueError('Prior Context binding differs')
            prior_context = {'definition_fingerprint': {**effective, **{key: previous['materialized_context']['definition_fingerprint'][key]
                for key in ('policy_revision', 'context_revision')}}, 'evidence_ids': proof['observation_evidence_refs'],
                'capability_requests': proof['capability_requests'], 'step_id': result['handoff']['step_id']}
    return assess_task(records,
        required_gates=gates, run_id=result['run_id'], definition_fingerprint=effective, prior_context=prior_context)['gates']


def validate_tasks(plane, tasks, run_id, task_parameters):
    by_id = {}
    for task in tasks:
        identifier = safe_id(task['id'], 'task_id')
        safe_id(f'{run_id}-{identifier}', 'task_run_id')
        from unityagent.control_plane.unity_agent_control_plane import validate_entry_request
        validate_entry_request(task['entry_request'])
        project = str(Path(task['entry_request']['project_root']).resolve(strict=True))
        if project != str(Path(task['workspace']).resolve(strict=True)):
            raise ValueError('Task workspace must match Entry project')
        state_root = plane.state_store.layout.root
        if Path(project) == state_root or Path(project) in state_root.parents:
            raise ValueError('DAG Persistence must be outside the Project')
        gates = task.get('required_gates')
        if not isinstance(gates, dict) or not gates or any(
                not isinstance(k, str) or not k or not isinstance(v, list) or not v or
                any(not isinstance(x, str) or not x for x in v) for k, v in gates.items()):
            raise ValueError('Required gates must be fixed before Task execution')
        if not isinstance(task.get('goal'), str) or not task['goal'].strip():
            raise ValueError('Task goal is required')
        if identifier not in task_parameters or set(task_parameters[identifier]) & {'run_id', 'definition_fingerprint', 'entry_request', '_strategy_consumer'}:
            raise ValueError('Task runtime parameters missing or override identity')
        candidates = task.get('repair_candidates', [])
        repair_limit = task.get('semantic_repair_limit', 2)
        if not isinstance(candidates, list) or isinstance(repair_limit, bool) or not isinstance(repair_limit, int) or repair_limit < 0:
            raise ValueError('Semantic repair requires finite Task budget and fixed candidates')
        for candidate in candidates:
            validate_entry_request(candidate)
            if Path(candidate['project_root']).resolve() != Path(project):
                raise ValueError('Semantic repair cannot change Task Project')
        by_id[identifier] = task
    return by_id


def execute_task_dag(plane, tasks, *, run_id, definition_fingerprint, task_parameters, resume=False, adaptive_strategy_enabled=False, root_contract=None, plan_proposer=None):
    """Task自体の権限を増やさず、既存executeで得た永続Evidenceだけで依存を開く。

    初期Schedulerは直列。parallel planを速度向上の実測と混同しない。
    実行途中の再開は副作用が不確定なので自動再送しない。
    """
    if root_contract is None and plan_proposer is not None:
        raise ValueError('Plan proposer requires an explicit Root contract')
    if not isinstance(adaptive_strategy_enabled, bool):
        raise ValueError('Adaptive strategy mode must be boolean')
    definition = deepcopy(dict(definition_fingerprint))
    validate_definition_fingerprint(definition)
    safe_id(run_id, 'run_id')
    tasks = deepcopy(tasks)
    initial_tasks = deepcopy(tasks)
    if resume:
        existing = plane.state_store.load_task_state(run_id)
        if ('parallel_execution' in existing or
                (plane.state_store.layout.run_root(run_id) / 'snapshots/parallel-execution').exists()):
            raise ValueError('Workspace execution must Resume through execute_workspace_tasks')
        if (existing.get('schema_version') == '2.0') != (root_contract is not None):
            raise ValueError('Dynamic Plan mode changed during resume')
        if root_contract is not None:
            from unityagent.control_plane.plan_execution import restore_plan
            tasks = restore_plan(plane, existing, initial_tasks, root_contract)
    plan = plan_task_batches(tasks)
    by_id = validate_tasks(plane, tasks, run_id, task_parameters)
    contract_digest = sha256_json(tasks)
    projects = sorted(root_contract['projects']) if root_contract is not None else sorted({str(Path(t['workspace']).resolve()) for t in tasks})
    revisions = {p: project_revision(p) for p in projects}
    if resume:
        state = plane.state_store.load_task_state(run_id)
        if state.get('adaptive_strategy_enabled', False) != adaptive_strategy_enabled:
            raise ValueError('Adaptive strategy mode changed during resume')
        if state['contract_digest'] != contract_digest:
            raise ValueError('Task contract changed during resume')
        if state['definition_fingerprint'] != definition or state['project_revisions'] != revisions:
            raise ValueError('Task definition or Project revision changed during resume')
        if any(t['status'] == 'running' for t in state['tasks'].values()):
            raise ValueError('Uncertain external side effects require reconciliation before resume')
    else:
        path = plane.state_store.layout.run_root(run_id) / 'current/task-state.json'
        if path.exists():
            raise ValueError('Run already exists; explicit resume is required')
        state = {'schema_version': '1.0', 'run_id': run_id, 'status': 'running',
                 'contract_digest': contract_digest, 'definition_fingerprint': definition,
                 'project_revisions': revisions, 'execution_order': [], 'evidence_refs': [],
                 'scheduling': 'serial', 'parallel_speedup': 'unmeasured',
                 'tasks': {i: {'status': 'pending', 'gates': {g: 'not_observed' for g in t['required_gates']},
                              'handoff_history': [], 'semantic_retries': 0} for i, t in by_id.items()}}
        contract = plane.state_store.layout.snapshot(run_id, 'task-contract', contract_digest)
        write_immutable_json(contract, {'tasks': tasks, 'definition_fingerprint': definition})
        state['contract_ref'] = relative_ref(plane.state_store.layout.root, contract)
        if root_contract is not None:
            from unityagent.control_plane.plan_execution import initialize_plan
            initialize_plan(plane, state, tasks, root_contract)
    from unityagent.control_plane.strategy_application import prepare_application, finalize_application, verify_application_state
    application_root = plane.state_store.layout.run_root(run_id) / 'snapshots/strategy-application'
    if adaptive_strategy_enabled:
        if not resume:
            state.update(adaptive_strategy_enabled=True, strategy_application_refs=[], coordination_path=None)
        else:
            verify_application_state(plane, state, tasks)
    elif application_root.exists():
        raise ValueError('Adaptive strategy mode or history was removed')
    plane.state_store.save_task_state(state)
    stop_dispatch = False
    def schedule():
        if root_contract is None:
            for batch in plan['batches']:
                yield from batch['task_ids']
            return
        while True:
            pending = [name for name, item in state['tasks'].items() if item['status'] == 'pending']
            ready = [name for name in pending if all(state['tasks'][dep]['status'] == 'verified'
                     for dep in by_id[name].get('depends_on', []))]
            if not ready:
                for name in pending:
                    state['tasks'][name]['status'] = 'blocked_dependency'
                return
            yield sorted(ready)[0]

    for identifier in schedule():
        task, record = by_id[identifier], state['tasks'][identifier]
        if stop_dispatch:
            break
        if record['status'] == 'verified':
            continue
        if any(state['tasks'][dep]['status'] != 'verified' for dep in task.get('depends_on', [])):
            record['status'] = 'blocked_dependency'
            plane.state_store.save_task_state(state)
            continue
        # blocked/failed Taskを再開だけで再送しない。修正は別承認Taskとして再計画する。
        if record['status'] != 'pending':
            continue
        if not adaptive_strategy_enabled and {p: project_revision(p) for p in projects} != state['project_revisions']:
            raise ValueError('Project revision changed before Task dispatch')
        record['status'] = 'running'
        plane.state_store.save_task_state(state)
        from unityagent.runtime.reference_implementation.authority import RuntimeBudgetLedger
        from unityagent.orchestration.loop.semantic_loop import decide_semantic_loop
        candidates = [task['entry_request'], *task.get('repair_candidates', [])]
        ledger = RuntimeBudgetLedger({'max_global_replans': task.get('semantic_repair_limit', 2)})
        prior_failure = None
        for attempt, candidate in enumerate(candidates):
            if attempt > task.get('semantic_repair_limit', 2):
                break
            child_run = f'{run_id}-{identifier}' + (f'-repair{attempt}' if attempt else '')
            safe_id(child_run, 'task_run_id')
            record['status'] = 'running'
            plane.state_store.save_task_state(state)
            dispatch_revisions = dict(state['project_revisions'])
            start = time.monotonic()
            application = None
            parameters = dict(task_parameters[identifier])
            parameters['_host_resource_claims'] = task.get('resource_claims', [])
            if adaptive_strategy_enabled:
                def consume(preparation):
                    nonlocal application
                    application = prepare_application(plane, state, tasks, task_id=identifier,
                        attempt=attempt, candidate=candidate, preparation=preparation, project_revision=project_revision)
                    return application is not None
                parameters['_strategy_consumer'] = consume
            elif root_contract is not None:
                from unityagent.control_plane.plan_execution import validate_dynamic_preparation
                parameters['_strategy_consumer'] = lambda preparation: validate_dynamic_preparation(
                    plane, state, task, candidate, preparation, attempt=attempt)
            try:
                result = plane.execute(candidate, run_id=child_run,
                    definition_fingerprint=definition, **parameters)
            except BaseException as exc:
                if adaptive_strategy_enabled and application is not None:
                    from unityagent.persistence.state.strategy_application import save_application
                    try:
                        save_application(plane, state, {**application, 'phase': 'interrupted',
                            'uncertain_side_effects': True, 'error_type': type(exc).__name__})
                    except (OSError, ValueError):
                        # dispatchingが残ればResumeは不確定なAttemptを再送しない。
                        pass
                raise
            if adaptive_strategy_enabled and application is None:
                # 受理されないAttemptの後へ進まず、未実行Taskはpendingのまま保持する。
                stop_dispatch = True
            record['latency_ms'] = record.get('latency_ms', 0) + (time.monotonic() - start) * 1000
            record['result'] = result
            record['gates'] = _acceptance(plane, result, task['required_gates'], definition, verify=adaptive_strategy_enabled)
            if root_contract is not None:
                record['accepted_plan_ref'] = state['active_plan_ref']
                record['task_definition_digest'] = sha256_json(task)
                record['input_project_revisions'] = dispatch_revisions
                record['result_project_revisions'] = {p: project_revision(p) for p in projects}
            record['status'] = 'verified' if result['status'] == 'completed' and all(
                g == 'passed' for g in record['gates'].values()) else 'blocked'
            # Acceptance確定後のAttemptに結び付ける。Resume時はこの境界を再実行しない。
            if result.get('handoff'):
                observed = plane._observe_strategy(result, observation_run_id=run_id,
                    task_id=identifier, attempt=attempt, gates=record['gates'])
                record.setdefault('strategy_observation_refs', []).extend(observed['strategy_observation_refs'])
                if observed.get('strategy_observation_diagnostics'):
                    record.setdefault('strategy_observation_diagnostics', []).extend(observed['strategy_observation_diagnostics'])
            else:
                record.setdefault('strategy_observation_diagnostics', []).append(
                    {'code': 'observation_not_available', 'attempt': attempt})
            record['handoff_history'].append({'run_id': result['run_id'],
                'decision_ref': result.get('orchestration_decision_ref'),
                'requested_subagent': candidate.get('requested_subagent')})
            state['evidence_refs'].extend(result.get('evidence_refs', []))
            state['project_revisions'] = {p: project_revision(p) for p in projects}
            plane.state_store.save_task_state(state)
            failures = [item.get('provider_result') or {} for item in result.get('results', [])]
            failure = sha256_json([{'failure_class': f.get('failure_class'), 'reason': f.get('reason')} for f in failures])
            # 不確定な外部副作用/環境不足/権限拒否は意味的修正で再送しない。
            repairable = (record['status'] != 'verified' and 'failed' in record['gates'].values()
                and all(r.get('operation_kind') == 'read' for r in result.get('handoff', {}).get('capability_requests', []))
                and any(f.get('failure_class') == 'execution_failed' for f in failures)
                and all(f.get('failure_class') in {None, 'execution_failed'} for f in failures))
            decision = decide_semantic_loop(
                {'id': identifier, 'continue_on': ['validation_failed'], 'replan_on': [], 'exit_on': ['passed']},
                outcome='passed' if record['status'] == 'verified' else 'validation_failed',
                semantic_attempt=attempt, progress_marker=failure,
                progress_made=failure != prior_failure, blocked=not repairable and record['status'] != 'verified')
            record['semantic_decision'] = decision
            observe_dag_boundary(plane, tasks, state, task_id=identifier, attempt=attempt,
                dispatch_revisions=dispatch_revisions)
            if adaptive_strategy_enabled and application is not None:
                try:
                    finalize_application(plane, state, application, task_id=identifier, attempt=attempt)
                except (OSError, ValueError) as exc:
                    # 実行済みEvidenceを保持し、保存失敗を理由に同じProviderへ再送しない。
                    state.setdefault('strategy_application_diagnostics', []).append(
                        {'code': 'application_result_incomplete', 'task_id': identifier,
                         'attempt': attempt, 'error_type': type(exc).__name__})
                    plane.state_store.save_task_state(state)
                    raise ValueError('Application result incomplete; reconciliation required') from exc
            if (decision['decision'] != 'continue' or attempt + 1 >= len(candidates)
                    or attempt >= task.get('semantic_repair_limit', 2)):
                break
            ledger.consume('global_replans')
            record['semantic_retries'] += 1
            prior_failure = failure
        record['budget_counts'] = ledger.snapshot()
        state['execution_order'].append(identifier)
        plane.state_store.save_task_state(state)
        if root_contract is not None:
            from unityagent.control_plane.plan_execution import update_plan
            update_plan(plane, state, tasks, by_id, task_parameters, identifier, plan_proposer)
    state['status'] = 'verified' if all(t['status'] == 'verified' for t in state['tasks'].values()) else 'blocked'
    if root_contract is not None:
        from unityagent.control_plane.plan_execution import verify_final_gates
        verify_final_gates(plane, state, tasks)
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    plane.state_store.save_task_state(state)
    digest = sha256_json(state)
    snapshot = plane.state_store.layout.snapshot(run_id, 'task-state', digest)
    write_immutable_json(snapshot, state)
    plane._save_execution_state(run_id=run_id, step_id='task-dag', action_id='execute-tasks',
        status='completed' if state['status'] == 'verified' else 'blocked', evidence_refs=state['evidence_refs'])
    plane._save_workflow_state(run_id=run_id, route_id='task-dag', node_id='acceptance',
        evidence_refs=state['evidence_refs'] + [relative_ref(plane.state_store.layout.root, snapshot)])
    checkpoint_id = 'tasks-' + digest.split(':')[1][:24]
    CheckpointStore(plane.state_store.layout.root).create(checkpoint_id=checkpoint_id, run_id=run_id,
        reason='Task DAG acceptance; state only, not Unity Asset restore', loop_ids=[],
        evidence_refs=state['evidence_refs'], definition_fingerprint=definition)
    return {**state, 'checkpoint_id': checkpoint_id}
