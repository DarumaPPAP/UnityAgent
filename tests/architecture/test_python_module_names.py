"""Ensure internal-only Python module names do not repeat their package context."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RENAMED_MODULES = {
    "context/manifest/build_context_manifest.py": "context/manifest/build.py",
    "context/manifest/validate_context_manifest.py": "context/manifest/validate.py",
    "context/budget/budget_runtime.py": "context/budget/evaluate.py",
    "context/retrieval/reference/reference_navigator.py": "context/retrieval/reference/navigator.py",
    "context/retrieval/memory/project_memory.py": "context/retrieval/memory/projections.py",
    "runtime/telemetry/runtime_telemetry.py": "runtime/telemetry/builders.py",
    "control_plane/workspace_task_execution.py": "control_plane/workspace_tasks.py",
}


class InternalModuleNamesTests(unittest.TestCase):
    def test_new_modules_present_without_duplicate_old_modules(self):
        root = ROOT / "src/unityagent"
        for previous, current in RENAMED_MODULES.items():
            with self.subTest(current=current):
                self.assertFalse((root / previous).exists())
                self.assertTrue((root / current).is_file())

    def test_no_stale_internal_module_imports(self):
        root = ROOT / "src/unityagent"
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for previous in RENAMED_MODULES:
                module = "unityagent." + previous[:-3].replace("/", ".")
                with self.subTest(path=path.relative_to(ROOT), module=module):
                    self.assertNotIn(module, source)


if __name__ == "__main__":
    unittest.main()
