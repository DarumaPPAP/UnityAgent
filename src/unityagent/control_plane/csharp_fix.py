"""限定C#提案を既存Approval・ToolBroker・同一revisionの検証へ束縛する。"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import atomic_write_json, read_json, safe_id, sha256_bytes, sha256_json, write_immutable_json
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.runtime.guardrails.csharp_patch import patch_revisions, project_revision
from unityagent.runtime.handoff.csharp_patch import propose_patch


def _path(plane, kind, identifier):
    return plane.state_store.layout.root / 'csharp-fixes' / kind / (safe_id(identifier) + '.json')


def load_patch_plan(plane, identifier):
    plan = read_json(_path(plane, 'plans', identifier))
    if plan['plan_id'] != identifier or sha256_json({key: value for key, value in plan.items() if key != 'plan_id'}).split(':')[1] != identifier:
        raise ValueError('C# patch Plan digest differs')
    for ref in plan['source_evidence_refs']:
        record = plane.evidence_store.verify_record(ref)
        if record.get('capability') != 'source.read' or record.get('completion') != 'verified':
            raise ValueError('C# proposal source Evidence is incomplete')
        observed = plane.evidence_store.read_observation(ref, expected_run_id=record['run_id'],
            expected_project_root=plan['project_root'], expected_capability='source.read')
        if observed['result'].get('sha256') != plan['observed_source_sha256']:
            raise ValueError('C# proposal source observation differs')
        context = decision_snapshot(plane.state_store.layout, plan['proposal_context_ref'], record['run_id'], 'context-manifest')
        view = context['materialized_context']
        if (view['context_id'] != plan['patch']['source_context_id']
                or view['context_fingerprint']['value'] != plan['patch']['source_context_fingerprint']):
            raise ValueError('C# proposal Context binding differs')
    return plan


def approve_csharp_fix(plane, plan_id):
    plan = load_patch_plan(plane, plan_id)
    if project_revision(plan['project_root']) != plan['expected_revision']:
        raise ValueError('C# patch approval preimage is stale')
    now = datetime.now(timezone.utc)
    decision = {'schema_version': '1.0', 'approval_decision_id': 'csharp-' + uuid.uuid4().hex,
        'operation': 'csharp_local_fix', 'plan_id': plan_id, 'plan_digest': sha256_json(plan),
        'project_root': plan['project_root'], 'expected_revision': plan['expected_revision'],
        'scope_paths': [plan['intent']['target_source']], 'human_review': 'approved', 'status': 'active',
        'approved_at': now.isoformat(), 'expires_at': (now + timedelta(minutes=15)).isoformat(), 'revocation_epoch': 0}
    decision['decision_digest'] = sha256_json(decision)
    ApprovalDecisionStore(plane.state_store.layout.root).register(decision)
    return {'approval_ref': decision['approval_decision_id'], 'patch_plan_id': plan_id}


def _approval(plane, plan, approval_ref):
    record = ApprovalDecisionStore(plane.state_store.layout.root).get(safe_id(approval_ref, 'approval_ref'))
    decision = record['decision']
    if (decision.get('decision_digest') != sha256_json({key: value for key, value in decision.items() if key != 'decision_digest'})
            or decision.get('operation') != 'csharp_local_fix' or decision.get('plan_id') != plan['plan_id']
            or decision.get('plan_digest') != sha256_json(plan) or decision.get('project_root') != plan['project_root']
            or decision.get('expected_revision') != plan['expected_revision']
            or decision.get('scope_paths') != [plan['intent']['target_source']]
            or decision.get('status') != 'active' or decision.get('human_review') != 'approved'
            or decision.get('revocation_epoch') != record['current_revocation_epoch']
            or datetime.fromisoformat(decision['expires_at']) <= datetime.now(timezone.utc)):
        raise ValueError('C# patch approval is missing, stale, revoked, or bound to another diff')


def prepare(plane, entry, context, handoff):
    project = Path(entry['project_root']).resolve(strict=True)
    state_root = plane.state_store.layout.root
    if state_root == project or project in state_root.parents:
        raise ValueError('C# execution Persistence must be outside the Project')
    intent = {key: value for key, value in entry['intent'].items() if key != 'patch_plan_id'}
    if project_revision(project) != intent['expected_revision']:
        raise ValueError('C# Entry expected revision is stale')
    session = {'entry': entry, 'intent': intent, 'project': project, 'plan': None, 'source': None,
               'file_arguments': {'relative_path': intent['target_source']}, 'context': context}
    plan_id = entry['intent'].get('patch_plan_id')
    if plan_id:
        plan = load_patch_plan(plane, plan_id)
        if (plan['intent'] != intent or plan['project_root'] != str(project)
                or any(plan['definition_fingerprint'].get(key) != value for key, value in handoff['definition_fingerprint'].items() if key != 'context_revision')):
            raise ValueError('C# approved Plan differs from the current Typed Intent')
        if _path(plane, 'applications', plan_id).exists():
            raise ValueError('C# patch was already attempted; reconciliation or a new approved Plan is required')
        _approval(plane, plan, entry.get('approval_ref'))
        revisions = patch_revisions(project, intent['target_source'], plan['patch']['expected_text'], plan['patch']['replacement_text'])
        if any(plan[key] != value for key, value in revisions.items()):
            raise ValueError('C# approved patch preimage differs')
        session.update(plan=plan, context=replace(context, approval_required=True, approval_complete=True),
            file_arguments={'bounded_csharp_patch': True, 'relative_path': intent['target_source'],
                'expected_text': plan['patch']['expected_text'], 'replacement_text': plan['patch']['replacement_text'], **revisions})
    return session


def before_capability(plane, session, capability, run_id):
    plan = session['plan']
    expected = plan['result_revision'] if plan and capability in {'static.review', 'compile.observe', 'project.test'} else session['intent']['expected_revision']
    if project_revision(session['project']) != expected:
        raise ValueError('C# capability Project revision changed')
    session['input_revision'] = expected
    if capability == 'source.patch':
        _approval(plane, plan, session['entry'].get('approval_ref'))
        atomic_write_json(_path(plane, 'applications', plan['plan_id']),
            {'plan_id': plan['plan_id'], 'run_id': run_id, 'phase': 'dispatching', 'evidence_refs': []})


def after_capability(session, capability, outcome):
    plan = session['plan']
    expected = plan['result_revision'] if plan and capability != 'source.read' else session['intent']['expected_revision']
    return outcome.get('status') == 'completed' and project_revision(session['project']) == expected


def finish(plane, session, *, handoff, manifest, manifest_ref, evidence_refs, results, model,
           command_prefix=None, timeout_seconds=120.0, reasoning_effort='high'):
    plan = session['plan']
    successful = bool(results) and all(item.get('status') == 'completed' for item in results)
    if session['intent'].get('verification_only'):
        expected = session['intent']['expected_revision']
        successful = (successful and {item.get('capability') for item in results}
                      == {'source.read', 'compile.observe', 'project.test'}
                      and project_revision(session['project']) == expected)
        for ref in evidence_refs:
            record = plane.evidence_store.verify_record(ref, expected_run_id=handoff['run_id'])
            if record.get('execution_binding') != {'patch_plan_id': None, 'input_project_revision': expected,
                    'result_project_revision': expected, 'context_manifest_ref': manifest_ref}:
                successful = False
        return {'status': 'completed' if successful else 'blocked', 'verification_only': True,
                'result_revision': project_revision(session['project'])}
    if plan is None:
        if not successful or session['source'] is None:
            return {'status': 'blocked', 'reason': 'csharp_source_observation_failed'}
        patch = propose_patch(handoff, manifest, intent=session['intent'], source=session['source'],
            original_project=session['project'], model=model, command_prefix=command_prefix,
            timeout_seconds=timeout_seconds, reasoning_effort=reasoning_effort)
        revisions = patch_revisions(session['project'], session['intent']['target_source'],
                                    patch['expected_text'], patch['replacement_text'])
        if revisions['expected_revision'] != session['intent']['expected_revision']:
            raise ValueError('C# Project changed during model proposal')
        core = {'schema_version': '1.0', 'project_root': str(session['project']), 'intent': session['intent'],
            'patch': patch, **revisions, 'proposal_context_ref': manifest_ref, 'source_evidence_refs': list(evidence_refs),
            'definition_fingerprint': handoff['definition_fingerprint'], 'model': model, 'model_usage': None,
            'observed_source_sha256': sha256_bytes(session['source'].encode('utf-8')).split(':')[1]}
        identifier = sha256_json(core).split(':')[1]
        plan = {**core, 'plan_id': identifier}
        write_immutable_json(_path(plane, 'plans', identifier), plan)
        return {'status': 'blocked', 'reason': 'explicit_patch_approval_required', 'patch_plan_id': identifier,
                'patch_preview': patch, 'expected_revision': plan['expected_revision'], 'result_revision': plan['result_revision']}
    final_revision = project_revision(session['project'])
    required = {'source.read', 'source.patch', 'static.review', 'compile.observe', 'project.test'}
    successful = successful and {item.get('capability') for item in results} == required and final_revision == plan['result_revision']
    for ref in evidence_refs:
        record = plane.evidence_store.verify_record(ref, expected_run_id=handoff['run_id'])
        capability = record.get('capability')
        expected_input = plan['expected_revision'] if capability in {'source.read', 'source.patch'} else plan['result_revision']
        expected_result = plan['expected_revision'] if capability == 'source.read' else plan['result_revision']
        if record.get('execution_binding') != {'patch_plan_id': plan['plan_id'], 'input_project_revision': expected_input,
                'result_project_revision': expected_result, 'context_manifest_ref': manifest_ref}:
            successful = False
    status = 'completed' if successful else 'blocked'
    atomic_write_json(_path(plane, 'applications', plan['plan_id']),
        {'plan_id': plan['plan_id'], 'run_id': handoff['run_id'], 'phase': 'finalized', 'status': status,
         'result_revision': final_revision, 'evidence_refs': list(evidence_refs)})
    return {'status': status, 'patch_plan_id': plan['plan_id'], 'result_revision': final_revision,
            'csharp_gates': {capability: 'passed' if any(item.get('capability') == capability
                and item.get('status') == 'completed' for item in results) and final_revision == plan['result_revision']
                else 'not_observed' for capability in required}}
