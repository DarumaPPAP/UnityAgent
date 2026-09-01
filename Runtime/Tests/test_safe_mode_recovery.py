from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Tooling.Environment.native_editor_discovery import EditorProcessObservation
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.recovery import (
    ExactSourcePatch,
    SafeModeRecoveryBudget,
    SafeModeRecoveryCoordinator,
    SafeModeRecoveryPlan,
)


class SafeModeRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = (Path(self.tmp.name) / "Project").resolve()
        (self.project / "Assets/Scripts").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.12f1\n",
            encoding="utf-8",
        )
        self.source = self.project / "Assets/Scripts/Broken.cs"
        self.source.write_text("class Broken { BROKEN }\n", encoding="utf-8")
        self.editor_executable = self.project / "FakeUnityEditor"
        self.editor_executable.write_text("fixture", encoding="utf-8")
        self.killed: list[int] = []
        self.restarts: list[tuple[str, str]] = []

    def snapshot(
        self,
        *,
        safe_mode=True,
        editor=True,
        bound_pid=123,
        cli=False,
        myunity=False,
        coplay=False,
    ) -> dict:
        if editor:
            binding_status = "bound" if bound_pid is not None else "not_running"
            running = bound_pid is not None
            project_bound = bound_pid is not None
            instance = f"pid:{bound_pid}" if bound_pid is not None else None
        else:
            binding_status = "not_running"
            running = False
            project_bound = False
            instance = None
        return {
            "schema_version": "1.0",
            "project": {
                "root": str(self.project),
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.12f1",
                "required_paths": {
                    "assets": True,
                    "packages": True,
                    "project_settings": True,
                },
            },
            "filesystem": {
                "readable": True,
                "writable": True,
                "writable_in_mutation_scope": True,
            },
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {
                "installed": editor,
                "version": "6000.3.12f1" if editor else None,
                "executable_path": str(self.editor_executable) if editor else None,
                "project_version_match": True if editor else "unknown",
                "running": running,
                "safe_mode": safe_mode if editor else "unknown",
                "project_bound": project_bound,
                "binding_status": binding_status,
                "bound_instance_id": instance,
            },
            "unity_cli": {
                "available": cli,
                "version": "1.0" if cli else None,
                "executable_path": "/unity-cli" if cli else None,
                "failure_class": None if cli else "unavailable",
            },
            "pipeline": {"installed": cli, "reachable": cli},
            "myunitymcp": {
                "reachable": myunity,
                "available": myunity,
                "project_bound": myunity,
                "binding_status": "bound" if myunity else "unbound",
                "bound_instance_id": "mcp-1" if myunity else None,
            },
            "coplay_mcp": {
                "reachable": coplay,
                "available": coplay,
                "project_bound": coplay,
                "binding_status": "bound" if coplay else "unbound",
                "bound_instance_id": "coplay-1" if coplay else None,
            },
            "test_framework": {"available": True},
            "build": {
                "requested_target": "StandaloneWindows64",
                "requested_target_module_available": True,
            },
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "SAFE_MODE" if safe_mode is True else "NATIVE_EDITOR",
            "binding_fingerprint": "0" * 64,
        }

    def request(
        self,
        capability: str,
        *,
        approval_ref: str | None = None,
    ) -> dict:
        policy = policy_for_capability(capability)
        scope = None
        if policy["requires_mutation_scope"]:
            scope = {
                "allowed_paths": ["Assets/Scripts/Broken.cs"],
                "prohibited_paths": ["ProjectSettings"],
            }
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": str(self.project),
            "operation_kind": policy["operation_kind"],
            "required_evidence": list(policy["minimum_required_evidence"]),
            "mutation_scope": scope,
            "approval_ref": approval_ref,
            "preferred_surface": None,
        }

    def patch_plan(self, *, relative_path="Assets/Scripts/Broken.cs") -> SafeModeRecoveryPlan:
        return SafeModeRecoveryPlan.create(
            patch_request=self.request("source.patch"),
            patch=ExactSourcePatch(
                relative_path=relative_path,
                expected_text="BROKEN",
                replacement_text="FIXED",
            ),
        )

    def exact_process(
        self,
        *,
        pid=123,
        project_root: Path | None = None,
        safe_mode=True,
    ) -> EditorProcessObservation:
        return EditorProcessObservation(
            pid=pid,
            executable_path=str(self.editor_executable),
            command_line=(
                f'"{self.editor_executable}" -projectPath "{project_root or self.project}" '
                + ("-safeMode" if safe_mode else "")
            ),
            project_root=str(project_root or self.project),
            safe_mode=safe_mode,
        )

    def terminate(self, pid: int) -> bool:
        self.killed.append(pid)
        return True

    def restart(self, executable, project_root) -> int:
        self.restarts.append((str(executable), str(project_root)))
        return 456

    def recovered_snapshot(self) -> dict:
        return self.snapshot(safe_mode=False, editor=True, bound_pid=None)

    @staticmethod
    def compiler_log(path="Assets/Scripts/Broken.cs") -> str:
        return f"{path}(1,16): error CS0103: The name 'BROKEN' does not exist\n"

    def coordinator(
        self,
        *,
        process_probe=None,
        terminate=None,
        restart=None,
        rediscover=None,
        budget=None,
    ) -> SafeModeRecoveryCoordinator:
        return SafeModeRecoveryCoordinator(
            self.project,
            budget=budget,
            process_probe_fn=process_probe or (lambda **_: [self.exact_process()]),
            terminate_fn=terminate or self.terminate,
            restart_fn=restart or self.restart,
            rediscover_fn=rediscover or (lambda **_: self.recovered_snapshot()),
        )

    def recover(self, coordinator: SafeModeRecoveryCoordinator, *, plan=None, log=None):
        return coordinator.recover(
            self.request("project.test"),
            self.snapshot(),
            capability_context=ResolutionContext(policy_allowed=True),
            plan=plan or self.patch_plan(),
            patch_context=ResolutionContext(
                policy_allowed=True,
                approval_required=False,
                approval_complete=False,
            ),
            compiler_log_text=log or self.compiler_log(),
        )

    def test_happy_path_patches_restarts_exact_editor_and_only_marks_ready_for_retry(self) -> None:
        result = self.recover(self.coordinator())
        self.assertEqual(result["status"], "recovered")
        self.assertFalse(result["verified"])
        self.assertEqual(result["original_capability_status"], "ready_for_retry")
        self.assertEqual(result["capability_resolution"]["status"], "resolved")
        self.assertEqual(
            result["capability_resolution"]["provider_ref"],
            "native_unity_editor",
        )
        self.assertEqual(self.killed, [123])
        self.assertEqual(len(self.restarts), 1)
        self.assertEqual(Path(self.restarts[0][0]), self.editor_executable)
        self.assertEqual(Path(self.restarts[0][1]), self.project)
        self.assertIn("FIXED", self.source.read_text(encoding="utf-8"))
        self.assertEqual(result["evidence"], ["source_diff"])
        self.assertNotIn("test_execution", result["evidence"])

    def test_wrong_pid_is_rejected_before_patch_or_kill(self) -> None:
        coordinator = self.coordinator(
            process_probe=lambda **_: [self.exact_process(pid=999)]
        )
        result = self.recover(coordinator)
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.assertEqual(self.killed, [])
        self.assertIn("BROKEN", self.source.read_text(encoding="utf-8"))

    def test_exact_pid_bound_to_other_project_is_never_killed(self) -> None:
        other = (Path(self.tmp.name) / "OtherProject").resolve()
        other.mkdir()
        coordinator = self.coordinator(
            process_probe=lambda **_: [self.exact_process(project_root=other)]
        )
        result = self.recover(coordinator)
        self.assertEqual(result["failure_class"], "scope_violation")
        self.assertEqual(self.killed, [])
        self.assertIn("BROKEN", self.source.read_text(encoding="utf-8"))

    def test_safe_mode_recovery_cycle_budget_is_bounded(self) -> None:
        coordinator = self.coordinator(
            budget=SafeModeRecoveryBudget(maximum_cycles=1)
        )
        first = self.recover(coordinator, log="error CS0103: unknown source\n")
        self.assertEqual(first["failure_class"], "not_observed")
        second = self.recover(coordinator)
        self.assertEqual(second["failure_class"], "precondition_failed")
        self.assertIn("budget is exhausted", second["reason"])
        self.assertEqual(coordinator.budget.cycles_used, 1)
        self.assertEqual(self.killed, [])

    def test_scope_expansion_after_recovery_plan_creation_is_rejected(self) -> None:
        plan = self.patch_plan()
        plan.patch_request["mutation_scope"]["allowed_paths"] = ["Assets"]
        result = self.recover(self.coordinator(), plan=plan)
        self.assertEqual(result["failure_class"], "scope_violation")
        self.assertEqual(self.killed, [])
        self.assertIn("BROKEN", self.source.read_text(encoding="utf-8"))

    def test_serialized_unity_artifact_cannot_be_a_safe_mode_source_patch(self) -> None:
        with self.assertRaises(ValueError):
            self.patch_plan(relative_path="Assets/Scenes/Test.unity")

    def test_non_narrow_or_pathless_compiler_diagnostics_do_not_authorize_patch(self) -> None:
        pathless = self.recover(
            self.coordinator(),
            log="error CS0103: path was not observed\n",
        )
        self.assertEqual(pathless["failure_class"], "not_observed")
        self.assertEqual(self.killed, [])
        self.assertIn("BROKEN", self.source.read_text(encoding="utf-8"))

        self.source.write_text("class Broken { BROKEN }\n", encoding="utf-8")
        multi = self.compiler_log() + self.compiler_log("Assets/Scripts/Other.cs")
        other_target = self.recover(self.coordinator(), log=multi)
        self.assertEqual(other_target["failure_class"], "not_observed")
        self.assertEqual(self.killed, [])

    def test_pid_change_after_patch_is_reobserved_and_refuses_kill(self) -> None:
        calls = {"count": 0}

        def probe(**_):
            calls["count"] += 1
            if calls["count"] == 1:
                return [self.exact_process(pid=123)]
            return [self.exact_process(pid=999)]

        result = self.recover(self.coordinator(process_probe=probe))
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.assertEqual(self.killed, [])
        self.assertIn("FIXED", self.source.read_text(encoding="utf-8"))

    def test_termination_failure_stops_before_restart(self) -> None:
        def fail_terminate(pid: int) -> bool:
            self.killed.append(pid)
            return False

        result = self.recover(self.coordinator(terminate=fail_terminate))
        self.assertEqual(result["failure_class"], "execution_failed")
        self.assertEqual(self.killed, [123])
        self.assertEqual(self.restarts, [])
        self.assertIn("FIXED", self.source.read_text(encoding="utf-8"))

    def test_recovery_without_safe_original_capability_candidate_is_partial(self) -> None:
        unavailable = self.snapshot(safe_mode="unknown", editor=False, bound_pid=None)
        coordinator = self.coordinator(rediscover=lambda **_: unavailable)
        result = self.recover(coordinator)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["verified"])
        self.assertEqual(result["evidence"], ["source_diff"])
        self.assertNotEqual(result["capability_resolution"]["status"], "resolved")
        self.assertNotIn("test_execution", result["evidence"])


if __name__ == "__main__":
    unittest.main()
