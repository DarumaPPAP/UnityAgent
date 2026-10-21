import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from unityagent.cli import _fingerprint
from unityagent.control_plane.csharp_fix import approve_csharp_fix
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.persistence.store.atomic_store import PersistenceError
from unityagent.runtime.guardrails.csharp_patch import project_revision
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider


GATES = {'static': ['static_review'], 'compile': ['compile_observation', 'current_compile_observation'],
         'editmode': ['test_execution', 'targeted_editmode_execution']}


class CSharpIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = self.root / 'original'
        for child in ('Assets', 'Packages', 'ProjectSettings', '.git/objects'):
            (self.original / child).mkdir(parents=True)
        (self.original / '.git/HEAD').write_text('ref: refs/heads/fixture\n')
        (self.original / 'Packages/manifest.json').write_text('{"dependencies":{"com.unity.test-framework":"1.3.9"}}')
        (self.original / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.15f1\n')
        (self.original / 'Assets/Calculator.cs').write_text('public static class Calculator { public static int Add(int a, int b) { return a - b; } }\n')
        (self.original / 'Assets/Multiplier.cs').write_text('public static class Multiplier { public static int Multiply(int a, int b) { return a + b; } }\n')
        self.plane = UnityAgentControlPlane(self.root / 'state')
        self.definition = _fingerprint()
        self.tasks, self.parameters, self.native_calls = [], {}, []
        projects = {str(self.original): {'read_set': ['.'], 'write_set': ['Assets/Calculator.cs', 'Assets/Multiplier.cs']}}
        self.lease_patch = patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks')
        self.lease_patch.start()
        self.addCleanup(self.lease_patch.stop)
        for name, target, test in [('left', 'Calculator.cs', 'CalculatorTests.AddReturnsSum'),
                                   ('right', 'Multiplier.cs', 'MultiplierTests.Multiplies')]:
            project = self.root / name
            shutil.copytree(self.original, project)
            parameters = self.runtime(project)
            entry = {'schema_version': '2.0', 'request_id': name, 'entry_point': 'codex_plugin',
                'project_root': str(project), 'intent': {'kind': 'csharp_local_fix',
                    'goal_or_confirmed_error': 'Correct the confirmed arithmetic error in ' + target,
                    'target_source': 'Assets/' + target, 'expected_behavior': 'Return the mathematically correct result',
                    'allowed_changes': 'Correct one return expression and preserve every declaration',
                    'expected_revision': project_revision(project), 'editmode_tests': [test]}}
            with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process', side_effect=self.model):
                proposal = self.plane.execute(entry, run_id='proposal-' + name,
                    definition_fingerprint=self.definition, reasoning_model='gpt-fixture', **parameters)
            self.assertEqual(proposal['reason'], 'explicit_patch_approval_required', proposal)
            approval = approve_csharp_fix(self.plane, proposal['patch_plan_id'])
            entry['intent']['patch_plan_id'] = proposal['patch_plan_id']
            entry['approval_ref'] = approval['approval_ref']
            self.tasks.append({'id': name, 'workspace': str(project), 'depends_on': [],
                'goal': entry['intent']['goal_or_confirmed_error'], 'read_set': ['.'], 'write_set': ['Assets/' + target],
                'resource_claims': [], 'parallel_safe': True, 'required_gates': copy.deepcopy(GATES), 'entry_request': entry})
            self.parameters[name] = parameters
            projects[str(project)] = {'read_set': ['.'], 'write_set': ['Assets/' + target]}
        self.contract = {'goal': 'Correct both arithmetic errors and verify the final original revision',
            'project_root': str(self.original), 'projects': projects, 'required_gates': copy.deepcopy(GATES),
            'approval_conditions': ['existing_policy'], 'allowed_entry_kinds': ['csharp_local_fix']}

    def model(self, command, **kwargs):
        workspace = Path(command[command.index('--cd') + 1])
        context = json.loads((workspace / 'patch-context.json').read_text())
        multiply = context['intent']['target_source'].endswith('Multiplier.cs')
        response = {'expected_text': 'return a + b;' if multiply else 'return a - b;',
            'replacement_text': 'return a * b;' if multiply else 'return a + b;', 'summary': 'Correct arithmetic',
            'source_context_id': context['context_id'], 'source_context_fingerprint': context['context_fingerprint']}
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(response))
        from tests.runtime.test_reasoning_runtime_handoff import process_result
        return process_result()

    def runtime(self, project, *, zero_final_tests=False):
        snapshot = discover_environment(str(project), mutation_allowed_paths=['Assets'],
            editor_processes=[], editor_processes_observed=True).to_dict()
        editor = self.root / 'Unity.exe'
        editor.write_text('fixture')
        snapshot['unity_editor'].update(installed=True, executable_path=str(editor), version='6000.3.15f1',
                                        project_version_match=True, safe_mode=False)
        def dispatch(request, **kwargs):
            command = list(request.command)
            self.native_calls.append((str(project), command))
            Path(command[command.index('-logFile') + 1]).write_text('Begin MonoManager ReloadAssembly\n')
            if '-testResults' in command:
                names = command[command.index('-testFilter') + 1].split(';')
                now = datetime.now(timezone.utc).isoformat()
                cases = ''.join(f'<test-case fullname="{name}" result="Passed"/>' for name in names)
                if zero_final_tests and len(names) == 2:
                    names, cases = [], ''
                Path(command[command.index('-testResults') + 1]).write_text(
                    f'<test-run result="Passed" total="{len(names)}" passed="{len(names)}" failed="0" start-time="{now}" end-time="{now}">{cases}</test-run>')
            return {'status': 'passed', 'result': SimpleNamespace(returncode=0)}
        native = NativeUnityEditorProvider(project, snapshot, dispatch_fn=dispatch,
            process_probe_fn=lambda **kwargs: [], temp_root=self.root / ('native-' + project.name))
        return {'environment_snapshot': snapshot, 'context': ResolutionContext(policy_allowed=True),
                'executors': {'file': FileProvider(project).execute, 'native_unity_editor': native.execute}}

    def workers(self):
        result = self.plane.execute_workspace_tasks(self.tasks, run_id='parallel-fixes',
            definition_fingerprint=self.definition, task_parameters=self.parameters,
            root_contract=self.contract, parallel_enabled=True)
        self.assertTrue(all(record['status'] == 'verified' for record in result['tasks'].values()), result)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(project_revision(self.original), self.tasks[0]['entry_request']['intent']['expected_revision'])
        return result

    def test_worker_results_need_explicit_union_approval_before_original_changes(self):
        self.workers()
        proposal = self.plane.create_integration_plan(run_id='parallel-fixes')
        self.assertEqual(len(proposal['patch_preview']), 2)
        before = project_revision(self.original)
        with self.assertRaises((ValueError, PersistenceError)):
            self.plane.integrate_workspace_results(run_id='parallel-fixes',
                integration_plan_id=proposal['integration_plan_id'], approval_ref='not-approved',
                original_parameters=self.runtime(self.original))
        self.assertEqual(project_revision(self.original), before)

    def test_approved_serial_integration_takes_static_compile_and_union_tests_at_final_revision(self):
        self.workers()
        proposal = self.plane.create_integration_plan(run_id='parallel-fixes')
        approval = self.plane.approve_integration(integration_plan_id=proposal['integration_plan_id'])
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process') as model:
            result = self.plane.integrate_workspace_results(run_id='parallel-fixes',
                integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
                original_parameters=self.runtime(self.original))
        model.assert_not_called()
        self.assertEqual(result['status'], 'verified', result)
        self.assertTrue(all(value == 'passed' for value in result['final_gates'].values()))
        self.assertEqual(project_revision(self.original), proposal['result_revision'])
        self.assertIn('return a + b;', (self.original / 'Assets/Calculator.cs').read_text())
        self.assertIn('return a * b;', (self.original / 'Assets/Multiplier.cs').read_text())
        original_calls = [command for project, command in self.native_calls if project == str(self.original)]
        self.assertEqual(len(original_calls), 6)
        self.assertEqual(set(original_calls[-1][original_calls[-1].index('-testFilter') + 1].split(';')),
                         {'CalculatorTests.AddReturnsSum', 'MultiplierTests.Multiplies'})
        self.assertEqual(result.get('dag_decision_diagnostics', []), [])

    def test_zero_final_union_tests_cannot_adopt_a_single_child_or_prefix_gate(self):
        self.workers()
        proposal = self.plane.create_integration_plan(run_id='parallel-fixes')
        approval = self.plane.approve_integration(integration_plan_id=proposal['integration_plan_id'])
        parameters = self.runtime(self.original, zero_final_tests=True)
        result = self.plane.integrate_workspace_results(run_id='parallel-fixes',
            integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
            original_parameters=parameters)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertNotEqual(result['final_gates']['editmode'], 'passed')
        count = len(self.native_calls)
        repeated = self.plane.integrate_workspace_results(run_id='parallel-fixes',
            integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
            original_parameters=parameters)
        self.assertEqual(repeated['status'], 'blocked')
        self.assertEqual(len(self.native_calls), count)

    def test_revoked_approval_and_changed_original_never_apply(self):
        from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
        self.workers()
        proposal = self.plane.create_integration_plan(run_id='parallel-fixes')
        approval = self.plane.approve_integration(integration_plan_id=proposal['integration_plan_id'])
        ApprovalDecisionStore(self.plane.state_store.layout.root).revoke(approval['approval_ref'])
        before = project_revision(self.original)
        with self.assertRaises(ValueError):
            self.plane.integrate_workspace_results(run_id='parallel-fixes',
                integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
                original_parameters=self.runtime(self.original))
        self.assertEqual(project_revision(self.original), before)
        approval = self.plane.approve_integration(integration_plan_id=proposal['integration_plan_id'])
        (self.original / 'Assets/User.cs').write_text('class User {}')
        before = project_revision(self.original)
        with self.assertRaises(ValueError):
            self.plane.integrate_workspace_results(run_id='parallel-fixes',
                integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
                original_parameters=self.runtime(self.original))
        self.assertEqual(project_revision(self.original), before)

    def test_save_failure_after_original_patch_cannot_replay_even_if_preimage_is_restored(self):
        self.workers()
        proposal = self.plane.create_integration_plan(run_id='parallel-fixes')
        approval = self.plane.approve_integration(integration_plan_id=proposal['integration_plan_id'])
        original_source = (self.original / 'Assets/Calculator.cs').read_bytes()
        append = self.plane.evidence_store.append
        def interrupted(record, **kwargs):
            if record.get('capability') == 'source.patch' and record.get('project_root') == str(self.original):
                raise OSError('fixture persistence failure after original mutation')
            return append(record, **kwargs)
        parameters = self.runtime(self.original)
        with patch.object(self.plane.evidence_store, 'append', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.plane.integrate_workspace_results(run_id='parallel-fixes',
                    integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
                    original_parameters=parameters)
        self.assertIn('return a + b;', (self.original / 'Assets/Calculator.cs').read_text())
        (self.original / 'Assets/Calculator.cs').write_bytes(original_source)
        count = len(self.native_calls)
        with self.assertRaises(ValueError):
            self.plane.integrate_workspace_results(run_id='parallel-fixes',
                integration_plan_id=proposal['integration_plan_id'], approval_ref=approval['approval_ref'],
                original_parameters=parameters)
        self.assertEqual(len(self.native_calls), count)
