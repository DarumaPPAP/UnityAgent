"""承認済みSource/RunnerをOptional Hot Reloadへ渡し、通常Compile/QAを別Gateに残す。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import uuid

from unityagent.control_plane.task_execution import project_revision
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import read_json, safe_id, sha256_json, write_immutable_json, relative_ref
from unityagent.persistence.evidence.runtime_adapter import append_runtime_execution_evidence
from unityagent.runtime.evidence_capture.tool_runtime_evidence import normalize_provider_result
from unityagent.runtime.sandbox.workspace_guard import confined_path
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.providers.unity_cli_loop.hot_reload_provider import HotReloadProvider


def plan_hot_reload(project_root, state_root, files, runner_path, runner_sha256, definition):
    project, state = Path(project_root).resolve(strict=True), Path(state_root).resolve()
    if project == state or project in state.parents:
        raise ValueError('Hot Reload Persistence must be outside Project')
    runner = Path(runner_path).resolve(strict=True)
    if hashlib.sha256(runner.read_bytes()).hexdigest() != runner_sha256:
        raise ValueError('Reviewed runner hash differs')
    sources = {}
    for name in files:
        if not name.startswith('Assets/') or not name.endswith('.cs') or any(c in name for c in ',\r\n'):
            raise ValueError('Exact Source paths are required')
        sources[name] = hashlib.sha256(confined_path(project,name,require_file=True).read_bytes()).hexdigest()
    if not sources:
        raise ValueError('Hot Reload Source scope is empty')
    plan = {'schema_version':'1.0','project_root':str(project),'source_hashes':sources,
            'runner_path':str(runner),'runner_sha256':runner_sha256,
            'project_revision':project_revision(project), 'definition_fingerprint':dict(definition),
            'required_gates':['hot_reload','play_behavior','normal_compile','qa_acceptance'],
            'rollback':'Removing runtime patches does not restore Source or runtime side effects'}
    plan['plan_id'] = sha256_json(plan).split(':')[1]
    write_immutable_json(state/'hot-reload-plans'/(plan['plan_id']+'.json'),plan)
    return plan


def approve_hot_reload(state_root, plan_id):
    state = Path(state_root).resolve()
    plan = read_json(state/'hot-reload-plans'/(safe_id(plan_id)+'.json'))
    approval = {'approval_decision_id':'hot-reload-'+uuid.uuid4().hex,'operation':'editor.hot_reload',
                'plan_digest':sha256_json(plan),'revocation_epoch':0,
                'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}
    ApprovalDecisionStore(state).register(approval)
    return approval


def apply_hot_reload(plane, plan_id, approval_ref, *, definition_fingerprint):
    state = plane.state_store.layout.root
    plan = read_json(state/'hot-reload-plans'/(safe_id(plan_id)+'.json'))
    if plan['definition_fingerprint'] != dict(definition_fingerprint) or plan['project_revision'] != project_revision(plan['project_root']):
        raise ValueError('Hot Reload definition or Project revision changed')
    def check_approval(_):
        record = ApprovalDecisionStore(state).get(approval_ref)
        decision = record['decision']
        if (decision.get('operation') != 'editor.hot_reload' or decision.get('plan_digest') != sha256_json(plan)
                or record['current_revocation_epoch'] != decision['revocation_epoch']
                or datetime.fromisoformat(decision['expires_at']) <= datetime.now(timezone.utc)):
            raise ValueError('Hot Reload approval invalid, stale or revoked')
    check_approval(None)
    project = Path(plan['project_root'])
    provider = HotReloadProvider(project, plan['runner_path'], binary_sha256=plan['runner_sha256'], check_approval=check_approval)
    snapshot = discover_environment(project).to_dict()
    bound = snapshot['unity_editor']['project_bound'] is True
    snapshot['unity_cli_loop'] = {'available':True,'project_bound':bound,'reachable':bound,
        'binding_status':'bound' if bound else 'unknown','bound_instance_id':snapshot['unity_editor']['bound_instance_id']}
    request = {'schema_version':'1.0','capability':'editor.hot_reload','operation_kind':'editor_mutation',
        'project_root':str(project),'required_evidence':['editor_observation','mutation_evidence'],
        'mutation_scope':{'allowed_paths':sorted(plan['source_hashes']),'prohibited_paths':['ProjectSettings']},
        'approval_ref':approval_ref,'preferred_surface':'live_editor'}
    run_id = 'hot-reload-'+uuid.uuid4().hex
    result = plane.broker.dispatch(request,snapshot,
        context=ResolutionContext(policy_allowed=True,approval_required=True,approval_complete=True),
        executors={'unity_cli_loop':provider.execute},
        provider_arguments={'unity_cli_loop':{'source_hashes':plan['source_hashes']}}, maximum_retry_attempts=0)
    refs = []
    if (result.get('resolution') or {}).get('status') == 'resolved':
        raw_path = plane.state_store.layout.snapshot(run_id,'provider-result',sha256_json(result['provider_result']))
        write_immutable_json(raw_path,result['provider_result'])
        raw_ref = relative_ref(state,raw_path)
        evidence = normalize_provider_result(request,result['resolution'],snapshot,result['provider_result'],
            run_id=run_id,step_id='hot-reload',evidence_id=run_id+'-evidence',
            definition_fingerprint=plan['definition_fingerprint'],structured_result_ref=raw_ref,raw_refs=[raw_ref])
        append_runtime_execution_evidence(plane.evidence_store,evidence)
        refs.append(evidence['evidence_id'])
    plane._save_execution_state(run_id=run_id,step_id='hot-reload',action_id='editor.hot_reload',
        status='blocked',evidence_refs=refs)
    return {**result,'run_id':run_id,'evidence_refs':refs,'acceptance':'blocked',
            'required_gates':{'hot_reload':result['status'],'play_behavior':'not_observed',
                              'normal_compile':'not_observed','qa_acceptance':'not_observed'}}
