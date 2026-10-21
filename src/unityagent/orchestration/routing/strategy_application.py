"""次の確定済みAttemptへ適用する親Runの調整モードと、その読取検証。"""
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError

from unityagent.resources import resource_root

from unityagent.orchestration.routing.adaptive_execution import PATHS, facts_from_boundary, read_dag_decision, select_execution_path
from unityagent.persistence.state.dag_decision import decision_snapshot
from unityagent.persistence.store.atomic_store import sha256_json
from unityagent.persistence.store.layout import PersistenceLayout


def preparation_inputs(task, attempt, proof, manifest):
    facts = facts_from_boundary(task, proof, manifest, {'decision': 'exit'}, attempt=attempt,
        same_revision=True, proof_ref='', manifest_ref='')['values']
    return {**facts, 'task_count': 1, 'requires_replan': False, 'resource_conflict': False}


def select_coordination(prepared, task, *, current_path, boundary=None):
    """残Task数で昇格させず、今回の準備情報と固定契約の調整要件だけを使う。"""
    inputs = dict(prepared['selection_inputs'])
    inputs['required_subagents'] = tuple(inputs['required_subagents'])
    initial = select_execution_path(**inputs)
    if initial['status'] != 'planned' or current_path not in (*PATHS, None):
        raise ValueError('Unconfirmed coordination inputs')
    repair = prepared['attempt'] > 0
    if repair:
        name, attempt = prepared['task_id'], prepared['attempt']
        if (not boundary or boundary['boundary']['task_id'] != name
                or boundary['boundary']['attempt'] != attempt - 1
                or boundary['boundary']['semantic_decision']['decision'] != 'continue'
                or boundary['inputs']['tasks'][name]['category'] != 'repair_pending'
                or attempt > task.get('semantic_repair_limit', 2)
                or attempt > len(task.get('repair_candidates', []))
                or any(r['operation_kind'] != 'read' for r in prepared['handoff']['capability_requests'])):
            raise ValueError('Repair coordination is outside the verified fixed contract')
    coordinated = bool(task.get('depends_on') or task.get('resource_claims') or task.get('write_set'))
    path = 'orchestrated' if coordinated else 'standard' if repair else initial['path']
    recommendation = 'initialize' if current_path is None else 'keep' if current_path == path else (
        'promote' if PATHS.index(path) > PATHS.index(current_path) else 'demote')
    return {'current_path': current_path, 'path': path, 'recommendation': recommendation,
            'reason_codes': ['fixed_dag_coordination' if coordinated else 'verified_repair' if repair else 'prepared_attempt']}


