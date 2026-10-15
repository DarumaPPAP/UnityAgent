"""既存Control Plane実行をDAGの成功依存と固定Acceptanceへ接続する。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time

from unityagent.orchestration.graph.resource_planning import plan_task_batches
from unityagent.persistence.checkpoint.checkpoint_store import CheckpointStore
from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.persistence.store.atomic_store import safe_id, sha256_json, write_immutable_json, relative_ref
from unityagent.runtime.sandbox.workspace_guard import snapshot_workspace_hashes


def project_revision(project: str | Path) -> str:
    project = Path(project).resolve(strict=True)
    return sha256_json({name: snapshot_workspace_hashes(project / name)
                        for name in ('Assets', 'Packages', 'ProjectSettings')})


def _acceptance(plane, result, gates, definition):
    effective = result.get('handoff', {}).get('definition_fingerprint', definition)
    if any(effective.get(k) != v for k, v in definition.items() if k not in {'policy_revision', 'context_revision'}):
        raise ValueError('Runtime definition revision differs')
    from unityagent.orchestration.qa.task_acceptance import assess_task
    return assess_task([plane.evidence_store.get(ref) for ref in result.get('evidence_refs', [])],
        required_gates=gates, run_id=result['run_id'], definition_fingerprint=effective)['gates']


def execute_task_dag(plane, tasks, *, run_id, definition_fingerprint, task_parameters, resume=False):
    """Task自体の権限を増やさず、既存executeで得た永続Evidenceだけで依存を開く。

    初期Schedulerは直列。parallel planを速度向上の実測と混同しない。
    実行途中の再開は副作用が不確定なので自動再送しない。
    """
    definition = deepcopy(dict(definition_fingerprint))
    validate_definition_fingerprint(definition)
    safe_id(run_id, 'run_id')
    tasks = deepcopy(tasks)
    plan = plan_task_batches(tasks)
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
        if identifier not in task_parameters or set(task_parameters[identifier]) & {'run_id', 'definition_fingerprint', 'entry_request'}:
            raise ValueError('Task runtime parameters missing or override identity')
        by_id[identifier] = task
    contract_digest = sha256_json(tasks)
    projects = sorted({str(Path(t['workspace']).resolve()) for t in tasks})
    revisions = {p: project_revision(p) for p in projects}
    if resume:
        state = plane.state_store.load_task_state(run_id)
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
    plane.state_store.save_task_state(state)
    for batch in plan['batches']:
        for identifier in batch['task_ids']:
            task, record = by_id[identifier], state['tasks'][identifier]
            if record['status'] == 'verified':
                continue
            if any(state['tasks'][dep]['status'] != 'verified' for dep in task.get('depends_on', [])):
                record['status'] = 'blocked_dependency'
                plane.state_store.save_task_state(state)
                continue
            # blocked/failed Taskを再開だけで再送しない。修正は別承認Taskとして再計画する。
            if record['status'] != 'pending':
                continue
            if {p: project_revision(p) for p in projects} != state['project_revisions']:
                raise ValueError('Project revision changed before Task dispatch')
            record['status'] = 'running'
            plane.state_store.save_task_state(state)
            start = time.monotonic()
            result = plane.execute(task['entry_request'], run_id=f'{run_id}-{identifier}',
                                   definition_fingerprint=definition, **task_parameters[identifier])
            record['latency_ms'] = (time.monotonic() - start) * 1000
            record['result'] = result
            record['gates'] = _acceptance(plane, result, task['required_gates'], definition)
            record['status'] = 'verified' if result['status'] == 'completed' and all(
                g == 'passed' for g in record['gates'].values()) else 'blocked'
            proof = result.get('orchestration_decision_ref')
            record['handoff_history'].append({'run_id': result['run_id'], 'decision_ref': proof,
                                               'requested_subagent': task['entry_request'].get('requested_subagent')})
            state['execution_order'].append(identifier)
            state['evidence_refs'].extend(result.get('evidence_refs', []))
            state['project_revisions'] = {p: project_revision(p) for p in projects}
            plane.state_store.save_task_state(state)
    state['status'] = 'verified' if all(t['status'] == 'verified' for t in state['tasks'].values()) else 'blocked'
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
