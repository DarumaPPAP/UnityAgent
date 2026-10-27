import json
import tempfile
import unittest
from pathlib import Path


class ModelUsageTests(unittest.TestCase):
    def observe(self, events):
        from unityagent.runtime.telemetry.model_usage import observe_codex_usage
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            path.write_text('\n'.join(json.dumps(event) for event in events), encoding='utf-8')
            return observe_codex_usage(path, model='configured-model', reasoning_effort='high')

    def test_missing_usage_is_null_and_does_not_copy_free_text(self):
        result = self.observe([{'type': 'item.completed', 'text': 'private source prompt'}])
        self.assertIsNone(result['input_tokens'])
        self.assertIsNone(result['output_tokens'])
        self.assertIsNone(result['model_revision'])
        self.assertNotIn('private', json.dumps(result))

    def test_completed_turn_usage_sums_cache_as_subset_of_input(self):
        result = self.observe([{'type': 'turn.completed', 'usage': {
            'input_tokens': 20, 'cached_input_tokens': 10, 'output_tokens': 3}},
            {'type': 'turn.completed', 'usage': {
                'input_tokens': 5, 'cached_input_tokens': 2, 'output_tokens': 4}}])
        self.assertEqual(result['input_tokens'], 25)
        self.assertEqual(result['cached_input_tokens'], 12)
        self.assertEqual(result['output_tokens'], 7)
        self.assertEqual(result['completed_turns'], 2)
        self.assertEqual(result['usage_source'], 'codex.turn.completed.usage')

    def test_partial_malformed_or_boolean_usage_is_not_reported_as_complete(self):
        for usage in ({'input_tokens': True, 'output_tokens': 2},
                      {'input_tokens': -1, 'output_tokens': 2},
                      {'input_tokens': 2, 'cached_input_tokens': 3, 'output_tokens': 2},
                      {'input_tokens': 2}):
            with self.subTest(usage=usage):
                result = self.observe([{'type': 'turn.completed', 'usage': usage}])
                self.assertIsNone(result['input_tokens'])
                self.assertIsNone(result['output_tokens'])

    def test_missing_cache_does_not_invent_zero_or_discard_other_usage(self):
        result = self.observe([{'type': 'turn.completed', 'usage': {
            'input_tokens': 20, 'output_tokens': 3}}])
        self.assertEqual(result['input_tokens'], 20)
        self.assertIsNone(result['cached_input_tokens'])