def validate_preparation(layout, prepared, contract):
    """保存されたFactを今回のTask・Project・定義・Scopeの出所へ戻して検証する。"""
    run_id, name, attempt = prepared['run_id'], prepared['task_id'], prepared['attempt']
    if prepared.get('plan_ref'):
        from unityagent.persistence.state.plan import read_plan
        plan = read_plan(layout, prepared['plan_ref'], run_id)
        if plan['tasks'] != contract['tasks'] or plan['definition_fingerprint'] != contract['definition_fingerprint']:
            raise ValueError('Dynamic preparation Plan binding differs')
    tasks = {task['id']: task for task in contract['tasks']}
    task = tasks[name]
    projects = set(plan['root_contract']['projects']) if prepared.get('plan_ref') else {str(Path(value['workspace']).resolve()) for value in tasks.values()}
    revisions = prepared['project_revisions']
    if set(revisions) != projects or any(not isinstance(value, str) or len(value) != 71 or not value.startswith('sha256:') or any(c not in '0123456789abcdef' for c in value[7:]) for value in revisions.values()):
        raise ValueError('Prepared Project revision set differs')
    candidate = task['entry_request'] if attempt == 0 else task['repair_candidates'][attempt - 1]
    child = f'{run_id}-{name}' + (f'-repair{attempt}' if attempt else '')
    handoff = prepared['handoff']
    from unityagent.runtime.contracts.runtime_handoff import validate_runtime_handoff
    validate_runtime_handoff(handoff)
    if prepared['result_run_id'] != child or handoff['run_id'] != child or prepared['entry_digest'] != sha256_json(candidate):
        raise ValueError('Prepared Task or Attempt differs')
    proof = decision_snapshot(layout, prepared['proof_ref'], child, 'orchestration-decision')
    manifest = decision_snapshot(layout, prepared['manifest_ref'], child, 'context-manifest')
    view = manifest['materialized_context']
    effective = {**contract['definition_fingerprint'], **{k: view['definition_fingerprint'][k] for k in ('policy_revision', 'context_revision')}}
    if (manifest['run_id'] != child or proof['context_manifest_ref'] != prepared['manifest_ref']
            or handoff['definition_fingerprint'] != effective
            or handoff['context_id'] != view['context_id']
            or handoff['context_fingerprint'] != view['context_fingerprint']['value']
            or manifest['budget_report']['decision'] != 'within_budget' or view['unresolved_bindings']):
        raise ValueError('Prepared Context or definition differs')
    for field in ('capability_requests', 'mutation_scope', 'validation_requirements', 'execution_profile'):
        if handoff[field] != proof[field]:
            raise ValueError('Prepared scope or Capability differs')
    if any(Path(r['project_root']).resolve() != Path(task['workspace']).resolve() for r in handoff['capability_requests']):
        raise ValueError('Prepared Project differs')
    if handoff['step_id'] != proof['node_id'] or handoff['task_contract_runtime_projection'] != proof['task_contract_projection']:
        raise ValueError('Prepared runtime contract differs')
    writes = handoff['mutation_scope'].get('allowed_paths', [])
    if any(not any(value == scope or value.startswith(scope.rstrip('/') + '/') for scope in task.get('write_set', [])) for value in writes):
        raise ValueError('Prepared mutation Scope is outside the fixed DAG write set')
    expected = preparation_inputs(task, attempt, proof, manifest)
    if sha256_json(expected) != sha256_json(prepared['selection_inputs']) or prepared['project_facts'] != manifest['project_facts']:
        raise ValueError('Prepared Fact or provenance differs')
    original = dict(expected)
    original['required_subagents'] = tuple(original['required_subagents'])
    if select_execution_path(**original) != proof['execution_plan']:
        raise ValueError('Prepared initial selection differs')
    return task


