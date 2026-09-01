from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.provider_contract import (
    REGISTRY_PATH,
    load_provider_registry,
    parse_provider_registry,
)
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry


class ProviderRegistryTests(unittest.TestCase):
    def test_canonical_registry_is_valid_and_complete(self):
        registry = load_provider_registry()
        self.assertEqual(len(registry.providers), 6)
        self.assertEqual(len(registry.capability_requirements), 15)
        runtime = RuntimeProviderRegistry(registry=registry)
        self.assertEqual(runtime.provider("myunitymcp").transport, "mcp")
        self.assertGreater(
            runtime.provider("unity_cli").capabilities["project.test"].priority,
            runtime.provider("unity_cli").capabilities["scene.inspect"].priority,
        )

    def test_duplicate_yaml_key_is_rejected(self):
        text = """\
schema_version: "1.0"
authority: Runtime
provider_resolution_authority: true
execution_dispatch_authority: false
providers:
  duplicate: {}
  duplicate: {}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
                load_provider_registry(path, root=ROOT)

    def test_malformed_provider_is_rejected(self):
        value = yaml.safe_load((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        malformed = copy.deepcopy(value)
        malformed["providers"]["file"]["transport"] = "arbitrary_eval"
        with self.assertRaisesRegex(ValueError, "unsupported transport"):
            parse_provider_registry(malformed, root=ROOT)

    def test_unknown_capability_is_rejected(self):
        value = yaml.safe_load((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        malformed = copy.deepcopy(value)
        malformed["providers"]["file"]["capabilities"]["unknown.capability"] = copy.deepcopy(
            malformed["providers"]["file"]["capabilities"]["source.read"]
        )
        with self.assertRaisesRegex(ValueError, "unknown capabilities"):
            parse_provider_registry(malformed, root=ROOT)

    def test_registry_does_not_advertise_raw_scene_or_arbitrary_eval_fallback(self):
        registry = load_provider_registry()
        file_provider = registry.providers["file"]
        native_editor = registry.providers["native_unity_editor"]
        self.assertNotIn("scene.mutate", file_provider.capabilities)
        self.assertNotIn("domain.workflow", file_provider.capabilities)
        self.assertNotIn("scene.mutate", native_editor.capabilities)
        self.assertFalse(any(provider.transport == "arbitrary_eval" for provider in registry.providers.values()))


if __name__ == "__main__":
    unittest.main()
