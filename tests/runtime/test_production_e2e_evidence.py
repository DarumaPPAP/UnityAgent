import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[2]/'tools/production_e2e/collect_evidence.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class ProductionEvidenceTests(unittest.TestCase):
    def test_missing_all_gates_remains_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            result = collector.collect(root, source_revision='revision', artifact_hash='hash')
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(all(v['status']=='BLOCKED_NOT_RUN' for v in result['gates'].values()))

    def test_fixture_success_wrong_revision_and_unhashed_files_cannot_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'render_capture.json'
            value = {'gate':'render_capture','status':'passed','source_revision':'revision',
                     'source_sha256':'hash','limitation':'Editor fixture only'}
            for update in ({}, {'source_revision':'stale'}, {'limitation':None, 'evidence_level':'production_runtime'}):
                path.write_text(json.dumps({**value, **update}))
                result = collector.collect(root, source_revision='revision', artifact_hash='hash')
                self.assertEqual(result['gates']['render_capture']['status'], 'failed')
                self.assertEqual(result['status'], 'blocked')
