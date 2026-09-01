from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.File.file_provider import FileProvider


class FileProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "Project"
        (self.project / "Assets/Scripts").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.12f1\n", encoding="utf-8")
        self.source = self.project / "Assets/Scripts/Example.cs"
        self.source.write_text("class Example { int Value = 1; }\n", encoding="utf-8")
        self.provider = FileProvider(self.project)

    def request(self, capability: str, *, allowed: list[str] | None = None) -> dict:
        mutation_scope = None
        if capability == "source.patch":
            mutation_scope = {"allowed_paths": allowed or ["Assets/Scripts"], "prohibited_paths": ["ProjectSettings"]}
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": str(self.project),
            "operation_kind": "source_mutation" if capability == "source.patch" else "read",
            "required_evidence": ["source_diff"] if capability == "source.patch" else ["source_read"],
            "mutation_scope": mutation_scope,
            "approval_ref": None,
            "preferred_surface": "project",
        }

    def test_read_text_returns_source_read_evidence(self) -> None:
        result = self.provider.read_text(self.request("source.read"), relative_path="Assets/Scripts/Example.cs", policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["source_read"])

    def test_exact_preimage_patch_succeeds_inside_scope(self) -> None:
        result = self.provider.patch_text(self.request("source.patch"), relative_path="Assets/Scripts/Example.cs", expected_text="Value = 1", replacement_text="Value = 2", policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertIn("Value = 2", self.source.read_text(encoding="utf-8"))

    def test_path_traversal_is_rejected(self) -> None:
        result = self.provider.patch_text(self.request("source.patch"), relative_path="../outside.cs", expected_text="a", replacement_text="b", policy_allowed=True)
        self.assertEqual(result["failure_class"], "scope_violation")

    def test_symlink_scope_escape_is_rejected(self) -> None:
        outside = Path(self.tmp.name) / "Outside.cs"
        outside.write_text("class Outside {}\n", encoding="utf-8")
        link = self.project / "Assets/Scripts/Escape.cs"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is not supported")
        result = self.provider.patch_text(self.request("source.patch"), relative_path="Assets/Scripts/Escape.cs", expected_text="Outside", replacement_text="Changed", policy_allowed=True)
        self.assertEqual(result["failure_class"], "scope_violation")
        self.assertEqual(outside.read_text(encoding="utf-8"), "class Outside {}\n")

    def test_serialized_unity_artifacts_are_not_raw_mutated(self) -> None:
        for relative in ("Assets/Test.unity", "Assets/Test.prefab", "Assets/Test.asset"):
            target = self.project / relative
            target.write_text("serialized: value\n", encoding="utf-8")
            result = self.provider.patch_text(self.request("source.patch", allowed=["Assets"]), relative_path=relative, expected_text="value", replacement_text="changed", policy_allowed=True)
            self.assertEqual(result["failure_class"], "blocked_by_policy", relative)
            self.assertEqual(target.read_text(encoding="utf-8"), "serialized: value\n")

    def test_mutation_outside_allowed_scope_is_rejected(self) -> None:
        target = self.project / "Assets/Other.cs"
        target.write_text("class Other {}\n", encoding="utf-8")
        result = self.provider.patch_text(self.request("source.patch"), relative_path="Assets/Other.cs", expected_text="Other", replacement_text="Changed", policy_allowed=True)
        self.assertEqual(result["failure_class"], "scope_violation")

    def test_ambiguous_preimage_is_rejected_without_writing(self) -> None:
        self.source.write_text("x x\n", encoding="utf-8")
        result = self.provider.patch_text(self.request("source.patch"), relative_path="Assets/Scripts/Example.cs", expected_text="x", replacement_text="y", policy_allowed=True)
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.assertEqual(self.source.read_text(encoding="utf-8"), "x x\n")

    def test_policy_denial_is_rechecked_immediately_before_patch(self) -> None:
        before = self.source.read_text(encoding="utf-8")
        result = self.provider.patch_text(self.request("source.patch"), relative_path="Assets/Scripts/Example.cs", expected_text="Value = 1", replacement_text="Value = 2", policy_allowed=False)
        self.assertEqual(result["failure_class"], "blocked_by_policy")
        self.assertEqual(self.source.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