def read_strategy_application(persistence_root, ref, *, run_id):
    """新形式だけを厳密に読む。既存の観測recordとapplied:falseには触れない。"""
    layout = PersistenceLayout(persistence_root)
    schema = yaml.safe_load((resource_root() / 'src/unityagent/orchestration/contracts/strategy-application.schema.yaml').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    chain, seen = [], set()
    while ref:
        if ref in seen:
            raise ValueError('Application chain cycle')
        seen.add(ref)
        item = decision_snapshot(layout, ref, run_id, 'strategy-application')
        try:
            validator.validate(item)
        except ValidationError as exc:
            raise ValueError('Invalid strategy application schema') from exc
        chain.append(item)
        ref = item['previous_ref']
    current = None
    group = None
    phases = []
    base = None
    fixed_contract_ref = None
    last_boundary_ref = None
    completed = set()
    for sequence, item in enumerate(reversed(chain)):
        if (item['schema_version'] != '1.0' or item['target'] != {'kind': 'parent_dag', 'run_id': run_id}
                or item['sequence'] != sequence):
            raise ValueError('Application target or sequence differs')
        if fixed_contract_ref is None:
            fixed_contract_ref = item['contract_ref']
        contract = decision_snapshot(layout, item['contract_ref'], run_id, 'task-contract')
        prepared = decision_snapshot(layout, item['preparation_ref'], run_id, 'strategy-preparation')
        task = validate_preparation(layout, prepared, contract)
        if item['contract_ref'] != fixed_contract_ref:
            if not prepared.get('plan_ref'):
                raise ValueError('Application fixed contract changed')
            from unityagent.persistence.state.plan import read_plan
            active = read_plan(layout, prepared['plan_ref'], run_id)
            initial = chain[-1]
            original = decision_snapshot(layout, initial['preparation_ref'], run_id, 'strategy-preparation')
            if not original.get('plan_ref'):
                raise ValueError('Application cannot migrate a legacy Run to dynamic Plan')
            root = read_plan(layout, original['plan_ref'], run_id)
            if active['root_contract'] != root['root_contract'] or active['root_digest'] != root['root_digest']:
                raise ValueError('Application immutable Root differs')
        if prepared['run_id'] != run_id or (item['task_id'], item['attempt']) != (prepared['task_id'], prepared['attempt']):
            raise ValueError('Application preparation identity differs')
        key = (item['task_id'], item['attempt'])
        if key != group:
            if key in completed or (phases and phases[-1] != 'finalized'):
                raise ValueError('Unfinished application precedes another Attempt')
            group, phases = key, []
            if item['prior_boundary_ref'] != last_boundary_ref:
                raise ValueError('Application prior boundary is not the latest finalized boundary')
            boundary = read_dag_decision(layout.root, item['prior_boundary_ref'], run_id=run_id) if item['prior_boundary_ref'] else None
            revisions = {sha256_json(project): revision for project, revision in prepared['project_revisions'].items()}
            if boundary and revisions != boundary['project_revisions']:
                raise ValueError('Prepared Project revision differs from prior Acceptance')
            expected = select_coordination(prepared, task, current_path=current, boundary=boundary)
            if item['decision'] != expected:
                raise ValueError('Application decision differs from verified inputs')
            base = {k: item[k] for k in ('preparation_ref', 'contract_ref', 'prior_boundary_ref', 'decision')}
        if any(item[k] != v for k, v in base.items()):
            raise ValueError('Application identity changed within Attempt')
        phase = item['phase']
        allowed = {None: {'prepared'}, 'prepared': {'accepted', 'rejected'}, 'accepted': {'dispatching'}, 'dispatching': {'finalized', 'interrupted'}}
        if phase not in allowed.get(phases[-1] if phases else None, set()):
            raise ValueError('Application lifecycle differs')
        applied = phase in {'accepted', 'dispatching', 'finalized', 'interrupted'}
        if item['applied'] is not applied:
            raise ValueError('Application applied state differs')
        if applied:
            checks = ['prepared_binding'] + (['prior_acceptance'] if item['decision']['path'] != 'fast' else []) + (
                ['fixed_dag'] if item['decision']['path'] == 'orchestrated' else [])
            if item['receipt'] != {'path': item['decision']['path'], 'checks': checks, 'preparation_digest': sha256_json(prepared)}:
                raise ValueError('Runtime acceptance receipt differs')
            current = item['decision']['path']
        if phase == 'finalized':
            final = read_dag_decision(layout.root, item['boundary_ref'], run_id=run_id)
            if final['contract_ref'] != item['contract_ref']:
                raise ValueError('Application result fixed contract differs')
            last_boundary_ref = item['boundary_ref']
            boundary = final['boundary']
            if (boundary['task_id'], boundary['attempt']) != key or item['gates'] != final['inputs']['tasks'][key[0]]['gates']:
                raise ValueError('Application result Acceptance differs')
            snapshot = decision_snapshot(layout, final['state_ref'], run_id, 'dag-boundary')
            if {sha256_json(project): revision for project, revision in prepared['project_revisions'].items()} != snapshot['dispatch_project_revisions']:
                raise ValueError('Prepared Project revision differs from dispatch Acceptance')
            completed.add(key)
            executed = {(name, attempt) for name, value in final['inputs']['tasks'].items() for attempt in range(value['attempts_completed'])}
            if completed != executed:
                raise ValueError('Application history differs from Acceptance Attempts')
        phases.append(phase)
    return chain[0]
