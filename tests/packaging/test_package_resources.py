"""Product resources must work independently of the repository checkout."""
import importlib.util
import unittest

class PackageResourcesTests(unittest.TestCase):
    def test_installed_namespace_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('unityagent'))

    def test_definition_fingerprints_are_complete(self):
        from unityagent.cli import _fingerprint
        fingerprint = _fingerprint()
        self.assertFalse([value for value in fingerprint.values() if value.startswith('missing:')])

    def test_context_resolves_bundled_skill_and_standards(self):
        from unityagent.context.assembly.materialize_context import materialize_context
        view = materialize_context('package-proof', 'csharp-local-fix')
        self.assertTrue(view['selected_refs']['primary_skill']['revision'].startswith('sha256:'))

    def test_resource_paths_cannot_escape(self):
        from unityagent.context.selection.path_resolver import resolve_for_read, ReferenceResolutionError
        from unityagent.resources import resource_root
        with self.assertRaises(ReferenceResolutionError):
            resolve_for_read('../outside', resource_root())

if __name__ == '__main__':
    unittest.main()
