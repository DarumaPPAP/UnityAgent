import tempfile
import unittest
from pathlib import Path
from unityagent.runtime.guardrails.staged_assets import StagedAssets


class StagedAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        (self.project / 'Assets').mkdir(parents=True)
        self.asset = self.project / 'Assets/Rock.fbx'
        self.asset.write_bytes(b'old')
        self.meta = self.project / 'Assets/Rock.fbx.meta'
        self.meta.write_text('fileFormatVersion: 2\nguid: abcdef1234567890abcdef1234567890\n')
        self.approvals = []
        self.stage = StagedAssets(self.project, self.root / 'state', 'stage-test',
                                  check_approval=lambda digest, phase: self.approvals.append((digest, phase)))

    def prepare(self):
        return self.stage.prepare({'Assets/Rock.fbx': b'new'}, approval_ref='approval-1',
            mutation_scope={'allowed_paths': ['Assets/Rock.fbx', 'Assets/Rock.fbx.meta'], 'prohibited_paths': []})

    def test_apply_and_rollback_preserve_original_asset_and_guid(self):
        plan = self.prepare()
        self.stage.apply(plan)
        self.assertEqual(self.asset.read_bytes(), b'new')
        self.stage.rollback(plan)
        self.assertEqual(self.asset.read_bytes(), b'old')
        self.assertIn('abcdef1234567890abcdef1234567890', self.meta.read_text())
        self.assertEqual([x[1] for x in self.approvals], ['apply', 'rollback'])

    def test_user_change_prevents_apply_and_rollback_without_partial_restore(self):
        plan = self.prepare()
        self.asset.write_bytes(b'user')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.stage.apply(plan)
        self.asset.write_bytes(b'old')
        self.stage.apply(plan)
        self.meta.write_text('user edit')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.stage.rollback(plan)
        self.assertEqual(self.asset.read_bytes(), b'new')

    def test_forbid_raw_unity_mutation_scope_escape_and_symlink(self):
        scope = {'allowed_paths': ['Assets'], 'prohibited_paths': []}
        for path in ['Assets/Scene.unity', 'Assets/Rock.prefab', '../out.fbx']:
            with self.assertRaises(ValueError):
                self.stage.prepare({path: b'bad'}, approval_ref='a', mutation_scope=scope)
        with self.assertRaises(ValueError):
            self.stage.prepare({'Assets/Rock.fbx': b'x'}, approval_ref='a',
                               mutation_scope={'allowed_paths': ['Assets/Other'], 'prohibited_paths': []})
        alias = self.project / 'Assets/Alias.fbx'
        alias.symlink_to(self.asset)
        with self.assertRaises(ValueError):
            self.stage.prepare({'Assets/Alias.fbx': b'x'}, approval_ref='a', mutation_scope=scope)

    def test_tampered_plan_and_staging_are_rejected(self):
        plan = self.prepare()
        plan['approval_ref'] = 'other'
        with self.assertRaises(ValueError):
            self.stage.apply(plan)
        plan = self.prepare()
        (self.stage.directory / 'generated/Assets/Rock.fbx').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.stage.apply(plan)
        self.assertEqual(self.asset.read_bytes(), b'old')
