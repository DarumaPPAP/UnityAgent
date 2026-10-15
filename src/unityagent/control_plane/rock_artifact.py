"""固定Blender制作を既存Control Plane / Broker / Approval / Evidenceへ接続する。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import uuid

from unityagent.control_plane.task_execution import project_revision
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import sha256_json, safe_id, read_json, write_immutable_json
from unityagent.persistence.evidence.runtime_adapter import append_runtime_execution_evidence
from unityagent.runtime.evidence_capture.tool_runtime_evidence import normalize_provider_result
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.blender_mcp.rock_template import rock_template
from unityagent.runtime.tooling.providers.blender_mcp.blender_provider import BlenderProvider
from unityagent.runtime.tooling.capability_resolver import ResolutionContext


def plan_rock(project_root, state_root, job_id, definition):
    project, state = Path(project_root).resolve(strict=True), Path(state_root).resolve()
    job_id = safe_id(job_id)
    if project == state or project in state.parents:
        raise ValueError('Staging/Persistence must be outside the Unity Project')
    folder = state / 'blender-jobs' / job_id
    template = rock_template(folder / 'Rock.fbx', folder / 'artifact.json')
    plan = {'schema_version': '1.0', 'job_id': job_id, 'project_root': str(project),
            'project_revision': project_revision(project), 'definition_fingerprint': dict(definition),
            'profile_id': 'world_creator_subagent', 'template': template,
            'required_gates': ['blender_mesh', 'fbx_export', 'artifact_integrity'],
            'mutation_scope': {'allowed_paths': ['blender-jobs/' + job_id],
                               'prohibited_paths': ['Assets', 'Packages', 'ProjectSettings']},
            'risk': 'Blender Scene adds one named mesh and material; output is Staging only',
            'external_paid_generation': False}
    plan['plan_id'] = sha256_json(plan).split(':')[1]
    write_immutable_json(state / 'rock-plans' / (plan['plan_id'] + '.json'), plan)
    return plan


def approve_rock(state_root, plan_id):
    state = Path(state_root).resolve()
    plan = read_json(state / 'rock-plans' / (safe_id(plan_id) + '.json'))
    decision = {'approval_decision_id': 'rock-' + uuid.uuid4().hex, 'plan_digest': sha256_json(plan),
                'project_root': plan['project_root'], 'operation': 'blender_rock',
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                'revocation_epoch': 0}
    ApprovalDecisionStore(state).register(decision)
    return decision


def apply_rock(plane, plan_id, approval_ref, client, *, definition_fingerprint):
    state = plane.state_store.layout.root
    plan = read_json(state / 'rock-plans' / (safe_id(plan_id) + '.json'))
    project = Path(plan['project_root'])
    if plan['definition_fingerprint'] != dict(definition_fingerprint) or plan['project_revision'] != project_revision(project):
        raise ValueError('Rock Task definition or Project revision changed')
    def check_approval(request_digest):
        expected = sha256_json({'template': plan['template'], 'approval_ref': approval_ref})
        if request_digest is not None and request_digest != expected:
            raise ValueError('Reviewed Blender template changed since approval')
        record = ApprovalDecisionStore(state).get(approval_ref)
        decision = record['decision']
        if (decision.get('operation') != 'blender_rock' or decision.get('plan_digest') != sha256_json(plan)
                or decision.get('project_root') != str(project)
                or record['current_revocation_epoch'] != decision['revocation_epoch']
                or datetime.fromisoformat(decision['expires_at']) <= datetime.now(timezone.utc)):
            raise ValueError('Rock approval is invalid, stale or revoked')
    check_approval(None)
    # 実接続のProtocol/Tool discoveryが完了したSessionだけを利用可能にする。
    available = bool(getattr(client, 'identity', None) and 'execute_blender_code' in getattr(client, 'tools', set()))
    snapshot = discover_environment(project).to_dict()
    snapshot['blender_mcp'] = {'available': available, 'project_bound': True, 'reachable': available,
                             'binding_status': 'bound', 'bound_instance_id': client.session_id}
    request = {'schema_version': '1.0', 'capability': 'world.create', 'operation_kind': 'editor_mutation',
               'project_root': str(project), 'required_evidence': ['domain_result', 'mutation_evidence'],
               'mutation_scope': plan['mutation_scope'], 'approval_ref': approval_ref,
               'preferred_surface': 'host', 'qualifiers': {'workflow': 'blender_rock'}}
    provider = BlenderProvider(project, state, client, job_id=plan['job_id'], check_approval=check_approval)
    result = plane.broker.dispatch(request, snapshot, context=ResolutionContext(
        policy_allowed=True, approval_required=True, approval_complete=True),
        executors={'blender_mcp': provider.execute}, maximum_retry_attempts=0)
    run_id = 'rock-' + plan['job_id']
    refs = []
    if (result.get('resolution') or {}).get('status') == 'resolved':
        from unityagent.persistence.store.atomic_store import relative_ref
        raw_path = plane.state_store.layout.snapshot(run_id, 'provider-result', sha256_json(result['provider_result']))
        write_immutable_json(raw_path, result['provider_result'])
        raw_ref = relative_ref(state, raw_path)
        evidence = normalize_provider_result(provider_result=result['provider_result'], request=request,
            resolution=result['resolution'], environment_snapshot=snapshot,
            evidence_id=run_id + '-' + uuid.uuid4().hex[:12], run_id=run_id, step_id='blender-rock',
            definition_fingerprint=definition_fingerprint, structured_result_ref=raw_ref, raw_refs=[raw_ref])
        persisted = append_runtime_execution_evidence(plane.evidence_store, evidence)
        refs.append(persisted['evidence_id'])
    plane._save_execution_state(run_id=run_id, step_id='blender-rock', action_id='world.create',
        status=result['status'], evidence_refs=refs)
    return {**result, 'run_id': run_id, 'evidence_refs': refs,
            'unity_import': 'BLOCKED_NOT_RUN', 'verified': False}
