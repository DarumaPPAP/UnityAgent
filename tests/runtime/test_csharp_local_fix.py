import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

from tests.orchestration import test_task_execution as dag
from unityagent.control_plane.unity_agent_control_plane import validate_entry_request
from unityagent.control_plane.task_execution import project_revision
from unityagent.orchestration.routing.route_selector import task_fingerprint_from_intent, select_route, load_routes
from unityagent.resources import resource_root


class CSharpEntryTests(unittest.TestCase):
    setUp = dag.TaskDagTests.setUp

    def entry(self):
        source = self.project / 'Assets/Calculator.cs'
        source.write_text('public static class Calculator { public static int Add(int a, int b) { return a - b; } }\n')
        return {'schema_version': '2.0', 'request_id': 'local-fix', 'entry_point': 'codex_plugin',
                'project_root': str(self.project), 'intent': {'kind': 'csharp_local_fix',
                    'goal_or_confirmed_error': 'Add(3, 2) returns 1 instead of 5', 'target_source': 'Assets/Calculator.cs',
                    'expected_behavior': 'Add returns the sum of its arguments',
                    'allowed_changes': 'Correct the return expression in Add; preserve all declarations',
                    'expected_revision': project_revision(self.project), 'editmode_tests': ['CalculatorTests.AddReturnsSum']}}

    def test_typed_entry_selects_existing_csharp_contract(self):
        entry = self.entry()
        validate_entry_request(entry)
        fingerprint = task_fingerprint_from_intent(entry['intent'], self.snapshot,
            project_root=str(self.project), policy_allowed=True)
        route = select_route(fingerprint, load_routes(resource_root() / 'src/unityagent/orchestration/routing/task-routes.yaml'))
        self.assertEqual(route['route_id'], 'csharp-local-fix')

    def test_entry_rejects_unbounded_target_and_missing_test_selection(self):
        entry = self.entry()
        for value in ('Assets/../ProjectSettings/x.cs', 'Assets/User.prefab', '/tmp/User.cs'):
            with self.subTest(target=value):
                entry['intent']['target_source'] = value
                with self.assertRaises((ValueError, ValidationError)):
                    validate_entry_request(entry)
        entry = self.entry()
        entry['intent']['editmode_tests'] = []
        with self.assertRaises(ValidationError):
            validate_entry_request(entry)


class CSharpPatchScopeTests(unittest.TestCase):
    source = '''namespace Example {
public static class Calculator {
    public static int Add(int a, int b) { return a - b; }
}
}
'''

    def test_patch_changes_only_existing_method_return_expression(self):
        from unityagent.runtime.guardrails.csharp_patch import validate_csharp_patch
        updated = validate_csharp_patch(self.source, 'return a - b;', 'return a + b;')
        self.assertEqual(updated, self.source.replace('return a - b;', 'return a + b;'))

    def test_declaration_serialized_and_structural_changes_are_rejected(self):
        from unityagent.runtime.guardrails.csharp_patch import validate_csharp_patch
        for before, after in [('public static int Add', 'public static long Sum'),
                              ('namespace Example', 'namespace Other'),
                              ('return a - b;', 'return a + b; } public int UserField; {'),
                              ('return a - b;', 'return a + b; // comment out rest'),
                              ('return a - b;', 'return a + b;\n')]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                validate_csharp_patch(self.source, before, after)

    def test_fake_return_inside_comment_is_not_a_method_patch(self):
        from unityagent.runtime.guardrails.csharp_patch import validate_csharp_patch
        source = 'class C { /* int Fake() { return 1; } */ public int Real() { return 2; } }'
        with self.assertRaises(ValueError):
            validate_csharp_patch(source, 'return 1;', 'return 3;')


