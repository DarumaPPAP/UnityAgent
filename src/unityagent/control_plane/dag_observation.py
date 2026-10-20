"""既存の確定結果だけを親DAG観測へ渡す。補助保存の失敗で実行を再送しない。"""
from copy import deepcopy
from pathlib import Path

from jsonschema import ValidationError

from unityagent.orchestration.routing.adaptive_execution import build_dag_inputs, facts_from_boundary
from unityagent.persistence.state.dag_decision import decision_snapshot, read_dag_decision
from unityagent.persistence.store.atomic_store import PersistenceError, relative_ref, sha256_json, write_immutable_json


def observe_dag_boundary(plane, tasks, state, *, task_id, attempt, dispatch_revisions):
    layout = plane.state_store.layout
    sources = []
    observed = {}
    phase = 'dag_decision_invalid_reference'
    try:
        contract = decision_snapshot(layout, state['contract_ref'], state['run_id'], 'task-contract')
        if contract != {'tasks':tasks, 'definition_fingerprint':state['definition_fingerprint']}:
            raise ValueError('DAG contract differs')
        failures = []
        uncertain = False
        for task in tasks:
            name = task['id']
            item = state['tasks'][name]
            result = item.get('result')
            if not result:
                continue
            history = item['handoff_history']
            child_attempt = len(history) - 1
            child = f"{state['run_id']}-{name}" + (f'-repair{child_attempt}' if child_attempt else '')
            if result['run_id'] != child or history[-1]['run_id'] != child:
                raise ValueError('DAG result Attempt differs')
            definition = result.get('handoff', {}).get('definition_fingerprint')
            if definition and any(definition.get(k) != v for k,v in state['definition_fingerprint'].items() if k not in {'policy_revision','context_revision'}):
                raise ValueError('DAG result definition differs')
            proof = manifest = None
            for kind, field in (('orchestration-decision','orchestration_decision_ref'),('context-manifest','context_manifest_ref')):
                if not result.get(field):
                    continue
                value = decision_snapshot(layout, result[field], child, kind)
                sources.append({'kind':kind, 'ref':result[field], 'digest':sha256_json(value),
                    'run_id':child, 'task_id':name, 'attempt':child_attempt})
                if kind == 'orchestration-decision':
                    proof = value
                else:
                    manifest = value
                    if manifest['run_id'] != child or any(manifest['materialized_context']['definition_fingerprint'][k] != definition[k] for k in ('policy_revision','context_revision')):
                        raise ValueError('DAG Context definition differs')
            if proof and manifest and proof['context_manifest_ref'] != result['context_manifest_ref']:
                raise ValueError('DAG proof Context differs')
            previous_definition = None
            if proof and proof.get('previous_context_manifest_ref'):
                previous = decision_snapshot(layout, proof['previous_context_manifest_ref'], child, 'context-manifest')
                sources.append({'kind':'context-manifest','ref':proof['previous_context_manifest_ref'], 'digest':sha256_json(previous),
                    'run_id':child, 'task_id':name,'attempt':child_attempt})
                if previous['run_id'] != child:
                    raise ValueError('DAG previous Context Run differs')
                previous_definition = {**definition, **{k:previous['materialized_context']['definition_fingerprint'][k] for k in ('policy_revision','context_revision')}}
            for evidence_ref in result.get('evidence_refs', []):
                evidence = plane.evidence_store.verify_record(evidence_ref, expected_run_id=child)
                matches = proof and any(evidence.get('capability') == request['capability'] and evidence['step_id'] == f"{result['handoff']['step_id']}-{index+1}" for index,request in enumerate(proof.get('capability_requests', [])))
                expected_definition = previous_definition if previous_definition and (evidence_ref in proof.get('observation_evidence_refs',[]) or matches) else definition
                if evidence['definition_fingerprint'] != expected_definition or (evidence.get('project_root') and Path(evidence['project_root']).resolve() != Path(task['workspace']).resolve()):
                    raise ValueError('DAG Evidence definition or Project differs')
                sources.append({'kind':'evidence', 'ref':relative_ref(layout.root, plane.evidence_store.layout.evidence(evidence_ref)),
                    'digest':sha256_json(evidence), 'evidence_id':evidence_ref, 'run_id':child, 'task_id':name, 'attempt':child_attempt})
            # 停止分類はP0〜P1のallowlist済み観測から再利用する。理由全文は持ち込まない。
            for ref in result.get('strategy_observation_refs', []):
                observation = decision_snapshot(layout, ref, child, 'strategy-observation')
                if observation['run_id'] != child or observation['result_run_id'] != child or observation['definition_fingerprint'] != definition:
                    raise ValueError('DAG observation binding differs')
                sources.append({'kind':'strategy-observation','ref':ref,'digest':sha256_json(observation),
                    'run_id':child,'task_id':name,'attempt':child_attempt})
                uncertain = uncertain or observation['uncertain_side_effects']
                if item['status'] != 'verified' and observation['failure_class']:
                    failures.append(observation['failure_class'])
            if name != task_id or not proof or not manifest:
                continue
            observed[name] = facts_from_boundary(task, proof, manifest, item['semantic_decision'],
                attempt=attempt, same_revision=dispatch_revisions == state['project_revisions'],
                proof_ref=result['orchestration_decision_ref'], manifest_ref=result['context_manifest_ref'])
        # 未実行Taskや別の修復候補には、今回実行したTaskの情報を転用しない。
        inputs = build_dag_inputs(tasks, state, failure_classes=failures, uncertain_side_effects=uncertain)
        decision = inputs.pop('decision')
        boundary = {'kind':'task_attempt_acceptance','task_id':task_id,'attempt':attempt,
                    'result_run_id':state['tasks'][task_id]['result']['run_id'],
                    'semantic_decision':{key:state['tasks'][task_id]['semantic_decision'][key] for key in ('decision','semantic_attempt','outcome')}}
        revisions = {sha256_json(project):revision for project,revision in state['project_revisions'].items()}
        snapshot = {'run_id':state['run_id'],'boundary':boundary,'contract_digest':state['contract_digest'],
            'definition_fingerprint':deepcopy(state['definition_fingerprint']), 'project_revisions':revisions,
            'inputs':inputs,'observed_facts':observed,'sources':sources,
            'dispatch_project_revisions':{sha256_json(project):revision for project,revision in dispatch_revisions.items()}}
        phase = 'dag_decision_persistence_failed'
        path = layout.snapshot(state['run_id'],'dag-boundary',sha256_json(snapshot))
        write_immutable_json(path,snapshot)
        record = {'schema_version':'1.0','target':{'kind':'parent_dag','run_id':state['run_id']},'boundary':boundary,
            'definition_fingerprint':snapshot['definition_fingerprint'],'project_revisions':revisions,
            'contract_ref':state['contract_ref'],'state_ref':relative_ref(layout.root,path),
            'inputs':inputs,'input_digest':sha256_json(inputs),'observed_facts':observed,'sources':sources,'decision':decision}
        path = layout.snapshot(state['run_id'],'dag-decision',sha256_json(record))
        write_immutable_json(path,record)
        ref = relative_ref(layout.root,path)
        read_dag_decision(layout.root,ref,run_id=state['run_id'])
        state.setdefault('dag_decision_refs',[]).append(ref)
    except (OSError, PersistenceError, ValueError, KeyError, TypeError, ValidationError) as exc:
        state.setdefault('dag_decision_diagnostics',[]).append(
            {'code':phase,'task_id':task_id,'attempt':attempt,'error_type':type(exc).__name__})
