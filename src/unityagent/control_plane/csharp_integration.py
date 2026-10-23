"""検証済み子patchの正確な和集合を承認し、元Projectへ直列反映する。"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from unityagent.control_plane.plan_execution import restore_plan, update_plan
from unityagent.control_plane.task_execution import _acceptance, project_revision
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.persistence.state.plan import read_active_plan, read_plan
from unityagent.persistence.store.atomic_store import read_json, relative_ref, safe_id, sha256_json, write_immutable_json
from unityagent.runtime.guardrails.csharp_patch import patch_revisions, source_target
from unityagent.runtime.sandbox.workspace_guard import snapshot_workspace_hashes


def _path(plane, identifier):
    return plane.state_store.layout.root / 'csharp-integrations/plans' / (safe_id(identifier) + '.json')


def _initial(plane, state):
    plan = read_active_plan(plane.state_store, state)
    while plan['previous_digest']:
        path = plane.state_store.layout.snapshot(state['run_id'], 'plan', plan['previous_digest'])
        plan = read_plan(plane.state_store.layout, relative_ref(plane.state_store.layout.root, path), state['run_id'])
    return plan


def _task_id(item):
    return safe_id('integrate-' + item['task_id'], 'integration_task_id')


def load_integration_plan(plane, identifier):
    plan = read_json(_path(plane, identifier))
    if plan['plan_id'] != identifier or sha256_json({k: v for k, v in plan.items() if k != 'plan_id'}).split(':')[1] != identifier:
        raise ValueError('Integration Plan digest differs')
    state = plane.state_store.load_task_state(plan['parent_run_id'])
    if sha256_json(state.get('parallel_execution')) != plan['parallel_mode_digest']:
        raise ValueError('Integration physical binding metadata changed')
    from unityagent.control_plane.workspace_tasks import verify_project_bindings
    verify_project_bindings(state)
    active = read_active_plan(plane.state_store, state)
    origin = read_plan(plane.state_store.layout, plan['source_plan_ref'], plan['parent_run_id'])
    if (active['root_digest'] != plan['root_digest'] or origin['root_digest'] != plan['root_digest']
            or state['definition_fingerprint'] != plan['definition_fingerprint']):
        raise ValueError('Integration Root or definition differs')
    from unityagent.control_plane.csharp_fix import load_patch_plan
    for item in plan['items']:
        record = state['tasks'][item['task_id']]
        receipt = decision_snapshot(plane.state_store.layout, item['task_receipt_ref'], state['run_id'], 'plan-task')
        child = load_patch_plan(plane, item['child_patch_plan_id'])
        if (receipt['record_digest'] != sha256_json(record) or record['status'] != 'verified'
                or record['result']['status'] != 'completed' or record['result']['run_id'] != item['child_run_id']
                or record['result'].get('patch_plan_id') != child['plan_id']
                or record['result'].get('result_revision') != child['result_revision']
                or receipt['definition_digest'] != origin['task_digests'][item['task_id']]
                or child['expected_revision'] != plan['expected_revision']
                or item['child_plan_digest'] != sha256_json(child) or item['patch'] != child['patch']):
            raise ValueError('Integration child provenance differs')
        task = next(task for task in origin['tasks'] if task['id'] == item['task_id'])
        if (_acceptance(plane, record['result'], task['required_gates'], state['definition_fingerprint'], verify=True)
                != record['gates'] or any(value != 'passed' for value in record['gates'].values())):
            raise ValueError('Integration child Evidence is not accepted')
    return plan


def create_integration_plan(plane, run_id):
    state = plane.state_store.load_task_state(run_id)
    initial = _initial(plane, state)
    restore_plan(plane, state, initial['tasks'], initial['root_contract'])
    active = read_active_plan(plane.state_store, state)
    root, original = active['root_contract'], active['root_contract']['project_root']
    if any(record['status'] == 'running' for record in state['tasks'].values()):
        raise ValueError('Integration requires a stopped worker barrier')
    if state['project_revisions'] != {project: project_revision(project) for project in root['projects']}:
        raise ValueError('Integration input Project revisions are stale')
    candidates = [task for task in active['tasks'] if task['workspace'] != original]
    if len(candidates) != 2:
        raise ValueError('Bounded integration requires exactly two isolated C# fixes')
    before = {name: snapshot_workspace_hashes(Path(original) / name) for name in ('Assets', 'Packages', 'ProjectSettings')}
    predicted, items, paths, tests = deepcopy(before), [], set(), set()
    from unityagent.control_plane.csharp_fix import load_patch_plan
    for task in sorted(candidates, key=lambda task: task['id']):
        record = state['tasks'][task['id']]
        if record['status'] != 'verified' or task['entry_request']['intent']['kind'] != 'csharp_local_fix':
            raise ValueError('Integration requires verified bounded C# workers')
        child = load_patch_plan(plane, record['result']['patch_plan_id'])
        target = child['intent']['target_source']
        scope = root['projects'][original]['write_set']
        if (target in paths or not any(path == '.' or target == path or target.startswith(path + '/') for path in scope)
                or child['project_root'] == original or child['expected_revision'] != sha256_json(before)):
            raise ValueError('Integration has overlapping Scope or a foreign base revision')
        source_target(original, target)
        revisions = patch_revisions(original, target, child['patch']['expected_text'], child['patch']['replacement_text'])
        if revisions['source_sha256'] != child['source_sha256'] or revisions['result_source_sha256'] != child['result_source_sha256']:
            raise ValueError('Integration Source preimage differs from its worker')
        prefix = sha256_json(predicted)
        predicted['Assets'][target.removeprefix('Assets/')] = revisions['result_source_sha256']
        items.append({'task_id': task['id'], 'child_run_id': record['result']['run_id'],
            'task_receipt_ref': state['task_receipt_refs'][task['id']], 'child_patch_plan_id': child['plan_id'],
            'child_plan_digest': sha256_json(child), 'patch': child['patch'], 'intent': child['intent'],
            'target_source': target, 'source_sha256': child['source_sha256'], 'result_source_sha256': child['result_source_sha256'],
            'expected_revision': prefix, 'result_revision': sha256_json(predicted)})
        paths.add(target)
        tests.update(child['intent']['editmode_tests'])
    core = {'schema_version': '1.0', 'parent_run_id': run_id, 'project_root': original,
        'parallel_mode_digest': sha256_json(state['parallel_execution']),
        'root_digest': active['root_digest'], 'source_plan_ref': state['active_plan_ref'],
        'definition_fingerprint': state['definition_fingerprint'], 'expected_revision': sha256_json(before),
        'result_revision': sha256_json(predicted), 'scope_paths': sorted(paths), 'editmode_tests': sorted(tests), 'items': items}
    identifier = sha256_json(core).split(':')[1]
    write_immutable_json(_path(plane, identifier), {**core, 'plan_id': identifier})
    load_integration_plan(plane, identifier)
    return {'integration_plan_id': identifier, 'expected_revision': core['expected_revision'],
            'result_revision': core['result_revision'], 'patch_preview': [
                {'target_source': item['target_source'], 'expected_text': item['patch']['expected_text'],
                 'replacement_text': item['patch']['replacement_text']} for item in items]}


def approve_integration(plane, identifier):
    plan = load_integration_plan(plane, identifier)
    if project_revision(plan['project_root']) != plan['expected_revision']:
        raise ValueError('Integration approval base is stale')
    now = datetime.now(timezone.utc)
    decision = {'schema_version': '1.0', 'approval_decision_id': 'integration-' + uuid.uuid4().hex,
        'operation': 'csharp_serial_integration', 'plan_id': identifier, 'plan_digest': sha256_json(plan),
        'project_root': plan['project_root'], 'expected_revision': plan['expected_revision'],
        'scope_paths': plan['scope_paths'], 'human_review': 'approved', 'status': 'active',
        'approved_at': now.isoformat(), 'expires_at': (now + timedelta(minutes=15)).isoformat(), 'revocation_epoch': 0}
    decision['decision_digest'] = sha256_json(decision)
    ApprovalDecisionStore(plane.state_store.layout.root).register(decision)
    return {'integration_plan_id': identifier, 'approval_ref': decision['approval_decision_id']}


def validate_integration_approval(plane, plan, approval_ref):
    record = ApprovalDecisionStore(plane.state_store.layout.root).get(safe_id(approval_ref, 'approval_ref'))
    decision = record['decision']
    expected = {'operation': 'csharp_serial_integration', 'plan_id': plan['plan_id'], 'plan_digest': sha256_json(plan),
        'project_root': plan['project_root'], 'expected_revision': plan['expected_revision'], 'scope_paths': plan['scope_paths'],
        'human_review': 'approved', 'status': 'active'}
    if (any(decision.get(key) != value for key, value in expected.items())
            or decision.get('decision_digest') != sha256_json({k: v for k, v in decision.items() if k != 'decision_digest'})
            or decision.get('revocation_epoch') != record['current_revocation_epoch']
            or datetime.fromisoformat(decision['expires_at']) <= datetime.now(timezone.utc)):
        raise ValueError('Integration approval is stale, revoked, or bound to another diff')


def validate_imported_plan(plane, plan):
    integration = load_integration_plan(plane, plan['integration_plan_id'])
    item = integration['items'][plan['integration_item']]
    if (plan['patch'] != item['patch'] or plan['project_root'] != integration['project_root']
            or any(plan[key] != item[key] for key in ('expected_revision', 'result_revision', 'source_sha256', 'result_source_sha256'))):
        raise ValueError('Imported patch differs from the verified worker artifact')
    manifest = decision_snapshot(plane.state_store.layout, plan['execution_context_ref'], plan['execution_run_id'], 'context-manifest')
    view = manifest['materialized_context']
    if (view['context_id'] != plan['execution_context_id']
            or view['context_fingerprint']['value'] != plan['execution_context_fingerprint']):
        raise ValueError('Imported patch parent execution Context differs')


def prepare_integration_session(plane, session, handoff, manifest_ref):
    intent = session['intent']
    integration = load_integration_plan(plane, intent['integration_plan_id'])
    validate_integration_approval(plane, integration, session['entry'].get('approval_ref'))
    state = plane.state_store.load_task_state(integration['parent_run_id'])
    current = read_active_plan(plane.state_store, state)
    final = bool(intent.get('verification_only'))
    name = 'integration-final' if final else _task_id(integration['items'][intent['integration_item']])
    expected_task = next(task for task in _integration_tasks(integration, session['entry']['approval_ref'], current['root_contract'])
                         if task['id'] == name)
    actual = next(task for task in current['tasks'] if task['id'] == name)
    if (actual != expected_task or actual['entry_request'] != session['entry']
            or state['tasks'][name]['status'] != 'running'
            or handoff['run_id'] != integration['parent_run_id'] + '-' + name):
        raise ValueError('Integration dispatch differs from the active parent Task')
    if final:
        if any(state['tasks'][_task_id(item)]['status'] != 'verified' for item in integration['items']):
            raise ValueError('Final integration verification requires both accepted patches')
        session.update(integration_final=True, evidence_plan_id=integration['plan_id'],
            file_arguments={'relative_path': intent['target_source'], 'bounded_csharp_union_review': True,
                'expected_revision': integration['result_revision'], 'items': [
                    {'relative_path': item['target_source'], 'expected_text': item['patch']['expected_text'],
                     'replacement_text': item['patch']['replacement_text'], 'source_sha256': item['source_sha256'],
                     'result_source_sha256': item['result_source_sha256']} for item in integration['items']]})
        return session
    index = intent['integration_item']
    item = integration['items'][index]
    if any(state['tasks'][_task_id(prior)]['status'] != 'verified' for prior in integration['items'][:index]):
        raise ValueError('Integration patches must be accepted serially')
    revisions = patch_revisions(session['project'], item['target_source'], item['patch']['expected_text'], item['patch']['replacement_text'])
    if any(revisions[key] != item[key] for key in revisions):
        raise ValueError('Integration Source or expected prefix revision changed')
    from unityagent.control_plane.csharp_fix import _path, load_patch_plan
    child = load_patch_plan(plane, item['child_patch_plan_id'])
    application_id = sha256_json({'integration_plan_id': integration['plan_id'], 'item': index}).split(':')[1]
    if _path(plane, 'applications', application_id).exists():
        raise ValueError('Integration patch was already attempted; reconciliation is required')
    core = {'schema_version': '2.0', 'project_root': str(session['project']), 'intent': intent,
        'patch': child['patch'], **revisions, 'proposal_context_ref': child['proposal_context_ref'],
        'source_evidence_refs': child['source_evidence_refs'], 'observed_source_sha256': child['observed_source_sha256'],
        'definition_fingerprint': handoff['definition_fingerprint'], 'model': child['model'], 'model_usage': None,
        'integration_plan_id': integration['plan_id'], 'integration_item': index, 'application_id': application_id,
        'execution_run_id': handoff['run_id'], 'execution_context_ref': manifest_ref,
        'execution_context_id': handoff['context_id'], 'execution_context_fingerprint': handoff['context_fingerprint']}
    identifier = sha256_json(core).split(':')[1]
    plan = {**core, 'plan_id': identifier}
    write_immutable_json(_path(plane, 'plans', identifier), plan)
    validate_imported_plan(plane, plan)
    session.update(plan=plan, context=replace(session['context'], approval_required=True, approval_complete=True),
        file_arguments={'bounded_csharp_patch': True, 'relative_path': item['target_source'],
            'expected_text': item['patch']['expected_text'], 'replacement_text': item['patch']['replacement_text'], **revisions})
    return session


def _integration_tasks(plan, approval_ref, root):
    tasks = []
    previous = [item['task_id'] for item in plan['items']]
    for index, item in enumerate(plan['items']):
        intent = {**item['intent'], 'expected_revision': item['expected_revision'],
                  'integration_plan_id': plan['plan_id'], 'integration_item': index}
        name = _task_id(item)
        tasks.append({'id': name, 'workspace': plan['project_root'], 'goal': item['intent']['goal_or_confirmed_error'],
            'read_set': ['.'], 'write_set': [item['target_source']], 'resource_claims': [], 'parallel_safe': False,
            'depends_on': previous, 'required_gates': deepcopy(root['required_gates']),
            'entry_request': {'schema_version': '2.0', 'request_id': name, 'entry_point': 'codex_plugin',
                'project_root': plan['project_root'], 'approval_ref': approval_ref, 'intent': intent}})
        previous = [name]
    intent = {**plan['items'][0]['intent'], 'expected_revision': plan['result_revision'],
        'verification_only': True, 'integration_plan_id': plan['plan_id'], 'editmode_tests': plan['editmode_tests']}
    tasks.append({'id': 'integration-final', 'workspace': plan['project_root'], 'goal': 'Verify the final integrated revision',
        'read_set': ['.'], 'write_set': [], 'resource_claims': [], 'parallel_safe': False, 'depends_on': previous,
        'required_gates': deepcopy(root['required_gates']), 'entry_request': {'schema_version': '2.0',
            'request_id': 'integration-final', 'entry_point': 'codex_plugin', 'project_root': plan['project_root'],
            'approval_ref': approval_ref, 'intent': intent}})
    return tasks


def integrate_workspace_results(plane, run_id, identifier, approval_ref, original_parameters, *, timeout_seconds=300.0, cancel_event=None):
    plan = load_integration_plan(plane, identifier)
    if plan['parent_run_id'] != run_id:
        raise ValueError('Integration belongs to another parent Run')
    validate_integration_approval(plane, plan, approval_ref)
    state = plane.state_store.load_task_state(run_id)
    initial = _initial(plane, state)
    tasks = restore_plan(plane, state, initial['tasks'], initial['root_contract'])
    additions = _integration_tasks(plan, approval_ref, initial['root_contract'])
    parameters = {task['id']: {} for task in tasks}
    parameters.update({task['id']: original_parameters for task in additions})
    names = {task['id']: task for task in tasks}
    if not any(task['id'] in names for task in additions):
        if project_revision(plan['project_root']) != plan['expected_revision']:
            raise ValueError('Integration expected base revision changed')
        active = read_active_plan(plane.state_store, state)
        proposal = {'base_digest': sha256_json(active), 'tasks': tasks + additions,
            'reason': 'Integrate explicitly approved worker patches and revalidate the original',
            'evidence_refs': list(state['evidence_refs'])}
        update_plan(plane, state, tasks, names, parameters, state['execution_order'][-1],
                    lambda context: proposal, record_boundary=False)
        if any(task['id'] not in names for task in additions):
            raise ValueError('Integration Plan revision was rejected')
    elif any(names.get(task['id']) != task for task in additions):
        raise ValueError('Integration Task definitions or approval changed')
    from unityagent.control_plane.workspace_tasks import execute_workspace_dag
    return execute_workspace_dag(plane, initial['tasks'], run_id=run_id,
        definition_fingerprint=state['definition_fingerprint'], task_parameters=parameters,
        root_contract=initial['root_contract'], parallel_enabled=state['parallel_execution']['enabled'], resume=True,
        timeout_seconds=timeout_seconds, cancel_event=cancel_event)