class CSharpBackendTests(unittest.TestCase):
    setUp = CSharpEntryTests.setUp
    entry = CSharpEntryTests.entry

    def test_alias_targets_never_mutate_scope_outside_the_approved_file(self):
        import os
        from unityagent.runtime.guardrails.csharp_patch import patch_revisions
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        request = self.patch_request()
        args = self.arguments()
        target = self.project / 'Assets/Calculator.cs'
        outside = self.root / 'outside.cs'
        original = target.read_bytes()
        outside.write_bytes(original)
        for alias in ('symlink', 'hardlink'):
            with self.subTest(alias=alias):
                target.unlink()
                if alias == 'symlink':
                    target.symlink_to(outside)
                else:
                    os.link(outside, target)
                with self.assertRaises(ValueError):
                    patch_revisions(self.project, 'Assets/Calculator.cs', 'return a - b;', 'return a + b;')
                result = self.provider.execute(request, ResolutionContext(policy_allowed=True,
                    approval_required=True, approval_complete=True), args)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(outside.read_bytes(), original)

    def patch_request(self):
        entry = self.entry()
        return {'schema_version': '1.0', 'capability': 'source.patch', 'operation_kind': 'source_mutation',
                'project_root': str(self.project), 'required_evidence': ['source_diff'],
                'mutation_scope': {'allowed_paths': ['Assets/Calculator.cs'], 'prohibited_paths': ['ProjectSettings', 'Packages']},
                'approval_ref': 'fixture-approval', 'preferred_surface': 'project'}

    def arguments(self):
        from unityagent.runtime.guardrails.csharp_patch import patch_revisions
        return {'bounded_csharp_patch': True, 'relative_path': 'Assets/Calculator.cs',
                'expected_text': 'return a - b;', 'replacement_text': 'return a + b;',
                **patch_revisions(self.project, 'Assets/Calculator.cs', 'return a - b;', 'return a + b;')}

    def test_bounded_backend_applies_exact_approved_preimage_and_preserves_newlines(self):
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        request = self.patch_request()
        source = self.project / 'Assets/Calculator.cs'
        source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
        original = source.read_bytes()
        result = self.provider.execute(request, ResolutionContext(policy_allowed=True, approval_required=True, approval_complete=True), self.arguments())
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(source.read_bytes(), original.replace(b'return a - b;', b'return a + b;'))

    def test_stale_revision_and_incomplete_approval_never_write(self):
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        request = self.patch_request()
        args = self.arguments()
        source = self.project / 'Assets/Calculator.cs'
        original = source.read_bytes()
        for context, arguments in [(ResolutionContext(policy_allowed=True, approval_required=True, approval_complete=False), args),
                (ResolutionContext(policy_allowed=True, approval_required=True, approval_complete=True), {**args, 'expected_revision': 'sha256:' + '0' * 64})]:
            result = self.provider.execute(request, context, arguments)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(source.read_bytes(), original)


class CSharpUnityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.xml = Path(self.temp.name) / 'results.xml'

    def test_zero_test_result_is_never_success(self):
        from unityagent.runtime.tooling.providers.native_unity_editor.log_parser import normalize_test_result
        self.xml.write_text('<test-run result="Passed" total="0" passed="0" failed="0"/>')
        result = normalize_test_result(exit_code=0, log_text='', test_results_path=self.xml)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['evidence'], [])

    def test_target_names_and_xml_run_time_must_match_the_current_execution(self):
        from datetime import datetime, timezone
        from unityagent.runtime.tooling.providers.native_unity_editor.log_parser import normalize_test_result
        import time
        now_ns = time.time_ns()
        now = datetime.now(timezone.utc).isoformat()
        self.xml.write_text(f'<test-run result="Passed" total="1" passed="1" failed="0" start-time="{now}" end-time="{now}"><test-case fullname="CalculatorTests.AddReturnsSum" result="Passed"/></test-run>')
        kwargs = dict(exit_code=0, log_text='', test_results_path=self.xml,
                      expected_test_names=['CalculatorTests.AddReturnsSum'], not_before_ns=now_ns)
        self.assertEqual(normalize_test_result(**kwargs)['status'], 'passed')
        self.assertEqual(normalize_test_result(**{**kwargs, 'expected_test_names': ['OtherTests.Unrelated']})['status'], 'failed')
        self.xml.write_text(self.xml.read_text().replace(now, '2020-01-01T00:00:00+00:00'))
        self.assertEqual(normalize_test_result(**kwargs)['status'], 'failed')

    def test_current_target_failure_remains_observed_failure(self):
        from unityagent.runtime.tooling.providers.native_unity_editor.log_parser import normalize_test_result
        from datetime import datetime, timezone
        import time
        started = time.time_ns()
        now = datetime.now(timezone.utc).isoformat()
        self.xml.write_text(f'<test-run result="Failed" total="1" passed="0" failed="1" start-time="{now}" end-time="{now}"><test-case fullname="CalculatorTests.AddReturnsSum" result="Failed"/></test-run>')
        result = normalize_test_result(exit_code=2, log_text='', test_results_path=self.xml,
            expected_test_names=['CalculatorTests.AddReturnsSum'], not_before_ns=started)
        self.assertEqual(result['failure_class'], 'observed_test_failure')


