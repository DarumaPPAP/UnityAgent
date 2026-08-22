#!/usr/bin/env python3
"""Runtime primitives for UnityAgent typed Context Manifest generation and tracing."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

INDEX_PATH = Path('.ai/context-index.yaml')
PACK_DIR = Path('.ai/context-packs')
GRAPH_CONTRACT_PATH = Path('.ai/graph-contract.yaml')
USER_POLICY_PATH = Path('.ai/user-policy.yaml')
QUALITY_GATES_PATH = Path('.ai/harness/quality-gates.yaml')
RISK_LEVELS_PATH = Path('.ai/harness/risk-levels.yaml')
MCP_ACTIVATION_PATH = Path('.ai/harness/mcp-activation.yaml')

MANIFEST_SCHEMA_VERSION = '3.1'
GRAPH_SCHEMA_VERSION = '1.0'
EXECUTION_STATUSES = {'in_progress', 'passed', 'failed', 'complete_with_unavailable'}
MUTATION_EFFECTS = {'allow', 'prohibit'}
GATE_REQUIREMENTS = {'required', 'conditional'}
CONTEXT_TYPES = {
    'binding',
    'repository_reference',
    'external_reference',
    'context_include',
    'route_handoff',
}
FACT_SOURCE_KINDS = {'detected_project', 'user_confirmed', 'project_profile'}
FACT_FRESHNESS_STATUSES = {'current', 'stale', 'unknown'}


class ManifestError(ValueError):
    """Raised when runtime data cannot satisfy the Context Manifest contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__('\n'.join(errors))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ManifestError([f'Missing file: {path.as_posix()}'])
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(data, dict):
        raise ManifestError([f'Expected YAML mapping: {path.as_posix()}'])
    return data


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def stable_node_id(node_type: str, stable_id: str) -> str:
    return f'{node_type}:{stable_id}'


