"""Root契約を保持する動的Planの純粋検証。実行権限は付与しない。"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import PurePosixPath

from unityagent.orchestration.graph.resource_planning import plan_task_batches

LIMITS = {'updates': 2, 'tasks': 32, 'proposals': 4}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def _paths(values):
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values) or len(set(values)) != len(values):
        raise ValueError('Scope must contain unique paths')
    for value in values:
        if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
                or PurePosixPath(value).is_absolute() or ':' in value or '..' in value.split('/')
                or any(character in value for character in '*?[') or str(PurePosixPath(value)) != value):
            raise ValueError('Scope path must be confined and canonical')
    return values


def _contained(path, scopes):
    return any(scope == '.' or path == scope or path.startswith(scope + '/') for scope in scopes)


def _validate_tasks(tasks, root):
    plan_task_batches(tasks)
    kinds = root.get('allowed_entry_kinds')
    for task in tasks:
        if not isinstance(task['id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', task['id']):
            raise ValueError('Task identity must be canonical')
        if 'read_set' not in task or '.' not in task['read_set']:
            raise ValueError('Current Entry Context requires explicit whole Project read Scope')
        project = task['workspace']
        if project not in root['projects'] or task.get('entry_request', {}).get('project_root') != project:
            raise ValueError('Task Project is outside Root Scope')
        if kinds is not None and task['entry_request'].get('intent', {}).get('kind') not in kinds:
            raise ValueError('Unknown Entry kind for Root contract')
        if not isinstance(task.get('goal'), str) or not task['goal'].strip():
            raise ValueError('Task goal is required')
        for field in ('read_set', 'write_set'):
            paths = _paths(task.get(field, []))
            if any(not _contained(path, root['projects'][project][field]) for path in paths):
                raise ValueError('Task is outside Root Scope')
        gates = task.get('required_gates')
        if not isinstance(gates, dict) or not gates or any(not isinstance(values, list) or not values for values in gates.values()):
            raise ValueError('Task requires fixed gates')
        if any(not set(values) <= set(gates.get(gate, [])) for gate, values in root['required_gates'].items()):
            raise ValueError('Task weakens Root Gate')



def _validate_identities(names):
    for left in names:
        for right in names:
            if left != right and re.fullmatch(re.escape(left) + r'-repair[0-9]+', right):
                raise ValueError('Task and repair Attempt identity collision')

def create_plan(*, run_id, root_contract, definition_fingerprint, tasks, project_revisions):
    root = deepcopy(root_contract)
    if (not isinstance(root, dict) or set(root) - {'goal', 'project_root', 'projects', 'required_gates', 'approval_conditions', 'allowed_entry_kinds'}
            or not isinstance(root.get('goal'), str) or not root['goal'].strip()
            or not isinstance(root.get('projects'), dict) or not root['projects']
            or not isinstance(root.get('required_gates'), dict) or not root['required_gates']
            or root.get('approval_conditions') != ['existing_policy']):
        raise ValueError('Explicit immutable Root contract is required')
    if root.get('project_root') not in root['projects']:
        raise ValueError('Final Gate requires a fixed Root Project identity')
    for scope in root['projects'].values():
        if set(scope) != {'read_set', 'write_set'}:
            raise ValueError('Root Scope requires read/write sets')
        for paths in scope.values():
            _paths(paths)
    if set(project_revisions) != set(root['projects']):
        raise ValueError('Root Project revision set differs')
    _validate_tasks(tasks, root)
    _validate_identities([task['id'] for task in tasks])
    if len(tasks) > LIMITS['tasks']:
        raise ValueError('Task budget exceeded')
    return {'schema_version': '1.0', 'run_id': run_id, 'revision': 0, 'previous_digest': None,
            'root_contract': root, 'root_digest': digest(root), 'definition_fingerprint': deepcopy(definition_fingerprint),
            'tasks': deepcopy(tasks), 'task_digests': {t['id']: digest(t) for t in tasks},
            'project_revisions': deepcopy(project_revisions), 'cancelled_task_ids': [],
            'generated_task_ids': sorted(t['id'] for t in tasks), 'reason': 'initial', 'evidence_refs': [],
            'limits': dict(LIMITS), 'rules_version': '1.0'}


def revise_plan(current, proposal, *, task_states, evidence_refs, proposals_consumed, project_revisions=None):
    if not isinstance(proposal, dict) or set(proposal) != {'base_digest', 'tasks', 'reason', 'evidence_refs'}:
        raise ValueError('Invalid Plan proposal contract')
    if proposal['base_digest'] != digest(current):
        raise ValueError('Stale Plan base digest')
    if any(t['status'] == 'running' for t in task_states.values()):
        raise ValueError('Plan cannot change while a Task is running')
    if not isinstance(proposal['reason'], str) or not proposal['reason'].strip():
        raise ValueError('Plan update needs a reason')
    refs = proposal['evidence_refs']
    if not isinstance(refs, list) or not refs or len(set(refs)) != len(refs) or not set(refs) <= set(evidence_refs):
        raise ValueError('Plan update needs verified Evidence')
    if type(proposals_consumed) is not int or not 1 <= proposals_consumed <= current['limits']['proposals']:
        raise ValueError('Plan proposal budget exceeded')
    if current['revision'] >= current['limits']['updates']:
        raise ValueError('Plan update budget exceeded')
    tasks = proposal['tasks']
    _validate_tasks(tasks, current['root_contract'])
    old = {t['id']: t for t in current['tasks']}
    new = {t['id']: t for t in tasks}
    if set(old) != set(task_states):
        raise ValueError('Plan Task state set differs')
    if set(new) & set(current['cancelled_task_ids']):
        raise ValueError('A cancelled Task identity cannot be reused')
    for name, task in old.items():
        if task_states[name]['status'] != 'pending' and new.get(name) != task:
            raise ValueError('Executed or stopped Task definition cannot change')
    generated = sorted(set(current['generated_task_ids']) | set(new))
    _validate_identities(generated)
    if len(generated) > current['limits']['tasks']:
        raise ValueError('Task budget exceeded')
    cancelled = sorted(set(current['cancelled_task_ids']) | (set(old) - set(new)))
    revisions = current['project_revisions'] if project_revisions is None else project_revisions
    if set(revisions) != set(current['root_contract']['projects']):
        raise ValueError('Plan Project revision set differs')
    return {**deepcopy(current), 'project_revisions': deepcopy(revisions), 'revision': current['revision'] + 1, 'previous_digest': digest(current),
            'tasks': deepcopy(tasks), 'task_digests': {t['id']: digest(t) for t in tasks},
            'generated_task_ids': generated, 'cancelled_task_ids': cancelled,
            'reason': proposal['reason'], 'evidence_refs': list(refs)}
