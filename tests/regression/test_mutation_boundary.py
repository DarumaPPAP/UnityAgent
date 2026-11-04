"""Mutation Scopeと限定C#差分の実際のGuard境界を検証する。"""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
import sys
import yaml
from functools import partial
from unittest.mock import Mock, patch
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
from unityagent.runtime.runner.codex.codex_runner import execute as run_codex
from unityagent.runtime.tooling.tool_broker import ToolBroker
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.execution_control.resource_lease import RuntimeProjectLease

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


class FileMutationTests(unittest.TestCase):
    """実FileProviderの書込みと、独立したFS差分でScopeを観測する。"""

    def setUp(self):
        temporary = TemporaryDirectory(prefix="ua-file-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.files = {"Assets/Allowed/Sample.cs": b"class Sample { int Value() { return 1; } }\r\n", "Assets/Other.cs": b"class Other {}\n", "Packages/manifest.json": b"{}\n"}
        self.files["ProjectSettings/ProjectVersion.txt"] = b"m_EditorVersion: 6000.3.0f1\n"
        for relative, content in self.files.items():
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.provider = FileProvider(self.project)
        self.request = {"schema_version": "1.0", "capability": "source.patch", "project_root": str(self.project), "operation_kind": "source_mutation", "required_evidence": ["source_diff"], "mutation_scope": {"allowed_paths": ["Assets/Allowed"], "prohibited_paths": []}, "approval_ref": "approval-A", "preferred_surface": "host"}

    def snapshot(self):
        return {path.relative_to(self.project).as_posix(): path.read_bytes() for path in self.project.rglob("*") if path.is_file()}

    def apply(self, relative="Assets/Allowed/Sample.cs", **overrides):
        parameters = {"relative_path": relative, "expected_text": "return 1;", "replacement_text": "return 2;", "policy_allowed": True, "approval_required": True, "approval_complete": True, "preserve_newlines": True}
        parameters.update(overrides)
        return self.provider.patch_text(self.request, **parameters)

    def test_applied_diff_is_exact_and_within_scope(self):
        outcome = self.apply()
        after = self.snapshot()
        self.assertEqual(outcome["status"], "passed")
        expected = {**self.files, "Assets/Allowed/Sample.cs": b"class Sample { int Value() { return 2; } }\r\n"}
        self.assertEqual(after, expected)
        changed = [path for path in set(self.files) | set(after) if self.files.get(path) != after.get(path)]
        scope = evaluate_mutation_scope(work_kind="mutation", changed_paths=changed, **self.request["mutation_scope"])
        self.assertEqual(scope["status"], "passed")
        self.assertEqual(changed, ["Assets/Allowed/Sample.cs"])
        self.assertEqual(outcome["before_sha256"], hashlib.sha256(self.files[changed[0]]).hexdigest())
        self.assertEqual(outcome["after_sha256"], hashlib.sha256(expected[changed[0]]).hexdigest())

    def test_invalid_targets_fail_closed_without_project_changes(self):
        for relative in ("../outside.cs", "Assets/../Packages/manifest.json", "Assets/Other.cs", "Assets/AllowedExtra/Sample.cs", str(self.project / "Assets/Allowed/Sample.cs")):
            with self.subTest(relative=relative):
                outcome = self.apply(relative)
                self.assertEqual(outcome["status"], "failed")
                self.assertEqual(outcome["failure_class"], "scope_violation")
                self.assertEqual(self.snapshot(), self.files)

    def test_prohibition_overrides_allowed_scope_before_write(self):
        self.request["mutation_scope"]["prohibited_paths"] = ["Assets/Allowed/Sample.cs"]
        outcome = self.apply()
        self.assertEqual(outcome["failure_class"], "scope_violation")
        self.assertEqual(outcome["reason"], "prohibited_path_mutated")
        self.assertEqual(self.snapshot(), self.files)

    def test_wrong_project_is_rejected_before_write(self):
        self.request["project_root"] = str(self.project / "other-project")
        self.assertEqual(self.apply()["failure_class"], "scope_violation")
        self.assertEqual(self.snapshot(), self.files)

    def test_missing_approval_or_stale_preimage_preserves_source(self):
        for parameters, failure in (({"approval_complete": False}, "blocked_by_approval"), ({"expected_sha256": "0" * 64}, "precondition_failed"), ({"expected_text": "return 9;"}, "precondition_failed")):
            with self.subTest(parameters=parameters):
                self.assertEqual(self.apply(**parameters)["failure_class"], failure)
                self.assertEqual(self.snapshot(), self.files)

    def test_post_apply_scope_check_detects_unexpected_additional_change(self):
        self.assertEqual(self.apply()["status"], "passed")
        # Provider外の故障を注入し、申告pathだけでなく実差分が拒否されることを確認する。
        (self.project / "Assets/Other.cs").write_bytes(b"unexpected mutation")
        after = self.snapshot()
        changed = [path for path in set(self.files) | set(after) if self.files.get(path) != after.get(path)]
        outcome = evaluate_mutation_scope(work_kind="mutation", changed_paths=changed, **self.request["mutation_scope"])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["paths"], ["Assets/Other.cs"])

    def run_provider_process(self, *, inject_escape):
        # Agentの判断は代替CLIで固定し、実子Process・FileProvider・適用後Guardを通す。
        driver = self.root / "provider_cli.py"
        driver.write_text('''import json, sys
from pathlib import Path
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = Path(request["project_root"])
result = FileProvider(root).patch_text(request, relative_path="Assets/Allowed/Sample.cs", expected_text="return 1;", replacement_text="return 2;", policy_allowed=True, approval_required=True, approval_complete=True, preserve_newlines=True)
if result["status"] != "passed":
    raise RuntimeError(result)
if sys.argv[2] == "escape":
    (root / "Assets/Other.cs").write_bytes(b"unexpected mutation")
''', encoding="utf-8")
        provider_request = self.root / "provider-request.json"
        provider_request.write_text(json.dumps(self.request), encoding="utf-8")
        request = {"schema_version": "1.0", "run_id": "run-A", "step_id": "step-A", "action_id": "action-A", "workspace_root": str(self.project), "prompt": "test-owned deterministic FileProvider invocation", "definition_fingerprint": {}, "execution": {"profile": "personal_full_control", "work_kind": "mutation", "mutation_authorized": True, "human_approval_required": True, "human_approval_granted": True}, "tool_identity": {"model": "test-driver", "provider": "test"}, "mutation_scope": self.request["mutation_scope"]}
        request_path = self.root / "runtime-request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        output = self.root / "output"
        result = run_codex(request, output, command_prefix=[sys.executable, str(driver), str(provider_request), "escape" if inject_escape else "normal"], timeout_seconds=20, reasoning_effort="high")
        evidence = yaml.safe_load((output / "mutation-evidence.yaml").read_text(encoding="utf-8"))
        return result, evidence

    def test_runtime_observes_actual_file_provider_mutation(self):
        result, evidence = self.run_provider_process(inject_escape=False)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(evidence["changed_paths"], {"observation_state": "observed", "paths": ["Assets/Allowed/Sample.cs"]})
        self.assertEqual(evidence["scope_status"], "within_scope")
        self.assertEqual(self.snapshot(), {**self.files, "Assets/Allowed/Sample.cs": b"class Sample { int Value() { return 2; } }\r\n"})

    def test_runtime_fails_closed_on_actual_extra_change_after_provider(self):
        result, evidence = self.run_provider_process(inject_escape=True)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["runtime_failure"]["reason"], "mutation_escaped_allowed_scope")
        self.assertEqual(evidence["changed_paths"]["paths"], ["Assets/Allowed/Sample.cs", "Assets/Other.cs"])
        self.assertNotEqual(evidence["scope_status"], "within_scope")
        self.assertEqual((self.project / "Packages/manifest.json").read_bytes(), self.files["Packages/manifest.json"])

    def bounded_dispatch(self, *, approval_complete=True, allowed_paths=None, arguments=None):
        request = {**self.request, "preferred_surface": "project", "mutation_scope": {"allowed_paths": allowed_paths or ["Assets/Allowed"], "prohibited_paths": []}}
        snapshot = discover_environment(str(self.project), mutation_allowed_paths=["Assets/Allowed"], editor_candidates=[], editor_processes=[], editor_candidates_observed=True, editor_processes_observed=True, which_fn=lambda name: None)
        context = ResolutionContext(policy_allowed=True, approval_required=True, approval_complete=approval_complete)
        revisions = patch_revisions(self.project, "Assets/Allowed/Sample.cs", "return 1;", "return 2;")
        parameters = {"bounded_csharp_patch": True, "relative_path": "Assets/Allowed/Sample.cs", "expected_text": "return 1;", "replacement_text": "return 2;", **revisions, **(arguments or {})}
        executor = Mock(wraps=self.provider.execute)
        # Leaseの保存先だけを所有領域へ束縛し、実Lease・Guard・Resolver・Dispatcherを通す。
        with patch("unityagent.runtime.dispatcher.tool_runtime_dispatcher.RuntimeProjectLease", partial(RuntimeProjectLease, lease_root=self.root / "leases")):
            result = ToolBroker().dispatch(request, snapshot, context=context, executors={"file": executor}, provider_arguments={"file": parameters}, maximum_retry_attempts=0)
        return result, executor, revisions

    def test_broker_applies_bounded_patch_through_real_provider_entry(self):
        before = project_revision(self.project)
        result, executor, revisions = self.bounded_dispatch()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["resolution"]["provider_ref"], "file")
        executor.assert_called_once()
        self.assertEqual(self.snapshot(), {**self.files, "Assets/Allowed/Sample.cs": b"class Sample { int Value() { return 2; } }\r\n"})
        self.assertEqual(before, revisions["expected_revision"])
        self.assertEqual(project_revision(self.project), revisions["result_revision"])
        self.assertEqual(result["provider_result"]["before_sha256"], hashlib.sha256(self.files["Assets/Allowed/Sample.cs"]).hexdigest())
        self.assertEqual(result["provider_result"]["after_sha256"], hashlib.sha256(b"class Sample { int Value() { return 2; } }\r\n").hexdigest())

    def test_broker_incomplete_approval_never_invokes_provider(self):
        result, executor, _ = self.bounded_dispatch(approval_complete=False)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["provider_result"]["failure_class"], "blocked_by_approval")
        executor.assert_not_called()
        self.assertEqual(self.snapshot(), self.files)

    def test_broker_provider_scope_rejection_preserves_entire_project(self):
        result, executor, _ = self.bounded_dispatch(allowed_paths=["Assets/Other.cs"])
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["provider_result"]["failure_class"], "scope_violation")
        executor.assert_called_once()
        self.assertEqual(self.snapshot(), self.files)

    def test_broker_provider_rechecks_patch_preimage_before_write(self):
        result, executor, _ = self.bounded_dispatch(arguments={"source_sha256": "0" * 64})
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["provider_result"]["failure_class"], "precondition_failed")
        executor.assert_called_once()
        self.assertEqual(self.snapshot(), self.files)


if __name__ == "__main__":
    unittest.main()
