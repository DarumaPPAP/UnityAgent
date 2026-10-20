"""Pure adaptive execution selection. Authority and approvals stay with UnityAgent.

This function decides *coordination cost*, never execution permission or success.
A SubAgent selection is a semantic constraint, not authorization to mutate.
"""
from __future__ import annotations

from typing import Any

PATHS = ("fast", "standard", "orchestrated")
RISK = {"low", "medium", "high", "critical"}
DESIGN = {"not_required", "conditional", "required"}
CONTEXT = {"tight", "standard", "wide"}


def select_execution_path(
    *,
    task_count: int,
    simple_task: bool,
    risk: str,
    design_review: str,
    requires_replan: bool,
    project_bound: bool,
    scope_known: bool,
    requested_subagent: str | None = None,
    required_subagents: tuple[str, ...] = (),
    resource_conflict: bool = False,
    context_profile: str = "tight",
) -> dict[str, Any]:
    """Choose a bounded path without allocating extra agents or worktrees.

    The returned plan is *not* permission to execute. Caller must enforce
    Project binding, existing Policy/Approval/Scope, resource leases, and
    evidence before/after Runtime dispatch. Unknown prerequisites fail closed.
    """
    if isinstance(task_count, bool) or not isinstance(task_count, int) or task_count < 1:
        raise ValueError("task_count must be a positive integer")
    if not all(isinstance(v, bool) for v in
               (simple_task, requires_replan, project_bound, scope_known, resource_conflict)):
        raise ValueError("adaptive execution requires observed boolean facts")
    if risk not in RISK or design_review not in DESIGN or context_profile not in CONTEXT:
        raise ValueError("unknown risk, design review, or context profile")
    if not isinstance(required_subagents, tuple) or any(
            not isinstance(x, str) or not x.endswith("_subagent") for x in required_subagents):
        raise ValueError("required_subagents must contain canonical SubAgent ids")
    if requested_subagent is not None and (
            not isinstance(requested_subagent, str) or not requested_subagent.endswith("_subagent")):
        raise ValueError("invalid explicitly requested SubAgent")
    if not project_bound or not scope_known:
        return {
            "status": "blocked",
            "path": None,
            "reason": "project binding or scope unknown; fail closed",
            "subagent_ids": [],
            "parent_graph_required": False,
            "worktree_required": False,
            "context_profile": context_profile,
            "approval_required": "consult_policy",
            "evidence_required": True,
        }

    selected = tuple(dict.fromkeys(required_subagents +
                    ((requested_subagent,) if requested_subagent else ())))
    # Explicit selection cannot override an incompatible authority decision.
    if requested_subagent is not None and required_subagents and \
            requested_subagent not in required_subagents:
        return {
            "status": "blocked", "path": None,
            "reason": "requested SubAgent is incompatible with resolved task ownership",
            "subagent_ids": list(selected),
            "parent_graph_required": False, "worktree_required": False,
            "context_profile": context_profile,
            "approval_required": "consult_policy", "evidence_required": True,
        }

    multi = task_count > 1 or len(selected) > 1 or resource_conflict
    bounded = (simple_task and risk == "low" and design_review == "not_required" and
               not requires_replan and not selected and not multi and context_profile == "tight")
    path = "orchestrated" if multi else "fast" if bounded else "standard"
    return {
        "status": "planned",
        "path": path,
        "reason": {
            "fast": "bounded direct execution without additional agent/graph/worktree",
            "standard": "single bounded task requires specialist or enhanced verification",
            "orchestrated": "multiple tasks, specialists, or resource conflicts require coordination",
        }[path],
        "subagent_ids": list(selected),
        "parent_graph_required": path == "orchestrated",
        "worktree_required": False,  # Scheduler decides only after resource/path analysis.
        "context_profile": "tight" if path == "fast" else context_profile,
        "approval_required": "consult_policy",
        "evidence_required": True,
    }


