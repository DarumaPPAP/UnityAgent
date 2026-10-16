import unittest
from unityagent.runtime.reference_implementation.profiles import CATALOG
from unityagent.orchestration.routing.subagent_identity import canonical_subagent_id


class QaMigrationTests(unittest.TestCase):
    def test_legacy_id_has_explicit_migration_and_one_canonical_profile(self):
        self.assertEqual(canonical_subagent_id('performance_subagent'), 'qa_subagent')
        self.assertEqual(CATALOG.get('performance_subagent').profile_id, 'qa_subagent')
        self.assertEqual(CATALOG.get('qa_subagent').display_name, 'QASubAgent')
        self.assertIn('performance.analyze', CATALOG.get('qa_subagent').capabilities)
        self.assertNotIn('performance_subagent', [d.definition_id for d in CATALOG.definitions()])