def _route_map(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    routes = index.get('routes', {})
    if not isinstance(routes, dict):
        return {}
    return {
        str(route['id']): route
        for route in routes.values()
        if isinstance(route, dict) and route.get('id')
    }


def _context_pack_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((root / PACK_DIR).glob('*.yaml')):
        document = load_yaml(path)
        context_id = str(document.get('id', '')).strip()
        if context_id:
            result[context_id] = path.relative_to(root).as_posix()
    return result


def _fingerprint_errors(
    index: dict[str, Any], route: dict[str, Any], fingerprint: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    contract = index.get('task_fingerprint', {})
    dimensions = contract.get('dimensions', {}) if isinstance(contract, dict) else {}
    required = contract.get('required_dimensions', []) if isinstance(contract, dict) else []

    if not isinstance(fingerprint, dict):
        return ['task.fingerprint must be a mapping.']

    for dimension in required:
        if dimension not in fingerprint:
            errors.append(f'Missing Task Fingerprint dimension: {dimension}')

    for dimension, value in fingerprint.items():
        allowed = dimensions.get(dimension)
        if not isinstance(allowed, list):
            errors.append(f'Unknown Task Fingerprint dimension: {dimension}')
        elif value not in allowed:
            errors.append(f'Unsupported Task Fingerprint value: {dimension}={value}')

    match = route.get('fingerprint_match', {})
    if not isinstance(match, dict):
        return errors + [f"Route {route.get('id')} has no fingerprint_match mapping."]
    for dimension, accepted in match.items():
        if dimension not in fingerprint:
            errors.append(
                f"Fingerprint lacks route-match dimension for {route.get('id')}: {dimension}"
            )
        elif fingerprint[dimension] not in accepted:
            errors.append(
                f"Fingerprint does not match route {route.get('id')}: "
                f"{dimension}={fingerprint[dimension]} not in {accepted}"
            )
    return errors


def _binding(name: str, raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        kind = str(raw.get('kind', 'scalar'))
        values = raw.get('values', [])
        reason = str(raw.get('reason', 'required_context'))
    else:
        kind = 'scalar'
        values = raw if isinstance(raw, list) else [raw]
        reason = 'required_context'
    if not isinstance(values, list):
        values = [values]
    return {
        'name': name,
        'kind': kind,
        'values': [str(value) for value in values],
        'reason': reason,
    }


def _repository_context_item(
    source_path: str,
    reason: str,
    condition: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        'node_id': stable_node_id('source', source_path),
        'reference_type': 'repository_reference',
        'source_path': source_path,
        'reason': reason,
    }
    if condition is not None:
        item['condition'] = condition
    return item


def _external_context_item(
    repository: str,
    path: str,
    requirement: str,
    condition: str | None,
) -> dict[str, Any]:
    stable_id = f'{repository}:{path}'
    item: dict[str, Any] = {
        'node_id': stable_node_id('external_reference', stable_id),
        'repository': repository,
        'path': path,
        'requirement': requirement,
        'reason': 'external_reference',
    }
    if condition is not None:
        item['condition'] = condition
    return item


def _context_include_item(
    context_id: str,
    source_path: str,
    requirement: str,
    condition: str | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        'node_id': stable_node_id('context_pack', context_id),
        'context_id': context_id,
        'source_path': source_path,
        'requirement': requirement,
        'reason': 'context_include',
    }
    if condition is not None:
        item['condition'] = condition
    return item


def _route_handoff_item(
    route_id: str,
    requirement: str,
    condition: str | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        'node_id': stable_node_id('route', route_id),
        'route_id': route_id,
        'requirement': requirement,
        'reason': 'route_handoff',
    }
    if condition is not None:
        item['condition'] = condition
    return item


def _typed_entry(raw: Any, location: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError([f'{location} must use a typed Context Pack mapping.'])
    item_type = str(raw.get('type', '')).strip()
    if item_type not in CONTEXT_TYPES:
        raise ManifestError([f'{location} has unsupported context type: {item_type}'])
    return raw


def _apply_context_entry(
    *,
    raw: Any,
    location: str,
    requirement: str,
    condition: str | None,
    binding_names: set[str],
    unresolved: set[str],
    required_context: list[dict[str, Any]],
    conditional_context: list[dict[str, Any]],
    external_references: list[dict[str, Any]],
    context_includes: list[dict[str, Any]],
    route_handoffs: list[dict[str, Any]],
    context_paths: dict[str, str],
    routes: dict[str, dict[str, Any]],
) -> None:
    item = _typed_entry(raw, location)
    item_type = str(item['type'])

    if item_type == 'binding':
        name = str(item.get('name', '')).strip()
        if not name:
            raise ManifestError([f'{location} binding requires name.'])
        if name not in binding_names:
            unresolved.add(name)
        return

    if item_type == 'repository_reference':
        source_path = str(item.get('path', '')).strip()
        if not source_path:
            raise ManifestError([f'{location} repository_reference requires path.'])
        target = _repository_context_item(
            source_path,
            'required_context' if requirement == 'required' else 'conditional_context',
            condition,
        )
        if requirement == 'required':
            required_context.append(target)
        else:
            conditional_context.append(target)
        return

    if item_type == 'external_reference':
        repository = str(item.get('repository', '')).strip()
        path = str(item.get('path', '')).strip()
        if not repository or not path:
            raise ManifestError([f'{location} external_reference requires repository and path.'])
        external_references.append(
            _external_context_item(repository, path, requirement, condition)
        )
        return

    if item_type == 'context_include':
        context_id = str(item.get('context_id', '')).strip()
        source_path = context_paths.get(context_id)
        if not context_id or source_path is None:
            raise ManifestError([f'{location} includes unknown context: {context_id}'])
        context_includes.append(
            _context_include_item(context_id, source_path, requirement, condition)
        )
        return

    route_id = str(item.get('route_id', '')).strip()
    if not route_id or route_id not in routes:
        raise ManifestError([f'{location} hands off to unknown route: {route_id}'])
    route_handoffs.append(_route_handoff_item(route_id, requirement, condition))


def _mutation_rules(contract_id: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for effect, key in (('allow', 'allowed_mutations'), ('prohibit', 'prohibited_mutations')):
        for raw in contract.get(key, []) or []:
            rule_id = str(raw)
            result.append(
                {
                    'node_id': stable_node_id(
                        'mutation_rule', f'{contract_id}:{effect}:{rule_id}'
                    ),
                    'id': rule_id,
                    'effect': effect,
                }
            )
    return result


def _quality_gates(contract: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for requirement, key in (
        ('required', 'required_quality_gates'),
        ('conditional', 'conditional_quality_gates'),
    ):
        for raw in contract.get(key, []) or []:
            gate_id = str(raw)
            result.append(
                {
                    'node_id': stable_node_id('quality_gate', gate_id),
                    'id': gate_id,
                    'requirement': requirement,
                }
            )
    return result


def _selected_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for section, key in (('policy', 'loaded'), ('knowledge', 'loaded')):
        for item in manifest.get(section, {}).get(key, []) or []:
            if isinstance(item, dict) and item.get('source_path'):
                paths.add(str(item['source_path']))
    context = manifest.get('context', {})
    for key in ('required_context', 'conditional_context', 'source_files', 'context_includes'):
        for item in context.get(key, []) or []:
            if isinstance(item, dict) and item.get('source_path'):
                paths.add(str(item['source_path']))
    return paths


def derive_execution_status(manifest: dict[str, Any]) -> str:
    gates = [
        gate
        for gate in manifest.get('harness', {}).get('quality_gates', []) or []
        if isinstance(gate, dict)
    ]
    if any(gate.get('status') == 'failed' for gate in gates):
        return 'failed'

    required = [gate for gate in gates if gate.get('requirement') == 'required']
    required_statuses = [gate.get('status') for gate in required]
    if not required or not all(
        status in {'passed', 'unavailable'} for status in required_statuses
    ):
        return 'in_progress'

    activated_conditional = [
        gate for gate in gates
        if gate.get('requirement') == 'conditional' and gate.get('status') is not None
    ]
    if any(gate.get('status') == 'unavailable' for gate in required + activated_conditional):
        return 'complete_with_unavailable'
    return 'passed'


def _project_fact(raw: Any, attempt: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError(['project_facts entries must be mappings.'])

    required = (
        'key',
        'value',
        'source_kind',
        'source_path',
        'revision',
        'observed_at_attempt',
        'freshness',
    )
    missing = [field for field in required if field not in raw]
    if missing:
        raise ManifestError([f'project_facts missing fields: {missing}'])

    freshness = raw.get('freshness')
    if not isinstance(freshness, dict):
        raise ManifestError(['project_facts freshness must be a mapping.'])
    if 'status' not in freshness or 'checked_at_attempt' not in freshness:
        raise ManifestError(['project_facts freshness requires status and checked_at_attempt.'])

    key = str(raw.get('key', '')).strip()
    source_path = str(raw.get('source_path', '')).strip()
    source_kind = str(raw.get('source_kind', '')).strip()
    revision = str(raw.get('revision', '')).strip()
    if not key or not source_path or not revision:
        raise ManifestError(['project_facts require non-empty key, source_path and revision.'])

    return {
        'node_id': stable_node_id('project_fact', key),
        'key': key,
        'value': raw['value'],
        'source_kind': source_kind,
        'source_path': source_path,
        'revision': revision,
        'observed_at_attempt': raw['observed_at_attempt'],
        'freshness': {
            'status': freshness.get('status'),
            'checked_at_attempt': freshness.get('checked_at_attempt'),
        },
        'reason': str(raw.get('reason', 'project_fact')),
    }


def build_manifest(
    root: Path,
    request: dict[str, Any],
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_yaml(root / INDEX_PATH)
    routes = _route_map(index)
    context_paths = _context_pack_map(root)
    task = request.get('task', {})
    if not isinstance(task, dict):
        raise ManifestError(['request.task must be a mapping.'])

    task_id = str(task.get('id', '')).strip()
    route_id = str(task.get('route', '')).strip()
    fingerprint = task.get('fingerprint', {})
    errors: list[str] = []
    if not task_id:
        errors.append('request.task.id is required.')
    if not route_id:
        errors.append('request.task.route is required.')
    route = routes.get(route_id)
    if route is None:
        errors.append(f'Unknown route: {route_id}')
    else:
        errors.extend(_fingerprint_errors(index, route, fingerprint))
    if errors:
        raise ManifestError(errors)

    context_pack_path = Path(str(route['context_pack']))
    contract_path = Path(str(route['task_contract']))
    context_pack = load_yaml(root / context_pack_path)
    contract = load_yaml(root / contract_path)

    attempt = 1
    previous_id: str | None = None
    previous_attempt: int | None = None
    previous_failure: dict[str, Any] | None = None
    if previous_manifest is not None:
        previous_errors = validate_manifest(root, previous_manifest)
        if previous_errors:
            raise ManifestError([f'Invalid previous manifest: {error}' for error in previous_errors])
        previous_meta = previous_manifest['manifest']
        previous_task = previous_manifest['task']
        if previous_task.get('id') != task_id:
            raise ManifestError(['Previous manifest task id does not match retry request.'])
        previous_id = str(previous_meta['id'])
        previous_attempt = int(previous_meta['attempt'])
        attempt = previous_attempt + 1
        execution = previous_manifest.get('execution', {})
        previous_failure = {
            'manifest_id': previous_id,
            'attempt': previous_attempt,
            'status': execution.get('status'),
            'failure_reason': execution.get('failure_reason'),
            'evidence_ids': [
                item.get('id')
                for item in execution.get('evidence', []) or []
                if isinstance(item, dict) and item.get('id')
            ],
        }

    manifest_id = str(request.get('manifest_id', '')).strip() or f'{task_id}-a{attempt}'

    raw_bindings = request.get('bindings', {})
    if not isinstance(raw_bindings, dict):
        raise ManifestError(['request.bindings must be a mapping.'])
    bindings = [_binding(str(name), raw) for name, raw in sorted(raw_bindings.items())]
    binding_names = {item['name'] for item in bindings}

    source_files: list[dict[str, Any]] = []
    for item in bindings:
        if item['kind'] != 'source':
            continue
        for source_path in item['values']:
            source_files.append(
                {
                    'node_id': stable_node_id('source', source_path),
                    'source_path': source_path,
                    'binding': item['name'],
                    'reason': item['reason'],
                }
            )

    conditions_raw = request.get('conditions', []) or []
    if not isinstance(conditions_raw, list):
        raise ManifestError(['request.conditions must be a list.'])
    conditions = [str(value) for value in conditions_raw]

    required_context: list[dict[str, Any]] = []
    conditional_context: list[dict[str, Any]] = []
    external_references: list[dict[str, Any]] = []
    context_includes: list[dict[str, Any]] = []
    route_handoffs: list[dict[str, Any]] = []
    unresolved = {str(value) for value in request.get('unresolved_bindings', []) or []}

    for index_no, raw in enumerate(context_pack.get('required', []) or []):
        _apply_context_entry(
            raw=raw,
            location=f'{context_pack_path}.required[{index_no}]',
            requirement='required',
            condition=None,
            binding_names=binding_names,
            unresolved=unresolved,
            required_context=required_context,
            conditional_context=conditional_context,
            external_references=external_references,
            context_includes=context_includes,
            route_handoffs=route_handoffs,
            context_paths=context_paths,
            routes=routes,
        )

    conditional_map = context_pack.get('conditional', {}) or {}
    if not isinstance(conditional_map, dict):
        raise ManifestError([f'{context_pack_path} conditional must be a mapping.'])
    for condition in conditions:
        values = conditional_map.get(condition)
        if values is None:
            raise ManifestError([f'Unknown Context Pack condition for {route_id}: {condition}'])
        for index_no, raw in enumerate(values or []):
            _apply_context_entry(
                raw=raw,
                location=f'{context_pack_path}.conditional.{condition}[{index_no}]',
                requirement='conditional',
                condition=condition,
                binding_names=binding_names,
                unresolved=unresolved,
                required_context=required_context,
                conditional_context=conditional_context,
                external_references=external_references,
                context_includes=context_includes,
                route_handoffs=route_handoffs,
                context_paths=context_paths,
                routes=routes,
            )

    for raw in contract.get('required_inputs', []) or []:
        value = str(raw)
        if value not in binding_names:
            unresolved.add(value)

    project_facts = [_project_fact(raw, attempt) for raw in request.get('project_facts', []) or []]

    knowledge: list[dict[str, Any]] = []
    for raw in request.get('knowledge', []) or []:
        if isinstance(raw, str):
            source_path, reason = raw, 'required_context'
        elif isinstance(raw, dict):
            source_path = str(raw.get('source_path', '')).strip()
            reason = str(raw.get('reason', 'required_context'))
        else:
            raise ManifestError(['knowledge entries must be strings or mappings.'])
        if not source_path:
            raise ManifestError(['knowledge source_path must not be empty.'])
        knowledge.append(
            {
                'node_id': stable_node_id('knowledge', source_path),
                'source_path': source_path,
                'reason': reason,
            }
        )

    tools: list[dict[str, Any]] = []
    for raw in request.get('tools', []) or []:
        if not isinstance(raw, dict) or not raw.get('id'):
            raise ManifestError(['tools entries require id.'])
        tool_id = str(raw['id'])
        tools.append(
            {
                'node_id': stable_node_id('tool', tool_id),
                'id': tool_id,
                'reason': str(raw.get('reason', 'harness_contract')),
            }
        )

    excluded_context = [
        {
            'node_id': stable_node_id('source', str(raw)),
            'source_path': str(raw),
            'reason': 'excluded_context',
        }
        for raw in context_pack.get('excluded_by_default', []) or []
    ]

    skill_name = str(route.get('primary_skill', '')).strip()
    skill_path = f'.agents/skills/{skill_name}/SKILL.md'
    contract_id = str(contract.get('id', route_id))

    manifest: dict[str, Any] = {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'manifest': {'id': manifest_id, 'graph_kind': 'execution', 'attempt': attempt},
        'task': {'id': task_id, 'route': route_id, 'fingerprint': copy.deepcopy(fingerprint)},
        'policy': {
            'loaded': [
                {
                    'node_id': stable_node_id('policy', 'user-policy'),
                    'source_path': USER_POLICY_PATH.as_posix(),
                    'reason': 'user_policy',
                }
            ]
        },
        'project_facts': {'loaded': project_facts},
        'context': {
            'context_pack': {
                'node_id': stable_node_id('context_pack', str(context_pack.get('id'))),
                'source_path': context_pack_path.as_posix(),
            },
            'primary_skill': {
                'node_id': stable_node_id('skill', skill_name),
                'source_path': skill_path,
            },
            'bindings': bindings,
            'conditions_applied': conditions,
            'required_context': required_context,
            'conditional_context': conditional_context,
            'external_references': external_references,
            'context_includes': context_includes,
            'route_handoffs': route_handoffs,
            'source_files': source_files,
            'excluded_context': excluded_context,
        },
        'knowledge': {'loaded': knowledge},
        'harness': {
            'task_contract': {
                'node_id': stable_node_id('task_contract', contract_id),
                'source_path': contract_path.as_posix(),
            },
            'mutation_rules': _mutation_rules(contract_id, contract),
            'risk_level': {
                'node_id': stable_node_id('risk_level', str(contract.get('risk_level'))),
                'id': contract.get('risk_level'),
            },
            'quality_gates': _quality_gates(contract),
        },
        'tools': {'activated': tools},
        'execution': {
            'evidence': [],
            'unresolved_bindings': sorted(unresolved),
            'status': 'in_progress',
        },
        'graph_projection': {
            'contract': GRAPH_CONTRACT_PATH.as_posix(),
            'graph_kind': 'execution',
            'manifest_is_graph_instance': True,
            'stable_node_ids_required_when_emitted': True,
            'typed_edges_required': True,
            'provenance_required': True,
            'source_of_truth_remains_canonical_yaml': True,
        },
    }
    if previous_id is not None:
        manifest['manifest']['previous_manifest_id'] = previous_id
        manifest['manifest']['previous_attempt'] = previous_attempt
        manifest['execution']['previous_failure'] = previous_failure

    for evidence in request.get('evidence', []) or []:
        if not isinstance(evidence, dict):
            raise ManifestError(['evidence entries must be mappings.'])
        manifest = apply_gate_evidence(
            root,
            manifest,
            gate=str(evidence.get('gate', '')),
            status=str(evidence.get('status', '')),
            evidence_id=str(evidence.get('id', '')),
            reason=str(evidence.get('reason', '')),
            source_path=evidence.get('source_path'),
            remaining_validation=evidence.get('remaining_validation'),
            failure_reason=evidence.get('failure_reason'),
        )

    errors = validate_manifest(root, manifest)
    if errors:
        raise ManifestError(errors)
    return manifest


def _selection_keys(context: dict[str, Any]) -> dict[str, set[Any]]:
    return {
        'required_repository': {
            str(item.get('source_path'))
            for item in context.get('required_context', []) or []
            if isinstance(item, dict) and item.get('source_path')
        },
        'conditional_repository': {
            (str(item.get('condition')), str(item.get('source_path')))
            for item in context.get('conditional_context', []) or []
            if isinstance(item, dict) and item.get('source_path')
        },
        'external': {
            (
                str(item.get('requirement')),
                str(item.get('condition', '')),
                str(item.get('repository')),
                str(item.get('path')),
            )
            for item in context.get('external_references', []) or []
            if isinstance(item, dict)
        },
        'includes': {
            (
                str(item.get('requirement')),
                str(item.get('condition', '')),
                str(item.get('context_id')),
            )
            for item in context.get('context_includes', []) or []
            if isinstance(item, dict)
        },
        'handoffs': {
            (
                str(item.get('requirement')),
                str(item.get('condition', '')),
                str(item.get('route_id')),
            )
            for item in context.get('route_handoffs', []) or []
            if isinstance(item, dict)
        },
    }


def _validate_selected_entry(
    raw: Any,
    *,
    requirement: str,
    condition: str | None,
    binding_names: set[str],
    unresolved: set[str],
    selections: dict[str, set[Any]],
    context_paths: dict[str, str],
    routes: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ['Context Pack scalar entry is invalid under Typed Context v3.']
    item_type = str(raw.get('type', ''))
    if item_type not in CONTEXT_TYPES:
        return [f'Unsupported Context Pack type: {item_type}']

    if item_type == 'binding':
        name = str(raw.get('name', ''))
        if name not in binding_names and name not in unresolved:
            errors.append(f'Context Pack binding is neither resolved nor unresolved: {name}')
    elif item_type == 'repository_reference':
        path = str(raw.get('path', ''))
        if requirement == 'required':
            if path not in selections['required_repository']:
                errors.append(f'Missing required repository Context: {path}')
        elif (str(condition), path) not in selections['conditional_repository']:
            errors.append(f'Missing conditional repository Context for {condition}: {path}')
    elif item_type == 'external_reference':
        key = (requirement, str(condition or ''), str(raw.get('repository', '')), str(raw.get('path', '')))
        if key not in selections['external']:
            errors.append(f'Missing external Context reference: {key}')
    elif item_type == 'context_include':
        context_id = str(raw.get('context_id', ''))
        if context_id not in context_paths:
            errors.append(f'Context Pack includes unknown context: {context_id}')
        key = (requirement, str(condition or ''), context_id)
        if key not in selections['includes']:
            errors.append(f'Missing Context include: {key}')
    else:
        route_id = str(raw.get('route_id', ''))
        if route_id not in routes:
            errors.append(f'Context Pack hands off to unknown route: {route_id}')
        key = (requirement, str(condition or ''), route_id)
        if key not in selections['handoffs']:
            errors.append(f'Missing route handoff: {key}')
    return errors


def _validate_project_facts(manifest: dict[str, Any], attempt: int) -> list[str]:
    errors: list[str] = []
    seen_keys: set[str] = set()
    for item in manifest.get('project_facts', {}).get('loaded', []) or []:
        if not isinstance(item, dict):
            errors.append('project_facts entries must be mappings.')
            continue
        key = str(item.get('key', '')).strip()
        if not key:
            errors.append('Project Fact key is required.')
        elif key in seen_keys:
            errors.append(f'Duplicate Project Fact key: {key}')
        seen_keys.add(key)

        source_kind = str(item.get('source_kind', ''))
        if source_kind not in FACT_SOURCE_KINDS:
            errors.append(f'Unsupported Project Fact source_kind: {key}={source_kind}')
        if not str(item.get('source_path', '')).strip():
            errors.append(f'Project Fact source_path is required: {key}')
        if not str(item.get('revision', '')).strip():
            errors.append(f'Project Fact revision is required: {key}')

        observed = item.get('observed_at_attempt')
        if not isinstance(observed, int) or observed < 1 or observed > attempt:
            errors.append(f'Project Fact observed_at_attempt is invalid: {key}={observed}')

        freshness = item.get('freshness')
        if not isinstance(freshness, dict):
            errors.append(f'Project Fact freshness must be a mapping: {key}')
            continue
        status = freshness.get('status')
        checked = freshness.get('checked_at_attempt')
        if status not in FACT_FRESHNESS_STATUSES:
            errors.append(f'Unsupported Project Fact freshness status: {key}={status}')
        if not isinstance(checked, int) or checked < 1 or checked > attempt:
            errors.append(f'Project Fact checked_at_attempt is invalid: {key}={checked}')
        if isinstance(observed, int) and isinstance(checked, int) and checked < observed:
            errors.append(f'Project Fact freshness check predates observation: {key}')
        if status == 'current' and checked != attempt:
            errors.append(
                f'Current Project Fact must be checked in manifest attempt {attempt}: {key} checked_at_attempt={checked}'
            )
    return errors


def validate_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    index = load_yaml(root / INDEX_PATH)
    graph_contract = load_yaml(root / GRAPH_CONTRACT_PATH)
    quality_contract = load_yaml(root / QUALITY_GATES_PATH)
    routes = _route_map(index)
    context_paths = _context_pack_map(root)

    if manifest.get('schema_version') != MANIFEST_SCHEMA_VERSION:
        errors.append(f'Context Manifest schema_version must be {MANIFEST_SCHEMA_VERSION}.')

    meta = manifest.get('manifest', {})
    if not isinstance(meta, dict):
        return ['manifest must be a mapping.']
    manifest_id = str(meta.get('id', '')).strip()
    if not manifest_id:
        errors.append('manifest.id is required.')
    if meta.get('graph_kind') != 'execution':
        errors.append('manifest.graph_kind must be execution.')
    attempt = meta.get('attempt')
    if not isinstance(attempt, int) or attempt < 1:
        errors.append('manifest.attempt must be an integer >= 1.')
        attempt = 1
    elif attempt == 1:
        if meta.get('previous_manifest_id') or meta.get('previous_attempt') is not None:
            errors.append('Attempt 1 must not reference a previous manifest.')
    else:
        if not meta.get('previous_manifest_id'):
            errors.append('Retry manifest requires previous_manifest_id.')
        if meta.get('previous_attempt') != attempt - 1:
            errors.append('Retry manifest previous_attempt must equal attempt - 1.')

    task = manifest.get('task', {})
    if not isinstance(task, dict):
        return errors + ['task must be a mapping.']
    task_id = str(task.get('id', '')).strip()
    route_id = str(task.get('route', '')).strip()
    if not task_id:
        errors.append('task.id is required.')

    route = routes.get(route_id)
    if route is None:
        return errors + [f'Manifest references unknown route: {route_id}']
    errors.extend(_fingerprint_errors(index, route, task.get('fingerprint', {})))

    pack_path = str(route.get('context_pack', ''))
    contract_path = str(route.get('task_contract', ''))
    pack = load_yaml(root / Path(pack_path))
    contract = load_yaml(root / Path(contract_path))

    policy_loaded = manifest.get('policy', {}).get('loaded', []) or []
    if not any(
        isinstance(item, dict) and item.get('source_path') == USER_POLICY_PATH.as_posix()
        for item in policy_loaded
    ):
        errors.append('Context Manifest must record .ai/user-policy.yaml.')

    context = manifest.get('context', {})
    if not isinstance(context, dict):
        return errors + ['context must be a mapping.']
    if context.get('context_pack', {}).get('source_path') != pack_path:
        errors.append('Context Pack binding does not match canonical route.')
    expected_skill = f".agents/skills/{route.get('primary_skill')}/SKILL.md"
    if context.get('primary_skill', {}).get('source_path') != expected_skill:
        errors.append('Primary Skill binding does not match canonical route.')

    harness = manifest.get('harness', {})
    if not isinstance(harness, dict):
        return errors + ['harness must be a mapping.']
    if harness.get('task_contract', {}).get('source_path') != contract_path:
        errors.append('Task Contract binding does not match canonical route.')
    if harness.get('risk_level', {}).get('id') != contract.get('risk_level'):
        errors.append('Risk level does not match selected Task Contract.')

    expected_mutations = {
        ('allow', str(rule)) for rule in contract.get('allowed_mutations', []) or []
    } | {
        ('prohibit', str(rule)) for rule in contract.get('prohibited_mutations', []) or []
    }
    actual_mutations = {
        (str(item.get('effect')), str(item.get('id')))
        for item in harness.get('mutation_rules', []) or []
        if isinstance(item, dict)
    }
    missing_mutations = expected_mutations - actual_mutations
    if missing_mutations:
        errors.append(f'Manifest is missing Task Contract mutation rules: {sorted(missing_mutations)}')
    for effect, _ in actual_mutations:
        if effect not in MUTATION_EFFECTS:
            errors.append(f'Unsupported mutation effect: {effect}')

    allowed_gate_statuses = set(quality_contract.get('result_statuses', []) or [])
    known_gates = set((quality_contract.get('gates', {}) or {}).keys())
    actual_gates: dict[str, dict[str, Any]] = {}
    for gate in harness.get('quality_gates', []) or []:
        if not isinstance(gate, dict) or not gate.get('id'):
            errors.append('quality_gates entries require id.')
            continue
        gate_id = str(gate['id'])
        actual_gates[gate_id] = gate
        if gate_id not in known_gates:
            errors.append(f'Unknown quality gate: {gate_id}')
        if gate.get('requirement') not in GATE_REQUIREMENTS:
            errors.append(f"Unsupported gate requirement: {gate_id}={gate.get('requirement')}")
        if gate.get('status') is not None and gate.get('status') not in allowed_gate_statuses:
            errors.append(f"Unsupported gate status: {gate_id}={gate.get('status')}")

    for key, requirement in (
        ('required_quality_gates', 'required'),
        ('conditional_quality_gates', 'conditional'),
    ):
        for raw in contract.get(key, []) or []:
            gate_id = str(raw)
            gate = actual_gates.get(gate_id)
            if gate is None or gate.get('requirement') != requirement:
                errors.append(f'Missing {requirement} quality gate: {gate_id}')

    bindings = context.get('bindings', []) or []
    binding_names = {
        str(item.get('name'))
        for item in bindings
        if isinstance(item, dict) and item.get('name')
    }
    unresolved = {
        str(value)
        for value in manifest.get('execution', {}).get('unresolved_bindings', []) or []
    }
    selections = _selection_keys(context)

    for raw in pack.get('required', []) or []:
        errors.extend(
            _validate_selected_entry(
                raw,
                requirement='required',
                condition=None,
                binding_names=binding_names,
                unresolved=unresolved,
                selections=selections,
                context_paths=context_paths,
                routes=routes,
            )
        )

    conditional_map = pack.get('conditional', {}) or {}
    for condition in context.get('conditions_applied', []) or []:
        if condition not in conditional_map:
            errors.append(f'Unknown applied Context Pack condition: {condition}')
            continue
        for raw in conditional_map.get(condition, []) or []:
            errors.extend(
                _validate_selected_entry(
                    raw,
                    requirement='conditional',
                    condition=str(condition),
                    binding_names=binding_names,
                    unresolved=unresolved,
                    selections=selections,
                    context_paths=context_paths,
                    routes=routes,
                )
            )

    for raw in contract.get('required_inputs', []) or []:
        value = str(raw)
        if value not in binding_names and value not in unresolved:
            errors.append(f'Task Contract input is neither resolved nor unresolved: {value}')

    errors.extend(_validate_project_facts(manifest, attempt))

    selected_paths = _selected_paths(manifest)
    for item in context.get('excluded_context', []) or []:
        if isinstance(item, dict):
            source_path = str(item.get('source_path', ''))
            if source_path and source_path in selected_paths:
                errors.append(f'Excluded Context was loaded: {source_path}')

    allowed_reasons = set(graph_contract.get('provenance', {}).get('reasons', []) or [])
    provenance_lists = [
        policy_loaded,
        manifest.get('project_facts', {}).get('loaded', []),
        context.get('bindings', []),
        context.get('required_context', []),
        context.get('conditional_context', []),
        context.get('external_references', []),
        context.get('context_includes', []),
        context.get('route_handoffs', []),
        context.get('source_files', []),
        context.get('excluded_context', []),
        manifest.get('knowledge', {}).get('loaded', []),
        manifest.get('tools', {}).get('activated', []),
        manifest.get('execution', {}).get('evidence', []),
    ]
    for items in provenance_lists:
        local_ids: list[str] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            reason = item.get('reason')
            if not reason:
                errors.append(f"Missing provenance reason on item: {item.get('node_id') or item}")
            elif reason not in allowed_reasons:
                errors.append(f'Unsupported provenance reason: {reason}')
            if item.get('node_id'):
                local_ids.append(str(item['node_id']))
        if len(local_ids) != len(set(local_ids)):
            errors.append('Duplicate stable node_id within one manifest section.')

    execution = manifest.get('execution', {})
    evidence = execution.get('evidence', []) or []
    evidence_ids: set[str] = set()
    evidence_by_gate: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            errors.append('evidence entries must be mappings.')
            continue
        evidence_id = str(item.get('id', '')).strip()
        gate_id = str(item.get('gate', '')).strip()
        status = item.get('status')
        if not evidence_id:
            errors.append('Evidence id is required.')
        elif evidence_id in evidence_ids:
            errors.append(f'Duplicate evidence id: {evidence_id}')
        evidence_ids.add(evidence_id)
        if status not in allowed_gate_statuses:
            errors.append(f'Unsupported evidence status: {evidence_id}={status}')
        if not gate_id or gate_id not in actual_gates:
            errors.append(f'Evidence references unselected gate: {evidence_id}->{gate_id}')
        else:
            evidence_by_gate.setdefault(gate_id, []).append(item)
        if status == 'unavailable' and not item.get('remaining_validation'):
            errors.append(f'Unavailable evidence requires remaining_validation: {evidence_id}')

    for gate_id, gate in actual_gates.items():
        status = gate.get('status')
        if status is None:
            continue
        matching = evidence_by_gate.get(gate_id, [])
        if not any(item.get('status') == status for item in matching):
            errors.append(f'Gate status lacks matching evidence: {gate_id}={status}')

    expected_status = derive_execution_status(manifest)
    actual_status = execution.get('status')
    if actual_status not in EXECUTION_STATUSES:
        errors.append(f'Unsupported execution.status: {actual_status}')
    elif actual_status != expected_status:
        errors.append(
            f'execution.status is inconsistent with selected gates: {actual_status} != {expected_status}'
        )
    if actual_status == 'failed' and not execution.get('failure_reason'):
        errors.append('Failed execution requires failure_reason.')
    if actual_status != 'failed' and execution.get('failure_reason'):
        errors.append('Non-failed execution must not keep stale failure_reason.')

    projection = manifest.get('graph_projection', {})
    if projection.get('contract') != GRAPH_CONTRACT_PATH.as_posix():
        errors.append('graph_projection.contract must reference .ai/graph-contract.yaml.')
    if projection.get('graph_kind') != 'execution':
        errors.append('graph_projection.graph_kind must be execution.')
    for key in (
        'manifest_is_graph_instance',
        'stable_node_ids_required_when_emitted',
        'typed_edges_required',
        'provenance_required',
        'source_of_truth_remains_canonical_yaml',
    ):
        if projection.get(key) is not True:
            errors.append(f'graph_projection.{key} must be true.')
    return errors


def apply_gate_evidence(
    root: Path,
    manifest: dict[str, Any],
    *,
    gate: str,
    status: str,
    evidence_id: str,
    reason: str,
    source_path: str | None = None,
    remaining_validation: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(manifest)
    quality = load_yaml(root / QUALITY_GATES_PATH)
    allowed_statuses = set(quality.get('result_statuses', []) or [])
    errors: list[str] = []
    if status not in allowed_statuses:
        errors.append(f'Unsupported gate status: {status}')
    if not gate:
        errors.append('gate is required.')
    if not evidence_id:
        errors.append('evidence_id is required.')
    if not reason:
        errors.append('evidence reason is required.')
    if status == 'unavailable' and not remaining_validation:
        errors.append('unavailable evidence requires remaining_validation.')
    if errors:
        raise ManifestError(errors)

    gates = result.get('harness', {}).get('quality_gates', []) or []
    selected_gate = next(
        (
            item for item in gates
            if isinstance(item, dict) and str(item.get('id')) == gate
        ),
        None,
    )
    if selected_gate is None:
        raise ManifestError([f'Gate is not selected by this manifest: {gate}'])
    selected_gate['status'] = status

    item: dict[str, Any] = {
        'node_id': stable_node_id('evidence', f"{result['manifest']['id']}:{evidence_id}"),
        'id': evidence_id,
        'gate': gate,
        'status': status,
        'reason': reason,
    }
    if source_path:
        item['source_path'] = str(source_path)
    if remaining_validation:
        item['remaining_validation'] = str(remaining_validation)

    evidence = result.setdefault('execution', {}).setdefault('evidence', [])
    evidence[:] = [
        existing for existing in evidence
        if not (isinstance(existing, dict) and existing.get('id') == evidence_id)
    ]
    evidence.append(item)

    result['execution']['status'] = derive_execution_status(result)
    if result['execution']['status'] == 'failed':
        result['execution']['failure_reason'] = str(
            failure_reason or result['execution'].get('failure_reason') or f'{gate}_failed'
        )
    else:
        result['execution'].pop('failure_reason', None)
    return result


def project_execution_graph(
    root: Path, manifest: dict[str, Any], manifest_source_path: str
) -> dict[str, Any]:
    errors = validate_manifest(root, manifest)
    if errors:
        raise ManifestError(errors)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(
        node_id: str, node_type: str, label: str, source_path: str, reason: str
    ) -> None:
        nodes.setdefault(
            node_id,
            {
                'id': node_id,
                'type': node_type,
                'label': label,
                'provenance': {'source_path': source_path, 'reason': reason},
            },
        )

    def add_edge(source: str, target: str, edge_type: str, reason: str) -> None:
        key = (source, target, edge_type)
        if any((edge['source'], edge['target'], edge['type']) == key for edge in edges):
            return
        edges.append({'source': source, 'target': target, 'type': edge_type, 'reason': reason})

    meta = manifest['manifest']
    task = manifest['task']
    context = manifest['context']
    harness = manifest['harness']
    execution = manifest['execution']

    attempt_id = stable_node_id('attempt', str(meta['id']))
    task_id = stable_node_id('task', str(task['id']))
    fingerprint_id = stable_node_id('task_fingerprint', str(task['id']))
    route_node_id = stable_node_id('route', str(task['route']))

    add_node(attempt_id, 'attempt', f"Attempt {meta['attempt']}", manifest_source_path, 'runtime_evidence')
    add_node(task_id, 'task', str(task['id']), manifest_source_path, 'runtime_evidence')
    add_node(fingerprint_id, 'task_fingerprint', 'Task Fingerprint', manifest_source_path, 'runtime_evidence')
    add_node(route_node_id, 'route', str(task['route']), INDEX_PATH.as_posix(), 'canonical_binding')
    add_edge(attempt_id, task_id, 'depends_on', 'runtime_evidence')
    add_edge(task_id, fingerprint_id, 'classifies_as', 'runtime_evidence')
    add_edge(fingerprint_id, route_node_id, 'selects', 'canonical_binding')

    pack = context['context_pack']
    add_node(pack['node_id'], 'context_pack', str(task['route']), pack['source_path'], 'canonical_binding')
    add_edge(route_node_id, pack['node_id'], 'selects', 'canonical_binding')

    skill = context['primary_skill']
    add_node(skill['node_id'], 'skill', skill['node_id'].split(':', 1)[-1], skill['source_path'], 'canonical_binding')
    add_edge(route_node_id, skill['node_id'], 'uses_skill', 'canonical_binding')

    contract = harness['task_contract']
    add_node(contract['node_id'], 'task_contract', contract['node_id'].split(':', 1)[-1], contract['source_path'], 'harness_contract')
    add_edge(route_node_id, contract['node_id'], 'selects', 'harness_contract')

    for item in manifest.get('policy', {}).get('loaded', []) or []:
        add_node(item['node_id'], 'policy', item['node_id'].split(':', 1)[-1], item['source_path'], item['reason'])
        add_edge(task_id, item['node_id'], 'applies_policy', item['reason'])

    for item in manifest.get('project_facts', {}).get('loaded', []) or []:
        add_node(item['node_id'], 'project_fact', str(item['key']), item['source_path'], item['reason'])
        add_edge(task_id, item['node_id'], 'requires', item['reason'])

    for key, edge_type in (
        ('required_context', 'requires'),
        ('conditional_context', 'conditionally_requires'),
        ('source_files', 'reads_source'),
        ('excluded_context', 'excludes'),
    ):
        for item in context.get(key, []) or []:
            add_node(item['node_id'], 'source', item['source_path'], item['source_path'], item['reason'])
            add_edge(pack['node_id'], item['node_id'], edge_type, item['reason'])

    for item in context.get('external_references', []) or []:
        source_path = f"{item['repository']}/{item['path']}"
        add_node(item['node_id'], 'external_reference', source_path, source_path, item['reason'])
        edge_type = 'requires' if item['requirement'] == 'required' else 'conditionally_requires'
        add_edge(pack['node_id'], item['node_id'], edge_type, item['reason'])

    for item in context.get('context_includes', []) or []:
        add_node(item['node_id'], 'context_pack', item['context_id'], item['source_path'], item['reason'])
        add_edge(pack['node_id'], item['node_id'], 'includes_context', item['reason'])

    for item in context.get('route_handoffs', []) or []:
        add_node(item['node_id'], 'route', item['route_id'], INDEX_PATH.as_posix(), item['reason'])
        add_edge(route_node_id, item['node_id'], 'hands-off-to', item['reason'])

    for item in manifest.get('knowledge', {}).get('loaded', []) or []:
        add_node(item['node_id'], 'knowledge', item['source_path'], item['source_path'], item['reason'])
        add_edge(pack['node_id'], item['node_id'], 'uses_knowledge', item['reason'])

    risk = harness['risk_level']
    add_node(risk['node_id'], 'risk_level', str(risk['id']), RISK_LEVELS_PATH.as_posix(), 'harness_contract')
    add_edge(contract['node_id'], risk['node_id'], 'depends_on', 'harness_contract')

    for item in harness.get('mutation_rules', []) or []:
        add_node(item['node_id'], 'mutation_rule', str(item['id']), contract['source_path'], 'harness_contract')
        edge_type = 'allows_mutation' if item['effect'] == 'allow' else 'prohibits_mutation'
        add_edge(contract['node_id'], item['node_id'], edge_type, 'harness_contract')

    for gate in harness.get('quality_gates', []) or []:
        add_node(gate['node_id'], 'quality_gate', str(gate['id']), QUALITY_GATES_PATH.as_posix(), 'quality_gate')
        edge_type = 'requires_gate' if gate['requirement'] == 'required' else 'conditionally_requires'
        add_edge(contract['node_id'], gate['node_id'], edge_type, 'quality_gate')

    for item in manifest.get('tools', {}).get('activated', []) or []:
        add_node(item['node_id'], 'tool', str(item['id']), MCP_ACTIVATION_PATH.as_posix(), item['reason'])
        add_edge(attempt_id, item['node_id'], 'uses_tool', item['reason'])

    for item in execution.get('evidence', []) or []:
        source_path = item.get('source_path') or manifest_source_path
        add_node(item['node_id'], 'evidence', str(item['id']), source_path, item['reason'])
        add_edge(attempt_id, item['node_id'], 'produces_evidence', item['reason'])
        add_edge(item['node_id'], stable_node_id('quality_gate', str(item['gate'])), 'validates', 'quality_gate')

    previous_id = meta.get('previous_manifest_id')
    if previous_id:
        previous_node = stable_node_id('attempt', str(previous_id))
        add_node(previous_node, 'attempt', f"Previous Attempt {meta.get('previous_attempt')}", manifest_source_path, 'runtime_evidence')
        add_edge(previous_node, attempt_id, 'retries_as', 'runtime_evidence')

    return {
        'schema_version': GRAPH_SCHEMA_VERSION,
        'graph_kind': 'execution',
        'manifest_id': meta['id'],
        'root_node': attempt_id,
        'metadata': {
            'task_id': task['id'],
            'route': task['route'],
            'attempt': meta['attempt'],
            'status': execution.get('status'),
        },
        'nodes': list(nodes.values()),
        'edges': edges,
    }