def observe_execution_strategy(*, current_path: str, selection_inputs: dict[str, Any],
                               failure_class: str | None = None, uncertain_side_effects: bool = False) -> dict[str, Any]:
    """確認済み入力だけで調整コストを提案する。実経路・権限・入力は変更しない。"""
    value = dict(current_path=current_path if current_path in PATHS else None, proposed_path=None,
                 recommendation='not_evaluated', reason_codes=[], applied=False)
    if not isinstance(uncertain_side_effects, bool) or (failure_class is not None and (not isinstance(failure_class, str) or not failure_class)):
        # 不正な失敗情報を確認済みの停止Factとして扱わない。
        value['reason_codes'] = ['invalid_failure_inputs']
        return value
    if uncertain_side_effects or failure_class:
        # 失敗の解消を戦略変更で代用しない。未知の分類も停止理由として残す。
        value.update(recommendation='blocked', reason_codes=[
            'uncertain_side_effects' if uncertain_side_effects else failure_class])
        return value
    if current_path not in PATHS or not isinstance(selection_inputs, dict):
        # 不正な現在経路から順序比較を行わない。
        value['reason_codes'] = ['invalid_observation_inputs']
        return value
    try:
        candidate = select_execution_path(**selection_inputs)
    except (TypeError, ValueError):
        # selectorが確認できないFactを補完しない。生入力を診断へ漏らさない。
        value['reason_codes'] = ['missing_or_invalid_selection_inputs']
        return value
    if candidate['status'] == 'blocked' or selection_inputs.get('resource_conflict', False):
        # 初期selectorの競合時調整とは別に、途中観測では競合解消まで停止を提案する。
        value.update(recommendation='blocked', reason_codes=[
            'resource_conflict' if selection_inputs.get('resource_conflict') else 'selection_prerequisite_blocked'])
        return value
    proposed = candidate['path']
    delta = PATHS.index(proposed) - PATHS.index(current_path)
    value.update(proposed_path=proposed, recommendation='promote' if delta > 0 else 'demote' if delta < 0 else 'keep',
                 reason_codes=['confirmed_selection_inputs'])
    return value


DAG_FACT_FIELDS = ('simple_task', 'risk', 'design_review', 'requires_replan', 'project_bound',
                   'scope_known', 'requested_subagent', 'required_subagents', 'resource_conflict', 'context_profile')


def build_dag_inputs(tasks, state, *, task_facts=None, current_path=None, failure_classes=(), uncertain_side_effects=False):
    """固定DAGの残作業を意味付けする。子Taskの経路を親の現在戦略へ代入しない。"""
    task_facts = task_facts or {}
    by_id = {task['id']:task for task in tasks}
    if set(by_id) != set(state['tasks']):
        raise ValueError('Task state and contract differ')
    verified = {name for name, item in state['tasks'].items() if item['status'] == 'verified'
                and item['gates'] and all(g == 'passed' for g in item['gates'].values())}
    summaries = {}
    remaining = []
    ready = []
    for name, task in by_id.items():
        item = state['tasks'][name]
        status = item['status']
        if status == 'verified' and name not in verified:
            raise ValueError('Verified Task has inconsistent Acceptance')
        deps = task.get('depends_on', [])
        satisfied = all(dep in verified for dep in deps)
        decision = item.get('semantic_decision', {}).get('decision')
        consumed = item.get('semantic_retries', 0)
        budget = max(0, task.get('semantic_repair_limit', 2) - consumed)
        attempts = len(item.get('handoff_history', []))
        candidates_left = max(0, len(task.get('repair_candidates', [])) + 1 - attempts)
        repair_ready = status == 'blocked' and decision == 'continue' and budget > 0 and candidates_left > 0
        if name in verified:
            category = 'verified'
        elif status == 'running':
            category = 'running'
        elif status == 'unavailable' or 'unavailable' in item['gates'].values():
            category = 'unavailable'
        elif repair_ready:
            category = 'repair_pending'
        elif status == 'blocked_dependency' or (status == 'pending' and any(state['tasks'][dep]['status'] in {'blocked','failed','unavailable','blocked_dependency'} for dep in deps)):
            category = 'blocked_dependency'
        elif status in {'blocked','failed'}:
            category = 'failed'
        else:
            category = 'pending' if satisfied else 'waiting_dependency'
        if name not in verified:
            remaining.append(name)
            if satisfied and (status == 'pending' or repair_ready):
                ready.append(name)
        summaries[name] = {'status':status, 'category':category, 'dependencies_satisfied':satisfied,
            'dependency_blockers':[dep for dep in deps if dep not in verified], 'gates':dict(item['gates']),
            'attempts_completed':attempts, 'semantic_retries':consumed, 'repair_budget_remaining':budget,
            'repair_candidates_remaining':candidates_left}
    selection = {}
    missing = []
    if remaining:
        selection['task_count'] = len(remaining)
        for name in remaining:
            for field in DAG_FACT_FIELDS:
                facts = task_facts.get(name, {})
                if field not in facts:
                    missing.append({'task_id':name, 'field':field, 'reason':
                        'not_executed' if not state['tasks'][name].get('handoff_history') else 'boundary_fact_not_confirmed'})
                else:
                    value = facts[field]
                    if field in {'simple_task','requires_replan','project_bound','scope_known','resource_conflict'}:
                        valid = isinstance(value, bool)
                    elif field in {'risk','design_review','context_profile'}:
                        allowed = {'risk':RISK, 'design_review':DESIGN, 'context_profile':CONTEXT}[field]
                        valid = isinstance(value, str) and value in allowed
                    elif field == 'required_subagents':
                        valid = isinstance(value, tuple) and all(isinstance(x,str) and x.endswith('_subagent') for x in value)
                    else:
                        valid = value is None or isinstance(value,str) and value.endswith('_subagent')
                    if not valid:
                        missing.append({'task_id':name,'field':field,'reason':'invalid_boundary_fact'})
        # 集約は全残Taskの同じ項目が確認済みのときだけ。既定値で穴を埋めない。
        for field in DAG_FACT_FIELDS:
            if any(m['field'] == field for m in missing):
                continue
            values = [task_facts[name][field] for name in remaining]
            if field in {'simple_task','project_bound','scope_known'}:
                selection[field] = all(values)
            elif field in {'requires_replan','resource_conflict'}:
                selection[field] = any(values)
            elif field in {'risk','design_review','context_profile'}:
                order = {'risk':('low','medium','high','critical'), 'design_review':('not_required','conditional','required'),
                         'context_profile':('tight','standard','wide')}[field]
                if all(value in order for value in values):
                    selection[field] = max(values, key=order.index)
            elif field == 'required_subagents':
                selection[field] = tuple(dict.fromkeys(x for value in values for x in value))
            elif len(set(values)) == 1:
                selection[field] = values[0]
            else:
                missing.append({'task_id':None, 'field':field, 'reason':'incompatible_explicit_requests'})
    unknown_effects = uncertain_side_effects or any(s['category']=='running' for s in summaries.values())
    failures = sorted(set(failure_classes))
    if any(item['category'] in {'failed','unavailable','blocked_dependency'} for item in summaries.values()) and not failures:
        failures.append('task_acceptance_blocked')
    proposal = {'current_path':current_path if current_path in PATHS else None, 'proposed_path':None,
                'recommendation':'not_evaluated', 'reason_codes':[], 'applied':False}
    candidate = None
    if not remaining:
        proposal['reason_codes'] = ['no_remaining_tasks']
    elif failures or unknown_effects:
        proposal = observe_execution_strategy(current_path=current_path, selection_inputs=selection,
            failure_class=failures[0] if failures else None, uncertain_side_effects=unknown_effects)
        proposal['reason_codes'] = failures + (['uncertain_side_effects'] if unknown_effects else [])
    elif missing:
        proposal['reason_codes'] = ['missing_boundary_facts']
    else:
        try:
            candidate = select_execution_path(**selection)['path']
            proposal = observe_execution_strategy(current_path=current_path, selection_inputs=selection)
        except (ValueError, TypeError):
            proposal['reason_codes'] = ['invalid_boundary_facts']
        if current_path is None and candidate:
            proposal['reason_codes'] = ['parent_strategy_not_observed']
    return {'tasks':summaries, 'verified_task_ids':sorted(verified), 'remaining_task_ids':remaining,
        'ready_task_ids':ready, 'selection_inputs':selection, 'missing_inputs':missing,
        'decision':{**proposal, 'candidate_path':candidate}}



