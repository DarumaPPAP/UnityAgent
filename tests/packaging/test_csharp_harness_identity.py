"""Python packaging migration must preserve public Unity C# type identity."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]

class CSharpHarnessIdentityTests(unittest.TestCase):
    def test_migrated_harness_retains_public_csharp_namespace(self):
        harness = ROOT / 'src/unityagent/runtime/harnesses/unity/editor'
        expected = {'UnityArtifactGraphScanner', 'UnityArtifactGraphExporter',
                    'UnityArtifactImpactAnalyzer', 'UnityRuntimeHarnessWindow', 'UnityArtifactGraph'}
        observed = set()
        for source in harness.glob('*.cs'):
            text = source.read_text(encoding='utf-8')
            namespace = re.search(r'^namespace\s+([\w.]+)', text, re.MULTILINE)
            self.assertIsNotNone(namespace, source.name)
            self.assertEqual('UnityAgent.Runtime.Harnesses.Unity.Editor', namespace.group(1), source.name)
            observed.update(re.findall(r'public\s+(?:sealed\s+|static\s+|abstract\s+)?class\s+(\w+)', text))
        self.assertTrue(expected.issubset(observed), expected - observed)
