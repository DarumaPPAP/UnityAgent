"""Codexの構造化usageだけを投影し、Source・Prompt・自由記述を保存しない。"""
import json


def observe_codex_usage(events_path, *, model, reasoning_effort):
    result = {'usage_source': None, 'unit': 'tokens', 'scope': 'all_observed_completed_turns', 'configured_model': model,
              'model_revision': None, 'reasoning_effort': reasoning_effort,
              'completed_turns': 0, 'input_tokens': None,
              'cached_input_tokens': None, 'output_tokens': None}
    totals = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0}
    complete, cache_complete = True, True
    try:
        with events_path.open(encoding='utf-8') as events:
            for line in events:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    complete = False
                    continue
                if not isinstance(event, dict) or event.get('type') != 'turn.completed':
                    continue
                result['completed_turns'] += 1
                usage = event.get('usage')
                if not isinstance(usage, dict):
                    complete = False
                    continue
                if any(type(usage.get(key)) is not int or usage[key] < 0
                       for key in ('input_tokens', 'output_tokens')):
                    complete = False
                    continue
                cached = usage.get('cached_input_tokens')
                if cached is None:
                    cache_complete = False
                elif type(cached) is not int or not 0 <= cached <= usage['input_tokens']:
                    complete = False
                    continue
                for key in ('input_tokens', 'output_tokens'):
                    totals[key] += usage[key]
                if cached is not None:
                    totals['cached_input_tokens'] += cached
    except (OSError, UnicodeError):
        complete = False
    if result['completed_turns'] and complete:
        result.update(totals)
        result['usage_source'] = 'codex.turn.completed.usage'
        if not cache_complete:
            result['cached_input_tokens'] = None
    return result