def facts_from_boundary(task, proof, manifest, semantic_decision, *, attempt, same_revision, proof_ref, manifest_ref):
    """現在Taskの有効な判定結果を射影する。未実行Taskや別修復候補には転用しない。"""
    values = {}
    provenance = {}
    if same_revision:
        candidate = task['entry_request'] if attempt == 0 else task['repair_candidates'][attempt-1]
        inspection = candidate['intent']['kind'] == 'project_inspection'
        risk = {'R0':'low','R1':'medium','R2':'high','R3':'critical'}.get(proof['task_contract_projection']['risk_level'])
        values = {'simple_task':inspection, 'design_review':'not_required' if inspection else proof['route_decision']['design_review'],
            'project_bound':proof['task_fingerprint']['project_access']=='authorized',
            'requested_subagent':candidate.get('requested_subagent'), 'required_subagents':tuple(proof['execution_plan']['subagent_ids']),
            'context_profile':manifest['budget_report']['profile']}
        if isinstance(proof.get('mutation_scope'), dict):
            values['scope_known'] = True
        if risk:
            values['risk'] = risk
        if semantic_decision['decision'] in {'continue','replan'}:
            values['requires_replan'] = semantic_decision['decision'] == 'replan'
        provenance = {key:proof_ref for key in values}
        provenance['context_profile'] = manifest_ref
        if 'requires_replan' in values:
            provenance['requires_replan'] = 'boundary.semantic_decision'
    return {'values':values, 'provenance':provenance,
        'freshness':'same_project_revision' if same_revision else 'project_revision_changed',
        'requires_revalidation':[field for field in DAG_FACT_FIELDS if field not in values] if same_revision else ['all_selection_facts']}
