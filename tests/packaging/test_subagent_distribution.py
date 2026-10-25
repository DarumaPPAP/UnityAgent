"""同居正本がReleaseとPython配布へ到達することを検証する。"""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class SubagentDistributionTests(unittest.TestCase):
    def test_resource_build_contains_all_manifest_execution_refs(self):
        copy = runpy.run_path(str(ROOT / 'setup.py'))['copy_resources']
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'resources'
            copy(destination)
            registry_path = destination / 'subagent/registry.yaml'
            self.assertTrue(registry_path.is_file(), 'SubAgent registry missing from Python distribution')
            self.assertFalse((destination / 'subagent/artist_subagent/tools/host').exists())
            self.assertTrue((destination / 'subagent/artist_subagent/contracts/backend-surface-contract.yaml').is_file())
            hashes = json.loads((destination / 'resource-manifest.json').read_text())
            registry = yaml.safe_load(registry_path.read_text())
            for entry in registry['entries']:
                manifest_path = destination / entry['manifest']
                manifest = yaml.safe_load(manifest_path.read_text())
                refs = [entry['manifest']]
                refs += [manifest['execution'][key] for key in ('instructions_ref', 'output_contract_ref')
                         if key in manifest['execution']]
                for ref in refs:
                    self.assertEqual((ROOT / ref).read_bytes(), (destination / ref).read_bytes())
                    self.assertEqual(hashes[ref], hashlib.sha256((destination / ref).read_bytes()).hexdigest())

    def test_distribution_gate_does_not_require_or_publish_host(self):
        source = (ROOT / 'tools/validate_artist_product_identity.py').read_text(encoding='utf-8')
        self.assertNotIn('tools/host/', source)
        validation = (ROOT / '.github/workflows/validate-agent-contracts.yml').read_text(encoding='utf-8')
        self.assertNotIn('tools/host/', validation)
        self.assertIn('AuthorityClientTests.csproj', validation)

    def test_release_uses_same_checkout_for_artist_and_catalog(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/release-tag.yml').read_text())
        steps = workflow['jobs']['release']['steps']
        checkouts = [step for step in steps if str(step.get('uses', '')).startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 1, 'Release must not fetch another repository')
        scripts = '\n'.join(step.get('run', '') for step in steps)
        self.assertNotIn('.release-sources/UnitySubAgentHub', scripts)
        self.assertNotIn('tools/host/', scripts)
        self.assertNotIn('ArtistSubAgent-host-', scripts)
        self.assertIn('subagent/artist_subagent/tools/editor', scripts)
        self.assertIn('subagent/tools/export_snapshot.py', scripts)
        self.assertIn('unity_agent_commit', scripts)


if __name__ == '__main__':
    unittest.main()
