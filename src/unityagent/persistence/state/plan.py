"""Plan snapshotとactive参照を分け、切替の中断をjournalで検出する。"""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator, ValidationError
import yaml

from unityagent.resources import resource_root

from unityagent.persistence.store.atomic_store import (
    append_jsonl, read_json, relative_ref, resolve_ref, sha256_json, write_immutable_json,
)


def stage_plan(layout, plan):
    path = layout.snapshot(plan['run_id'], 'plan', sha256_json(plan))
    write_immutable_json(path, plan)
    return relative_ref(layout.root, path)


def read_plan(layout, ref, run_id):
    path = resolve_ref(layout.root, ref)
    plan = read_json(path)
    schema = yaml.safe_load((resource_root() / 'src/unityagent/orchestration/contracts/plan.schema.yaml').read_text(encoding='utf-8'))
    try:
        Draft202012Validator(schema).validate(plan)
    except ValidationError as exc:
        raise ValueError('Invalid Plan snapshot schema') from exc
    expected = layout.snapshot(run_id, 'plan', sha256_json(plan))
    if path != expected.resolve() or ref != relative_ref(layout.root, expected) or plan.get('run_id') != run_id:
        raise ValueError('Plan snapshot digest or identity differs')
    if (plan['root_digest'] != sha256_json(plan['root_contract'])
            or plan['task_digests'] != {task['id']: sha256_json(task) for task in plan['tasks']}
            or not set(plan['task_digests']) <= set(plan['generated_task_ids'])
            or set(plan['cancelled_task_ids']) & set(plan['task_digests'])):
        raise ValueError('Plan definition digests or Task identity sets differ')
    return plan


def _events(layout, run_id, kind='plan'):
    path = layout.run_root(run_id) / f'current/{kind}-events.jsonl'
    if not path.exists():
        return []
    try:
        values = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        previous = None
        for sequence, event in enumerate(values):
            material = {key: value for key, value in event.items() if key != 'hash'}
            if (event['hash'] != sha256_json(material) or event['previous_hash'] != previous
                    or event['sequence'] != sequence or event['run_id'] != run_id):
                raise ValueError('Plan journal chain differs')
            previous = event['hash']
        return values
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Plan journal is corrupt') from exc


def read_active_plan(store, state):
    layout, run_id = store.layout, state['run_id']
    events = _events(layout, run_id)
    if (not events or state.get('plan_event_refs') != [event['hash'] for event in events]
            or state.get('active_plan_ref') != events[-1]['plan_ref']):
        raise ValueError('Plan journal and active history differ; reconciliation required')
    previous = None
    last = None
    for event in events:
        if event['expected_ref'] != previous:
            raise ValueError('Plan active history base differs')
        plan = read_plan(layout, event['plan_ref'], run_id)
        if (plan['revision'] != event['sequence'] or plan['previous_digest'] != (sha256_json(last) if last else None)
                or plan['root_digest'] != sha256_json(plan['root_contract'])
                or (last and any(plan[key] != last[key] for key in ('root_contract', 'root_digest', 'definition_fingerprint', 'limits', 'rules_version')))):
            raise ValueError('Plan revision history or immutable Root differs')
        previous, last = event['plan_ref'], plan
    return last


def commit_plan(store, state, plan_ref, *, expected_ref):
    """呼出し側は親Run lockを保持する。journalだけ残った失敗は自動適用しない。"""
    layout, run_id = store.layout, state['run_id']
    current_path = layout.run_root(run_id) / 'current/task-state.json'
    durable = store.load_task_state(run_id) if current_path.exists() else {}
    if durable.get('active_plan_ref') != expected_ref or state.get('active_plan_ref') != expected_ref:
        raise ValueError('Plan activation base differs')
    events = _events(layout, run_id)
    if state.get('plan_event_refs', []) != [event['hash'] for event in events]:
        raise ValueError('Plan journal history differs')
    proposed = read_plan(layout, plan_ref, run_id)
    if expected_ref:
        prior = read_active_plan(store, durable)
        if proposed['previous_digest'] != sha256_json(prior) or proposed['revision'] != prior['revision'] + 1:
            raise ValueError('Plan activation base digest differs')
    elif proposed['revision'] != 0 or proposed['previous_digest'] is not None:
        raise ValueError('Initial Plan revision differs')
    event = {'run_id': run_id, 'sequence': len(events), 'previous_hash': events[-1]['hash'] if events else None,
             'expected_ref': expected_ref, 'plan_ref': plan_ref}
    event['hash'] = sha256_json(event)
    append_jsonl(layout.run_root(run_id) / 'current/plan-events.jsonl', event)
    updated = {**deepcopy(state), 'active_plan_ref': plan_ref,
               'plan_event_refs': [entry['hash'] for entry in events] + [event['hash']]}
    store.save_task_state(updated)
    state.clear()
    state.update(updated)


def read_plan_audit(store, state):
    events = _events(store.layout, state['run_id'], 'plan-audit')
    if state.get('plan_audit_refs') != [event['hash'] for event in events]:
        raise ValueError('Plan audit journal history differs; reconciliation required')
    return events


def append_plan_audit(store, state, *, kind, ref):
    events = read_plan_audit(store, state)
    event = {'run_id': state['run_id'], 'sequence': len(events), 'kind': kind, 'ref': ref,
             'previous_hash': events[-1]['hash'] if events else None}
    event['hash'] = sha256_json(event)
    append_jsonl(store.layout.run_root(state['run_id']) / 'current/plan-audit-events.jsonl', event)
    state['plan_audit_refs'].append(event['hash'])
