"""準備済みCore Handoffから、原Projectへ書けないCodexRunner提案を作る。"""
import json
import hashlib
from pathlib import Path
import tempfile

from unityagent.resources import resource_root
from unityagent.context.budget.budget_runtime import estimate_tokens, load_contract
from unityagent.runtime.contracts.runtime_handoff import validate_runtime_handoff
from unityagent.runtime.guardrails.csharp_patch import validate_csharp_patch
from unityagent.runtime.runner.codex import codex_runner


def propose_patch(handoff, manifest, *, intent, source, original_project, model, command_prefix=None,
                  timeout_seconds=120.0, reasoning_effort='high', cancel_event=None, telemetry_out=None):
    validate_runtime_handoff(handoff)
    if (handoff['route_id'] != 'csharp-local-fix' or not model
            or any(request['capability'] != 'source.read' for request in handoff['capability_requests'])):
        raise ValueError('Bounded source proposal needs a read-only C# Handoff and an explicit model')
    view = manifest['materialized_context']
    if (view['context_id'] != handoff['context_id']
            or view['context_fingerprint']['value'] != handoff['context_fingerprint']):
        raise ValueError('C# proposal Context binding differs')
    budget = manifest['budget_report']
    limits = load_contract(resource_root())['profiles'][budget['profile']]
    selected_bytes = budget['selected_utf8_bytes'] + len(source.encode('utf-8'))
    if (budget['decision'] != 'within_budget' or budget['selected_artifacts'] + 1 > limits['retrieval']['max_artifacts']
            or selected_bytes > limits['retrieval']['max_selected_utf8_bytes']
            or estimate_tokens(selected_bytes) > limits['context']['soft_estimated_tokens']):
        raise ValueError('C# proposal source exceeds the existing Context budget')
    selected = {}
    def collect(value):
        if isinstance(value, dict):
            if 'resolved_path' in value and 'selected_utf8_bytes' in value:
                path = (resource_root() / value['resolved_path']).resolve()
                if resource_root().resolve() not in path.parents:
                    raise ValueError('Selected C# Context source escapes resources')
                content = path.read_bytes()
                if 'sha256:' + hashlib.sha256(content).hexdigest() != value['revision']:
                    raise ValueError('Selected C# Context source revision changed')
                selected[value['resolved_path']] = content.decode('utf-8')
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(view['selected_refs'])
    schema = json.loads((resource_root() / 'src/unityagent/runtime/contracts/csharp-patch.schema.json').read_text(encoding='utf-8'))
    context = {'context_id': handoff['context_id'], 'context_fingerprint': handoff['context_fingerprint'],
               'intent': intent, 'source': source, 'required_context': selected}
    with tempfile.TemporaryDirectory(prefix='unityagent-csharp-proposal-') as temporary:
        workspace = Path(temporary) / 'workspace'
        workspace.mkdir()
        (workspace / 'patch-context.json').write_text(json.dumps(context, ensure_ascii=False), encoding='utf-8')
        schema_path = workspace / 'output-schema.json'
        schema_path.write_text(json.dumps(schema), encoding='utf-8')
        prompt = ('Propose exactly one replacement of an existing method return expression. '
                  'Do not change declarations, public API, serialized fields, namespace, type names, or other files. '
                  'Do not mutate the workspace. Return the bounded patch and the exact supplied Context identity.\n'
                  + json.dumps(context, ensure_ascii=False))
        request = {'schema_version': '1.0', 'run_id': handoff['run_id'], 'step_id': handoff['step_id'],
            'action_id': handoff['action_id'], 'workspace_root': str(workspace), 'original_workspace_root': str(original_project),
            'prompt': prompt, 'execution': {'profile': 'generic_planning', 'work_kind': 'analysis',
                'reasoning': True, 'mutation_authorized': False}, 'mutation_scope': {},
            'output_schema_path': str(schema_path), 'profile_id': 'unityagent_core', 'capability': 'source.patch.propose',
            'source_context_id': handoff['context_id'], 'source_context_fingerprint': handoff['context_fingerprint'],
            'tool_identity': {'provider': 'openai', 'model': model, 'model_revision': 'not_observed'},
            'definition_fingerprint': handoff['definition_fingerprint']}
        output = Path(temporary) / 'output'
        execution = codex_runner.execute(request, output,
            command_prefix=command_prefix if command_prefix is not None else codex_runner._command_prefix(None),
            timeout_seconds=timeout_seconds, reasoning_effort=reasoning_effort, cancel_event=cancel_event)
        if telemetry_out is not None:
            from unityagent.runtime.telemetry.model_usage import observe_codex_usage
            telemetry_out.update({'model_usage': observe_codex_usage(output / 'codex-events.jsonl',
                model=model, reasoning_effort=reasoning_effort),
                'context': {'selected_utf8_bytes': selected_bytes,
                    'selected_artifacts': budget['selected_artifacts'] + 1,
                    'estimated_tokens': estimate_tokens(selected_bytes),
                    'prompt_utf8_bytes': len(prompt.encode('utf-8')),
                    'prompt_estimated_tokens': estimate_tokens(len(prompt.encode('utf-8')))}})
        if execution['status'] != 'passed':
            raise ValueError('C# proposal model execution did not pass its Runtime contract')
        patch = json.loads((output / 'response.json').read_text(encoding='utf-8'))
    if (patch['source_context_id'] != handoff['context_id']
            or patch['source_context_fingerprint'] != handoff['context_fingerprint']):
        raise ValueError('C# proposal output Context binding differs')
    validate_csharp_patch(source, patch['expected_text'], patch['replacement_text'])
    # 自由記述にはSourceやPromptが引用され得るため永続化しない。
    patch['summary'] = 'Replace one existing method return expression'
    return patch
