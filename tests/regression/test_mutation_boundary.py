"""Mutation Scopeと限定C#差分の実際のGuard境界を検証する。"""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unityagent.runtime.guardrails.csharp_patch import (
    patch_revisions,
    project_revision,
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
            project = Path(temporary) / "original"
            expected_project = Path(temporary) / "expected"
            source = b"public class Sample { public int Get() { return 1; } }\n"
            updated = b"public class Sample { public int Get() { return 2; } }\n"
            files = {
                "Assets/Sample.cs": source,
                "Assets/Unchanged.cs": b"class Unchanged {}\n",
                "Packages/manifest.json": b'{"dependencies":{}}\n',
                "ProjectSettings/ProjectVersion.txt": b"m_EditorVersion: 6000.3.0f1\n",
            }
            for root in (project, expected_project):
                for relative, contents in files.items():
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(contents)
            expected_input_revision = project_revision(expected_project)
            # 期待状態はPatch処理を使わず別Projectへ直接構成し、元Projectを保護する。
            (expected_project / "Assets/Sample.cs").write_bytes(updated)
            expected_result_revision = project_revision(expected_project)

            revision = patch_revisions(project, "Assets/Sample.cs", "return 1;", "return 2;")

            self.assertEqual(revision["expected_revision"], expected_input_revision)
            self.assertEqual(revision["result_revision"], expected_result_revision)
            self.assertEqual(revision["source_sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(revision["result_source_sha256"], hashlib.sha256(updated).hexdigest())
            self.assertEqual({path.relative_to(project).as_posix(): path.read_bytes() for path in project.rglob("*") if path.is_file()}, files)

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
