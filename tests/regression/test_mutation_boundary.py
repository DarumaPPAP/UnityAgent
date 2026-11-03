"""Mutation Scopeと限定C#差分の実際のGuard境界を検証する。"""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unityagent.runtime.guardrails.csharp_patch import (
    patch_revisions,
    source_target,
    validate_csharp_patch,
)
from unityagent.runtime.guardrails.mutation_guard import evaluate_mutation_scope
from unityagent.runtime.sandbox.workspace_guard import WorkspaceGuardError


class MutationBoundaryTests(unittest.TestCase):
    def test_allowed_path_accepts_its_child(self):
        result = evaluate_mutation_scope(
            work_kind="mutation",
            changed_paths=["Assets/Allowed/Edited.cs"],
            allowed_paths=["Assets/Allowed"],
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["scope_status"], "within_scope")

    def test_sibling_prefix_does_not_expand_allowed_scope(self):
        result = evaluate_mutation_scope(
            work_kind="mutation",
            changed_paths=["Assets/AllowedExtra/Edited.cs"],
            allowed_paths=["Assets/Allowed"],
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "mutation_escaped_allowed_scope")
        self.assertEqual(result["paths"], ["Assets/AllowedExtra/Edited.cs"])

    def test_prohibition_takes_precedence_over_allowed_scope(self):
        result = evaluate_mutation_scope(
            work_kind="mutation",
            changed_paths=["Assets/Allowed/Private/Edited.cs"],
            allowed_paths=["Assets/Allowed"],
            prohibited_paths=["Assets/Allowed/Private"],
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "prohibited_path_mutated")
        self.assertEqual(result["paths"], ["Assets/Allowed/Private/Edited.cs"])

    def test_verification_work_cannot_mutate(self):
        result = evaluate_mutation_scope(
            work_kind="verification",
            changed_paths=["Assets/Allowed/Edited.cs"],
            allowed_paths=["Assets/Allowed"],
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "non_mutating_work_changed_workspace")

    def test_path_traversal_is_rejected_before_scope_comparison(self):
        with self.assertRaises(WorkspaceGuardError):
            evaluate_mutation_scope(
                work_kind="mutation",
                changed_paths=["Assets/../Packages/Edited.cs"],
                allowed_paths=["Assets"],
            )

    def test_literal_or_comment_cannot_be_used_as_patch_preimage(self):
        source = "public class Sample { public int Get() { /* return 3; */ return 1; } }"
        with self.assertRaisesRegex(ValueError, "comment or literal"):
            validate_csharp_patch(source, "return 3;", "return 4;")
        self.assertIn("return 1;", source)

    def test_patch_revision_is_computed_without_changing_source(self):
        with TemporaryDirectory(prefix="unityagent-mutation-") as temporary:
            project = Path(temporary)
            for name in ("Assets", "Packages", "ProjectSettings"):
                (project / name).mkdir()
            source = "public class Sample { public int Get() { return 1; } }\n"
            target = project / "Assets" / "Sample.cs"
            target.write_text(source, encoding="utf-8")

            revision = patch_revisions(
                project, "Assets/Sample.cs", "return 1;", "return 2;"
            )

            self.assertNotEqual(revision["expected_revision"], revision["result_revision"])
            self.assertNotEqual(revision["source_sha256"], revision["result_source_sha256"])
            self.assertEqual(target.read_text(encoding="utf-8"), source)

    def test_patch_target_outside_assets_is_rejected_without_write(self):
        with TemporaryDirectory(prefix="unityagent-mutation-") as temporary:
            project = Path(temporary)
            (project / "Packages").mkdir()
            target = project / "Packages" / "Sample.cs"
            target.write_text("class Sample {}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Assets source file"):
                source_target(project, "Packages/Sample.cs")

            self.assertEqual(target.read_text(encoding="utf-8"), "class Sample {}")

    def test_symlink_source_alias_is_rejected(self):
        with TemporaryDirectory(prefix="unityagent-mutation-") as temporary:
            project = Path(temporary)
            (project / "Assets").mkdir()
            target = project / "Assets" / "Sample.cs"
            target.write_text("class Sample {}", encoding="utf-8")
            alias = project / "Assets" / "Alias.cs"
            try:
                alias.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable on this host: {exc}")

            with self.assertRaisesRegex(ValueError, "aliases"):
                source_target(project, "Assets/Alias.cs")
            self.assertEqual(target.read_text(encoding="utf-8"), "class Sample {}")

    def test_hardlink_source_alias_is_rejected(self):
        with TemporaryDirectory(prefix="unityagent-mutation-") as temporary:
            project = Path(temporary)
            (project / "Assets").mkdir()
            target = project / "Assets" / "Sample.cs"
            target.write_text("class Sample {}", encoding="utf-8")
            try:
                os.link(target, project / "Assets" / "Alias.cs")
            except OSError as exc:
                self.skipTest(f"hardlink creation unavailable on this host: {exc}")

            with self.assertRaisesRegex(ValueError, "unaliased regular file"):
                source_target(project, "Assets/Sample.cs")
            self.assertEqual(target.read_text(encoding="utf-8"), "class Sample {}")


if __name__ == "__main__":
    unittest.main()
