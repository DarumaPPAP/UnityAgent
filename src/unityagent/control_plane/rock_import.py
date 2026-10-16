"""承認済みBlender ArtifactからUnity Editor Import/Receipt/復旧までの最小Production Handoff。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import uuid

from unityagent.control_plane.task_execution import project_revision
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import (
    read_json, safe_id, sha256_json, write_immutable_json,
)
from unityagent.persistence.evidence.runtime_adapter import append_runtime_execution_evidence
from unityagent.runtime.evidence_capture.tool_runtime_evidence import normalize_provider_result
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.native_unity_editor.rock_import_provider import (
    RockImportProvider, TARGET, OWNED_FILES,
)


def _plan_file(state, plan_id):
    return Path(state).resolve() / 'rock-import/plans' / (safe_id(plan_id) + '.json')


def _require_plan(state, plan_id):
    plan = read_json(_plan_file(state, plan_id))
    if plan.get('plan_id') != plan_id:
        raise ValueError('Rock Import Plan mismatch')
    return plan


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan_rock_import(project_root, state_root, job_id, definition):
    """Blender MCP完成Jobの実体だけをProduction Import対象へ固定する。"""
    project = Path(project_root).resolve(strict=True)
    state = Path(state_root).resolve()
    if project == state or project in state.parents:
        raise ValueError('Rock staging must stay outside Unity Project')
    job = read_json(state / 'blender-jobs' / safe_id(job_id) / 'job.json')
    if job.get('status') != 'completed' or not isinstance(job.get('artifact_hash'), str):
        raise ValueError('Blender Artifact is not completed')
    source = (state / 'blender-jobs' / safe_id(job_id) / 'Rock.fbx').resolve(strict=True)
    if source.is_symlink() or source.stat().st_size < 1024 or _file_hash(source) != job['artifact_hash']:
        raise ValueError('Blender FBX source integrity mismatch')
    record = read_json(source.parent / 'artifact.json')
    if record.get('sha256') != job['artifact_hash'] or record.get('uv_layers', 0) < 1:
        raise ValueError('Artifact Manifest integrity mismatch')
    if (project / TARGET).exists() or (project / (TARGET + '.meta')).exists():
        raise ValueError('Rock target is not empty; cannot overwrite')
    core = {'schema_version':'1.0', 'project_root':str(project), 'project_revision':project_revision(project),
            'definition_fingerprint':dict(definition), 'job_id':safe_id(job_id),
            'source_path':str(source), 'source_sha256':job['artifact_hash'],
            'target_root':TARGET, 'owned_files':sorted(OWNED_FILES),
            'mutation_scope':{'allowed_paths':[TARGET], 'prohibited_paths':[]},
            'required_gates':['artifact_integrity','unity_import','prefab_scene_references','visual_acceptance'],
            'rollback':'separate approval and hash+GUID verified Editor asset removal'}
    plan_id = sha256_json(core).split(':', 1)[1]
    plan = {**core, 'plan_id':plan_id}
    write_immutable_json(_plan_file(state, plan_id), plan)
    return plan


def approve_rock_import(state_root, plan_id, kind):
    """Mutation / Save / Rollbackに別の明示承認を要求する。"""
    if kind not in {'mutation','save','rollback'}:
        raise ValueError('Unknown Rock Import approval kind')
    plan = _require_plan(state_root, plan_id)
    now = datetime.now(timezone.utc)
    decision = {'schema_version':'1.0', 'approval_decision_id':'rock-import-'+uuid.uuid4().hex,
                'operation':'rock_import_'+kind, 'plan_id':plan_id, 'plan_digest':sha256_json(plan),
                'project_root':plan['project_root'], 'scope_paths':plan['owned_files'],
                'approved_at':now.isoformat(), 'expires_at':(now + timedelta(minutes=30)).isoformat(),
                'human_review':'approved','status':'active','revocation_epoch':0}
    decision['decision_digest'] = sha256_json(decision)
    ApprovalDecisionStore(state_root).register(decision)
    return decision


def _check_approval(state_root, plan, approval_ref, kind):
    if not approval_ref:
        raise ValueError('Rock Import explicit approval required: ' + kind)
    record = ApprovalDecisionStore(state_root).get(safe_id(approval_ref))
    decision = record['decision']
    if (decision.get('approval_decision_id') != approval_ref
            or decision.get('operation') != 'rock_import_'+kind
            or decision.get('plan_id') != plan['plan_id']
            or decision.get('plan_digest') != sha256_json(plan)
            or decision.get('project_root') != plan['project_root']
            or decision.get('scope_paths') != plan['owned_files']
            or decision.get('status') != 'active' or decision.get('human_review') != 'approved'
            or decision.get('revocation_epoch') != record.get('current_revocation_epoch')
            or sha256_json({k:v for k,v in decision.items() if k != 'decision_digest'}) != decision.get('decision_digest')
            or datetime.fromisoformat(decision['expires_at']) <= datetime.now(timezone.utc)):
        raise ValueError('Rock Import Approval invalid, changed, expired or revoked')
    return decision


def _apply(plane, plan_id, approvals, *, action, definition_fingerprint, executor_factory=RockImportProvider):
    state = plane.state_store.layout.root
    plan = _require_plan(state, plan_id)
    project = Path(plan['project_root']).resolve(strict=True)
    if plan['definition_fingerprint'] != dict(definition_fingerprint):
        raise ValueError('Rock Import Definition changed')
    if action == 'apply' and plan['project_revision'] != project_revision(project):
        raise ValueError('Rock Import Project changed before apply')
    if action not in {'apply','rollback'}:
        raise ValueError('Unsupported Rock action')
    required = ('mutation','save') if action == 'apply' else ('rollback',)
    if any(kind not in approvals for kind in required):
        raise ValueError('Rock Import action requires explicit approvals: ' + ','.join(required))
    for kind in required:
        _check_approval(state, plan, approvals[kind], kind)
    def recheck(_plan, phase):
        for kind in required:
            _check_approval(state, plan, approvals[kind], kind)
    environment = discover_environment(project).to_dict()
    provider = executor_factory(project, state, snapshot=environment, check_approvals=recheck)
    request = {'schema_version':'1.0', 'capability':'scene.mutate',
               'operation_kind':'editor_mutation', 'project_root':str(project),
               'required_evidence':['editor_observation','mutation_evidence'],
               'mutation_scope':plan['mutation_scope'], 'approval_ref':approvals[required[0]],
               'preferred_surface':'editor', 'qualifiers':{'workflow':'blender_rock_import'}}
    result = plane.broker.dispatch(request, environment, context=ResolutionContext(
        policy_allowed=True, approval_required=True, approval_complete=True),
        executors={'native_rock_import':provider.execute},
        provider_arguments={'native_rock_import':{'plan':plan,'action':action,
                                                'approval_ref':approvals[required[0]]}},
        maximum_retry_attempts=0)
    run_id = 'rock-import-' + plan_id[:20] + ('-rollback' if action == 'rollback' else '')
    evidence_refs=[]
    if result.get('resolution',{}).get('status') == 'resolved':
        evidence = normalize_provider_result(
            provider_result=result['provider_result'],request=request,
            resolution=result['resolution'],environment_snapshot=environment,
            evidence_id=run_id+'-'+uuid.uuid4().hex[:12],run_id=run_id,
            step_id='rock-'+action,definition_fingerprint=definition_fingerprint)
        persisted = append_runtime_execution_evidence(plane.evidence_store,evidence)
        evidence_refs.append(persisted['evidence_id'])
    plane._save_execution_state(run_id=run_id,step_id='rock-'+action,
        action_id='scene.mutate',status=result['status'],evidence_refs=evidence_refs)
    return {**result,'run_id':run_id,'evidence_refs':evidence_refs,
            'verified':False,'visual_acceptance':'not_observed',
            'production_import':'completed' if action == 'apply' and result.get('status') == 'completed'
                    else 'BLOCKED_NOT_RUN' if result.get('status') != 'completed' else 'rolled_back'}


def apply_rock_import(plane, plan_id, approval_ref, save_approval_ref, *, definition_fingerprint):
    return _apply(plane, plan_id, {'mutation':approval_ref,'save':save_approval_ref},
                  action='apply', definition_fingerprint=definition_fingerprint)


def rollback_rock_import(plane, plan_id, rollback_approval_ref, *, definition_fingerprint):
    return _apply(plane, plan_id, {'rollback':rollback_approval_ref},
                  action='rollback', definition_fingerprint=definition_fingerprint)
