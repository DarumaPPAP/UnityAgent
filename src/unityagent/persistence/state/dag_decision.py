"""親DAGの補助判定記録をimmutableな根拠へ照合する。実行や意味判断は行わない。"""
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError

from unityagent.resources import resource_root
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from unityagent.persistence.store.atomic_store import PersistenceError, read_json, relative_ref, resolve_ref, sha256_json
from unityagent.persistence.store.layout import PersistenceLayout


def decision_snapshot(layout, ref, owner, kind):
    """呼出し側が指定したRun・種別・内容digestに一致するsnapshotだけを読む。"""
    path = resolve_ref(layout.root, ref)
    value = read_json(path)
    digest = sha256_json(value)
    if kind == 'task-contract':
        digest = sha256_json(value['tasks'])
    expected = layout.snapshot(owner, kind, digest)
    if ref != relative_ref(layout.root, expected) or path != expected.resolve():
        raise ValueError('DAG snapshot digest or Run differs')
    return value


def read_dag_decision(persistence_root, ref, *, run_id):
    """currentの再読込やProvider再送をせず、保存時点の対応関係を検証する。"""
    layout = PersistenceLayout(persistence_root)
    record = decision_snapshot(layout, ref, run_id, 'dag-decision')
    schema = yaml.safe_load((resource_root() / 'src/unityagent/orchestration/contracts/dag-decision.schema.yaml').read_text(encoding='utf-8'))
    try:
        Draft202012Validator(schema).validate(record)
    except ValidationError as exc:
        raise ValueError('invalid DAG decision schema') from exc
    if record['target'] != {'kind':'parent_dag', 'run_id':run_id}:
        raise ValueError('DAG target differs')
    state = decision_snapshot(layout, record['state_ref'], run_id, 'dag-boundary')
    contract = decision_snapshot(layout, record['contract_ref'], run_id, 'task-contract')
    if state['run_id'] != run_id or state['boundary'] != record['boundary'] or state['inputs'] != record['inputs']:
        raise ValueError('DAG boundary differs')
    if record['input_digest'] != sha256_json(record['inputs']) or state['contract_digest'] != sha256_json(contract['tasks']):
        raise ValueError('DAG inputs or contract digest differs')
    if state['definition_fingerprint'] != record['definition_fingerprint'] or contract['definition_fingerprint'] != record['definition_fingerprint']:
        raise ValueError('DAG definition differs')
    if state['project_revisions'] != record['project_revisions'] or state['observed_facts'] != record['observed_facts'] or state['sources'] != record['sources']:
        raise ValueError('DAG sources or Project revision differs')
    tasks = {task['id']:task for task in contract['tasks']}
    if set(tasks) != set(record['inputs']['tasks']):
        raise ValueError('DAG Task contract differs')
    boundary = record['boundary']
    expected_child = f"{run_id}-{boundary['task_id']}" + (f"-repair{boundary['attempt']}" if boundary['attempt'] else '')
    if boundary['task_id'] not in tasks or boundary['result_run_id'] != expected_child:
        raise ValueError('DAG Attempt differs')
    if record['inputs']['tasks'][boundary['task_id']]['attempts_completed'] != boundary['attempt'] + 1:
        raise ValueError('DAG Attempt state differs')
    evidence_store = EvidenceStore(layout.root)
    verified_sources = {}
    for source in record['sources']:
        child = f"{run_id}-{source['task_id']}" + (f"-repair{source['attempt']}" if source['attempt'] else '')
        if source['task_id'] not in tasks or source['run_id'] != child:
            raise ValueError('DAG source Task or Attempt differs')
        if source['kind'] == 'evidence':
            value = evidence_store.verify_record(source['evidence_id'], expected_run_id=child)
            if relative_ref(layout.root, layout.evidence(source['evidence_id'])) != source['ref']:
                raise ValueError('DAG Evidence ref differs')
        else:
            value = decision_snapshot(layout, source['ref'], child, source['kind'])
        if sha256_json(value) != source['digest']:
            raise ValueError('DAG source digest differs')
        verified_sources[source['ref']] = value
    # Context再構築前のTool Evidenceだけは、その時点の定義へ結び付ける。
    for source in record['sources']:
        if source['kind'] != 'orchestration-decision':
            continue
        proof = verified_sources[source['ref']]
        manifest = verified_sources[proof['context_manifest_ref']]
        if manifest['run_id'] != source['run_id']:
            raise ValueError('DAG manifest Run differs')
        definition = {**record['definition_fingerprint'], **{k:manifest['materialized_context']['definition_fingerprint'][k] for k in ('policy_revision','context_revision')}}
        previous_definition = None
        if proof.get('previous_context_manifest_ref'):
            previous = verified_sources[proof['previous_context_manifest_ref']]
            if previous['run_id'] != source['run_id']:
                raise ValueError('DAG previous manifest Run differs')
            previous_definition = {**definition, **{k:previous['materialized_context']['definition_fingerprint'][k] for k in ('policy_revision','context_revision')}}
        for related in record['sources']:
            if related['run_id'] != source['run_id']:
                continue
            value = verified_sources[related['ref']]
            if related['kind'] == 'evidence':
                matches = any(value.get('capability') == request['capability'] and value['step_id'] == f"{proof['node_id']}-{index+1}" for index,request in enumerate(proof.get('capability_requests',[])))
                uses_previous = previous_definition and (related['evidence_id'] in proof.get('observation_evidence_refs',[]) or matches)
                if value['definition_fingerprint'] != (previous_definition if uses_previous else definition):
                    raise ValueError('DAG Evidence definition differs')
            if related['kind'] == 'strategy-observation' and (value['run_id'] != related['run_id'] or value['definition_fingerprint'] != definition):
                raise ValueError('DAG child observation definition differs')
    same_revision = state['dispatch_project_revisions'] == record['project_revisions']
    for facts in record['observed_facts'].values():
        if (facts['freshness'] == 'same_project_revision') != same_revision or (not same_revision and facts['values']):
            raise ValueError('DAG fact Project revision differs')
        if any(ref not in verified_sources and ref != 'boundary.semantic_decision' for ref in facts['provenance'].values()):
            raise ValueError('DAG fact provenance differs')
    return record