class CSharpProductTests(unittest.TestCase):
    setUp = CSharpEntryTests.setUp
    entry = CSharpEntryTests.entry

    def execute(self, entry, **kwargs):
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            return self.plane.execute(entry, run_id=kwargs.pop('run_id', 'csharp-plan'),
                environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
                executors={'file': self.provider.execute, **kwargs.pop('executors', {})},
                definition_fingerprint=self.definition, **kwargs)

    def fake_model(self, command, **kwargs):
        import json
        from types import SimpleNamespace
        workspace = Path(command[command.index('--cd') + 1])
        context = json.loads((workspace / 'patch-context.json').read_text())
        response = {'expected_text': 'return a - b;', 'replacement_text': 'return a + b;',
                    'summary': 'Correct the addition return expression', 'source_context_id': context['context_id'],
                    'source_context_fingerprint': context['context_fingerprint']}
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(response))
        from tests.runtime.test_reasoning_runtime_handoff import process_result
        return process_result()

    def test_typed_entry_creates_reviewable_plan_without_modifying_source(self):
        entry = self.entry()
        original = (self.project / entry['intent']['target_source']).read_bytes()
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process', side_effect=self.fake_model) as model:
            result = self.execute(entry, reasoning_model='gpt-fixture', reasoning_command_prefix=['codex'])
        self.assertEqual(result['status'], 'blocked', result)
        self.assertTrue(result.get('patch_plan_id'), result)
        self.assertEqual(result['reason'], 'explicit_patch_approval_required')
        self.assertEqual(model.call_count, 1)
        self.assertEqual((self.project / entry['intent']['target_source']).read_bytes(), original)

    def test_worker_cancellation_signal_reaches_the_existing_model_runner(self):
        import threading
        cancel = threading.Event()
        def model(command, **kwargs):
            self.assertIs(kwargs['cancel_event'], cancel)
            return self.fake_model(command, **kwargs)
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process', side_effect=model):
            result = self.execute(self.entry(), reasoning_model='gpt-fixture',
                                  reasoning_command_prefix=['codex'], cancel_event=cancel)
        self.assertEqual(result.get('reason'), 'explicit_patch_approval_required', result)

    def test_verification_only_reuses_typed_route_without_model_patch_or_approval(self):
        entry = self.entry()
        entry['intent']['verification_only'] = True
        native, calls = self.native_executor()
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process') as model:
            result = self.execute(entry, executors={'native_unity_editor': native})
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual([item['capability'] for item in result['results']],
                         ['source.read', 'compile.observe', 'project.test'])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['handoff']['mutation_scope'], {})
        model.assert_not_called()
        entry['intent']['patch_plan_id'] = 'a' * 64
        with self.assertRaises(ValidationError):
            validate_entry_request(entry)

    def test_idle_editor_does_not_require_a_fabricated_safe_mode_fact(self):
        entry = self.entry()
        entry['intent']['verification_only'] = True
        native, calls = self.native_executor()
        self.snapshot['unity_editor']['safe_mode'] = 'unknown'
        result = self.execute(entry, executors={'native_unity_editor': native})
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(self.snapshot['unity_editor']['safe_mode'], 'unknown')

    def native_executor(self, *, test_name='CalculatorTests.AddReturnsSum', total=1, compile_failed=False):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider
        editor = self.root / 'Unity.exe'
        editor.write_text('fixture')
        self.snapshot['unity_editor'].update(installed=True, version='6000.3.15f1', executable_path=str(editor),
            project_version_match=True, running=False, safe_mode=False, project_bound=False, binding_status='not_running')
        self.snapshot['filesystem']['writable_in_mutation_scope'] = True
        self.snapshot['test_framework']['available'] = True
        calls = []
        def dispatch(request, **kwargs):
            command = list(request.command)
            calls.append(command)
            Path(command[command.index('-logFile') + 1]).write_text('Assets/Calculator.cs(1,1): error CS1002: fixture failure\n' if compile_failed else 'Begin MonoManager ReloadAssembly\n')
            if '-testResults' in command:
                self.assertEqual(command[command.index('-testFilter') + 1], 'CalculatorTests.AddReturnsSum')
                now = datetime.now(timezone.utc).isoformat()
                cases = f'<test-case fullname="{test_name}" result="Passed"/>' if total else ''
                Path(command[command.index('-testResults') + 1]).write_text(
                    f'<test-run result="Passed" total="{total}" passed="{total}" failed="0" start-time="{now}" end-time="{now}">{cases}</test-run>')
            return {'status': 'passed', 'result': SimpleNamespace(returncode=0)}
        provider = NativeUnityEditorProvider(self.project, self.snapshot, dispatch_fn=dispatch,
            process_probe_fn=lambda **kwargs: [], temp_root=self.root / 'native-output')
        return provider.execute, calls

    def plan(self, entry):
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process', side_effect=self.fake_model):
            return self.execute(entry, reasoning_model='gpt-fixture', reasoning_command_prefix=['codex'])

    def test_approved_typed_path_reaches_patch_static_compile_and_targeted_editmode(self):
        from unityagent.control_plane.csharp_fix import approve_csharp_fix
        entry = self.entry()
        planned = self.plan(entry)
        approval = approve_csharp_fix(self.plane, planned['patch_plan_id'])
        entry['intent']['patch_plan_id'] = planned['patch_plan_id']
        entry['approval_ref'] = approval['approval_ref']
        native, calls = self.native_executor()
        with patch('unityagent.runtime.execution_control.resource_lease._lease_directory', wraps=__import__(
                'unityagent.runtime.execution_control.resource_lease', fromlist=['_lease_directory'])._lease_directory):
            result = self.execute(entry, run_id='csharp-apply', executors={'native_unity_editor': native})
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual([item['capability'] for item in result['results']],
                         ['source.read', 'source.patch', 'static.review', 'compile.observe', 'project.test'])
        self.assertEqual(len(calls), 2)
        self.assertIn('return a + b;', (self.project / 'Assets/Calculator.cs').read_text())
        self.assertEqual(result['result_revision'], project_revision(self.project))
        self.assertTrue(all(value == 'passed' for value in result['csharp_gates'].values()))
        self.assertTrue(all(self.plane.evidence_store.verify_record(ref)['completion'] == 'verified' for ref in result['evidence_refs']))

    def test_rejected_or_foreign_approval_never_patches(self):
        entry = self.entry()
        planned = self.plan(entry)
        original = (self.project / 'Assets/Calculator.cs').read_bytes()
        entry['intent']['patch_plan_id'] = planned['patch_plan_id']
        entry['approval_ref'] = 'unknown-approval'
        result = self.execute(entry, run_id='csharp-unapproved')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['evidence_refs'], [])
        self.assertEqual((self.project / 'Assets/Calculator.cs').read_bytes(), original)

    def approved(self, entry):
        from unityagent.control_plane.csharp_fix import approve_csharp_fix
        planned = self.plan(entry)
        approval = approve_csharp_fix(self.plane, planned['patch_plan_id'])
        entry['intent']['patch_plan_id'] = planned['patch_plan_id']
        entry['approval_ref'] = approval['approval_ref']
        return planned

    def test_revoked_approval_is_rechecked_before_any_mutation(self):
        from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
        entry = self.entry()
        self.approved(entry)
        original = (self.project / 'Assets/Calculator.cs').read_bytes()
        ApprovalDecisionStore(self.plane.state_store.layout.root).revoke(entry['approval_ref'])
        result = self.execute(entry, run_id='csharp-revoked')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['evidence_refs'], [])
        self.assertEqual((self.project / 'Assets/Calculator.cs').read_bytes(), original)

    def test_compile_failure_does_not_launch_editmode(self):
        entry = self.entry()
        self.approved(entry)
        native, calls = self.native_executor(compile_failed=True)
        result = self.execute(entry, run_id='csharp-compile-failed', executors={'native_unity_editor': native})
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(calls), 1)
        self.assertNotIn('project.test', [item['capability'] for item in result['results']])

    def test_zero_tests_cannot_pass_the_product_gate_or_replay_the_patch(self):
        entry = self.entry()
        self.approved(entry)
        native, calls = self.native_executor(total=0)
        result = self.execute(entry, run_id='csharp-zero-tests', executors={'native_unity_editor': native})
        self.assertEqual(result['status'], 'blocked')
        self.assertNotEqual(result['csharp_gates']['project.test'], 'passed')
        self.assertEqual(len(calls), 2)
        repeated = self.execute(entry, run_id='csharp-repeated', executors={'native_unity_editor': native})
        self.assertEqual(repeated['status'], 'blocked')
        self.assertEqual(repeated['evidence_refs'], [])
        self.assertEqual(len(calls), 2)

    def test_evidence_save_failure_after_patch_is_not_automatically_resent(self):
        entry = self.entry()
        self.approved(entry)
        source = self.project / 'Assets/Calculator.cs'
        original = source.read_bytes()
        self.snapshot['filesystem']['writable_in_mutation_scope'] = True
        append = self.plane.evidence_store.append
        def failing(record):
            if record.get('capability') == 'source.patch':
                raise OSError('fixture Evidence storage failure')
            return append(record)
        with patch.object(self.plane.evidence_store, 'append', side_effect=failing):
            with self.assertRaises(OSError):
                self.execute(entry, run_id='csharp-interrupted')
        self.assertIn('return a + b;', source.read_text())
        source.write_bytes(original)
        result = self.execute(entry, run_id='csharp-after-interruption')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['evidence_refs'], [])
        self.assertEqual(source.read_bytes(), original)

    def test_proposal_does_not_persist_full_source_or_prompt(self):
        import json
        original_model = self.fake_model
        def leaking_model(command, **kwargs):
            outcome = original_model(command, **kwargs)
            workspace = Path(command[command.index('--cd') + 1])
            context = json.loads((workspace / 'patch-context.json').read_text())
            response_path = Path(command[command.index('--output-last-message') + 1])
            response = json.loads(response_path.read_text())
            response['summary'] = context['source']
            response_path.write_text(json.dumps(response))
            return outcome
        with patch('unityagent.runtime.runner.codex.codex_runner.run_streaming_process', side_effect=leaking_model):
            self.execute(self.entry(), reasoning_model='gpt-fixture', reasoning_command_prefix=['codex'])
        for path in self.plane.state_store.layout.root.rglob('*.json'):
            self.assertNotIn('public static class Calculator', path.read_text(), str(path))
