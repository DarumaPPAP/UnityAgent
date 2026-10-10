from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import yaml

from unityagent.runtime.reference_implementation.catalog_import_gate import CatalogImportError, build_import_plan
from tests.runtime import test_hub_source_validation as source_tests

ROOT = Path(__file__).resolve().parents[2]


class HubPathMigrationTests(unittest.TestCase):
    def plan(self, path_prefix: str) -> dict:
        payload = yaml.safe_load((ROOT / 'tests/runtime/fixtures/hub-production-specialists-v3.yaml').read_bytes())
        for entry in payload['specialists']:
            entry['manifest_ref'] = path_prefix + entry['manifest_ref']
            execution = entry['manifest']['execution']
            if execution['kind'] == 'reasoning':
                for key in ('instructions_ref', 'output_contract_ref'):
                    execution[key] = path_prefix + execution[key]
        data = yaml.safe_dump(payload, sort_keys=False).encode()
        return build_import_plan(data, source_ref='migration-fixture', expected_sha256=hashlib.sha256(data).hexdigest(), current_catalog_bytes=(ROOT / 'src/unityagent/runtime/reference_implementation/subagent-catalog.yaml').read_bytes())

    def test_new_hub_manifest_paths_are_read_only_noop(self):
        plan = self.plan('Hub/')
        self.assertEqual(plan['status'], 'no_op')
        self.assertFalse(plan['apply']['catalog_write_performed'])
        self.assertFalse(plan['apply']['apply_allowed'])

    def test_unknown_path_prefix_is_rejected(self):
        for prefix in ('Other/', '../', '/Hub/', 'Hub/../'):
            with self.subTest(prefix=prefix), self.assertRaises(CatalogImportError):
                self.plan(prefix)


class HubExporterMigrationTests(unittest.TestCase):
    setUp = source_tests.HubSourceValidationTests.setUp
    git = source_tests.HubSourceValidationTests.git
    validate = source_tests.HubSourceValidationTests.validate
    def test_development_new_exporter_does_not_change_old_pinned_source(self):
        old = self.hub / 'Tests/Hub/export_agent_snapshot.py'
        new = self.hub / 'Hub/Tools/export_snapshot.py'
        new.parent.mkdir(parents=True)
        old.rename(new)
        self.git('add', '.')
        self.git('commit', '-qm', 'move static exporter')
        new_plan = self.validate('development')
        old_plan = self.validate('pinned')
        self.assertEqual(new_plan['status'], 'no_op')
        self.assertTrue(new_plan['source']['ref'].endswith('/Hub/Tools/export_snapshot.py'))
        self.assertTrue(old_plan['source']['ref'].endswith('/Tests/Hub/export_agent_snapshot.py'))
        self.assertFalse(new_plan['apply']['catalog_write_performed'])

    def test_unknown_locked_exporter_is_rejected(self):
        import json
        lock = json.loads(self.lock.read_text())
        lock['hub']['snapshot_exporter'] = '../export.py'
        self.lock.write_text(json.dumps(lock))
        with self.assertRaises(ValueError):
            self.validate('pinned')
