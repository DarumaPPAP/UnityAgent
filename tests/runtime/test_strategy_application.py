"""同一親Runの調整モードを実行検証へ接続する契約。"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.orchestration import test_task_execution as dag


class StrategyApplicationTests(unittest.TestCase):
    setUp = dag.TaskDagTests.setUp
    task = dag.TaskDagTests.task
    run_tasks = dag.TaskDagTests.run_tasks
    execute_file = dag.TaskDagTests.execute_file

    def test_reader_verifies_each_boundary_once_but_rechecks_on_the_next_read(self):
        from unityagent.orchestration.routing import strategy_application as reader
        from unityagent.persistence.store.atomic_store import PersistenceError
        state = self.run_tasks([self.task('a'), self.task('b')], adaptive_strategy_enabled=True)
        ref = state['strategy_application_refs'][-1]
        with patch.object(reader, 'read_dag_decision', wraps=reader.read_dag_decision) as verify:
            reader.read_strategy_application(self.root / 'state', ref, run_id='dag-test')
        references = [call.args[1] for call in verify.call_args_list]
        self.assertEqual(len(references), len(set(references)))
        evidence = state['tasks']['a']['result']['evidence_refs'][0]
        path = self.plane.evidence_store.layout.evidence(evidence)
        value = json.loads(path.read_text())
        value['verification_status'] = 'unverified'
        path.write_text(json.dumps(value))
        with self.assertRaises((ValueError, PersistenceError)):
            reader.read_strategy_application(self.plane.state_store.layout.root, ref, run_id='dag-test')

    def applications(self, result):
        from unityagent.orchestration.routing.strategy_application import read_strategy_application
        return [read_strategy_application(self.plane.state_store.layout.root, ref, run_id='dag-test')
                for ref in result['strategy_application_refs']]

    def test_same_parent_promotes_for_repair_and_demotes_after_acceptance(self):
        original = self.execute_file
        calls = []
        def repairable(*args):
            calls.append(1)
            if len(calls) == 1:
                return {'status': 'failed', 'failure_class': 'execution_failed', 'reason': 'repair', 'evidence': []}
            return original(*args)
        self.execute_file = repairable
        task = self.task('a')
        task['repair_candidates'] = [self.task('repair')['entry_request']]
        result = self.run_tasks([task, self.task('b'), self.task('c', ['b'])], adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'verified')
        finalized = [item for item in self.applications(result) if item['phase'] == 'finalized']
        self.assertEqual([item['decision']['path'] for item in finalized], ['fast', 'standard', 'fast', 'orchestrated'])
        self.assertEqual([item['decision']['recommendation'] for item in finalized], ['initialize', 'promote', 'demote', 'promote'])
        self.assertTrue(all(item['target'] == {'kind': 'parent_dag', 'run_id': 'dag-test'} for item in finalized))
        self.assertEqual(finalized[1]['receipt']['checks'], ['prepared_binding', 'prior_acceptance'])
        self.assertEqual(finalized[-1]['receipt']['checks'], ['prepared_binding', 'prior_acceptance', 'fixed_dag'])
        self.assertEqual(len(calls), 4)
        for item in finalized:
            self.assertTrue(item['applied'])
        self.assertEqual(finalized[0]['gates'], {'project': 'failed'})
        self.assertTrue(all(item['gates'] == {'project': 'passed'} for item in finalized[1:]))

    def test_disabled_keeps_legacy_state_and_never_consumes_strategy(self):
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=AssertionError('unexpected')):
            result = self.run_tasks([self.task('a')])
        self.assertEqual(result['status'], 'verified')
        self.assertNotIn('strategy_application_refs', result)
        self.assertNotIn('adaptive_strategy_enabled', result)

    def test_orchestrated_demotes_and_can_promote_again_in_same_parent(self):
        first = self.task('a')
        first['resource_claims'] = ['fixture-resource']
        state = self.run_tasks([first, self.task('b'), self.task('c', ['b'])], adaptive_strategy_enabled=True)
        finalized = [item for item in self.applications(state) if item['phase'] == 'finalized']
        self.assertEqual(state['status'], 'verified')
        self.assertEqual([item['decision']['path'] for item in finalized], ['orchestrated', 'fast', 'orchestrated'])
        self.assertEqual([item['decision']['recommendation'] for item in finalized], ['initialize', 'demote', 'promote'])
        self.assertEqual(len(self.calls), 3)

    def test_asset_change_after_preparation_cannot_reach_provider(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def changed(*args, **kwargs):
            (self.project / 'Assets/changed.txt').write_text('changed after preparation')
            return consume_strategy(*args, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Project revision'):
                self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            self.run_tasks([self.task('a')], resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])

    def test_asset_change_during_dispatch_marker_persistence_cannot_reach_provider(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        def changed(path, payload):
            result = write_immutable_json(path, payload)
            if path.parent.name == 'strategy-application' and payload['phase'] == 'dispatching':
                (self.project / 'Assets/changed.txt').write_text('changed during persistence')
            return result
        with patch('unityagent.persistence.state.strategy_application.write_immutable_json', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Project revision'):
                self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])

    def test_resume_rejects_deleted_application_files_for_executed_attempt(self):
        tasks = [self.task('a'), self.task('b')]
        state = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        for ref in state['strategy_application_refs'][4:]:
            (self.plane.state_store.layout.root / ref).unlink()
        state['strategy_application_refs'] = state['strategy_application_refs'][:4]
        self.plane.state_store.save_task_state(state)
        with self.assertRaises(ValueError):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 2)

    def test_reader_rejects_repeated_attempt_and_forged_prepared_revision(self):
        from copy import deepcopy
        from unityagent.orchestration.routing.strategy_application import read_strategy_application
        from unityagent.persistence.store.atomic_store import sha256_json, write_immutable_json, relative_ref
        state = self.run_tasks([self.task('a'), self.task('b')], adaptive_strategy_enabled=True)
        layout = self.plane.state_store.layout
        original = [json.loads((layout.root / ref).read_text()) for ref in state['strategy_application_refs']]
        for change in ('revision', 'repeat'):
            with self.subTest(change=change):
                records = deepcopy(original)
                if change == 'revision':
                    prepared = json.loads((layout.root / records[-1]['preparation_ref']).read_text())
                    prepared['project_revisions'] = {key: 'sha256:' + '0' * 64 for key in prepared['project_revisions']}
                    path = layout.snapshot('dag-test', 'strategy-preparation', sha256_json(prepared))
                    write_immutable_json(path, prepared)
                    for item in records[4:]:
                        item['preparation_ref'] = relative_ref(layout.root, path)
                        if item['receipt']:
                            item['receipt']['preparation_digest'] = sha256_json(prepared)
                else:
                    for item in deepcopy(original[:4]):
                        item['prior_boundary_ref'] = original[-1]['boundary_ref']
                        item['decision']['current_path'] = 'fast'
                        item['decision']['recommendation'] = 'keep'
                        records.append(item)
                previous = None
                for sequence, item in enumerate(records):
                    item['sequence'], item['previous_ref'] = sequence, previous
                    path = layout.snapshot('dag-test', 'strategy-application', sha256_json(item))
                    write_immutable_json(path, item)
                    previous = relative_ref(layout.root, path)
                with self.assertRaises(ValueError):
                    read_strategy_application(layout.root, previous, run_id='dag-test')

    def test_completed_resume_preserves_applications_and_cannot_toggle_mode(self):
        tasks = [self.task('a')]
        first = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        second = self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(first['strategy_application_refs'], second['strategy_application_refs'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(ValueError, 'mode'):
            self.run_tasks(tasks, resume=True)

    def test_runtime_rejects_changed_prepared_fact_before_provider(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def change(*args, **kwargs):
            (self.project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: changed\n')
            return consume_strategy(*args, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=change):
            result = self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.applications(result)[-1]['phase'], 'rejected')
        self.assertFalse(self.applications(result)[-1]['applied'])

    def test_application_persistence_failure_blocks_dispatch(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        def failing(path, payload):
            if path.parent.name == 'strategy-application' and payload['phase'] == 'accepted':
                raise OSError('fixture disk failure')
            return write_immutable_json(path, payload)
        with patch('unityagent.persistence.state.strategy_application.write_immutable_json', side_effect=failing):
            with self.assertRaises(OSError):
                self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, 'Uncertain'):
            self.run_tasks([self.task('a')], resume=True, adaptive_strategy_enabled=True)

    def test_tampered_application_blocks_resume_without_replay(self):
        tasks = [self.task('a')]
        first = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        path = self.plane.state_store.layout.root / first['strategy_application_refs'][-1]
        data = json.loads(path.read_text())
        data['applied'] = False
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 1)

    def test_preparation_is_shared_without_extra_project_scans_or_provider_calls(self):
        from unityagent.control_plane import unity_agent_control_plane as control
        from unityagent.control_plane import task_execution
        with patch.object(control, 'derive_context_inputs', wraps=control.derive_context_inputs) as derive, patch.object(
                control, 'build_context_manifest', wraps=control.build_context_manifest) as build, patch.object(
                task_execution, 'project_revision', wraps=task_execution.project_revision) as revision:
            result = self.run_tasks([self.task('a'), self.task('b')], adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual((derive.call_count, build.call_count, revision.call_count, len(self.calls)), (2, 2, 5, 2))

    def test_runtime_orchestrated_audit_rejects_changed_dependency_state(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def change(decision, preparation, **kwargs):
            if preparation['task_id'] == 'b':
                # 実際の状態が変わった場合、追加監査がProvider到達を止める。
                state = self.plane.state_store.load_task_state('dag-test')
                state['tasks']['a']['gates']['project'] = 'not_observed'
                self.plane.state_store.save_task_state(state)
            return consume_strategy(decision, preparation, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=change):
            result = self.run_tasks([self.task('a'), self.task('b', ['a'])], adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(self.calls), 1)

    def test_finalization_failure_preserves_evidence_and_stops_next_dispatch(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        def failing(path, payload):
            if path.parent.name == 'strategy-application' and payload['phase'] == 'finalized':
                raise OSError('fixture finalization failure')
            return write_immutable_json(path, payload)
        tasks = [self.task('a'), self.task('b')]
        with patch('unityagent.persistence.state.strategy_application.write_immutable_json', side_effect=failing):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                self.run_tasks(tasks, adaptive_strategy_enabled=True)
        state = self.plane.state_store.load_task_state('dag-test')
        self.assertTrue(state['tasks']['a']['result']['evidence_refs'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)

    def test_interrupted_dispatch_cannot_be_replayed_by_resume(self):
        def interrupted(*args):
            self.calls.append('started')
            raise KeyboardInterrupt('fixture interruption')
        self.execute_file = interrupted
        tasks = [self.task('a')]
        with self.assertRaises(KeyboardInterrupt):
            self.run_tasks(tasks, adaptive_strategy_enabled=True)
        state = self.plane.state_store.load_task_state('dag-test')
        self.assertEqual(self.applications(state)[-1]['phase'], 'interrupted')
        with self.assertRaisesRegex(ValueError, 'Uncertain'):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, ['started'])

    def test_world_plan_specialist_promotion_and_demotion_reach_fixed_acceptance(self):
        from tests.runtime.test_reasoning_runtime_handoff import ReasoningRuntimeHandoffTests, process_result
        from unityagent.runtime.runner.codex import codex_runner
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        world = self.task('b')
        world['entry_request']['intent'] = {'kind': 'world_planning', 'world_goal': 'Plan a dungeon', 'scene_scope': 'Assets/Scenes/Dungeon'}
        world['required_gates'] = {'plan': ['world_plan']}
        tasks = [self.task('a'), world, self.task('c')]
        params = {task['id']: {'environment_snapshot': self.snapshot,
            'context': ResolutionContext(policy_allowed=True), 'executors': {'file': self.execute_file},
            'specialist_pilot_enabled': True, 'reasoning_model': 'gpt-fixture', 'reasoning_command_prefix': ['codex']}
            for task in tasks}
        def fake_process(command, **kwargs):
            artifact = ReasoningRuntimeHandoffTests.artifact(None, command)
            Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(artifact))
            return process_result()
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'), patch.object(
                codex_runner, 'run_streaming_process', side_effect=fake_process) as process:
            result = self.plane.execute_tasks(tasks, run_id='dag-test', definition_fingerprint=self.definition,
                task_parameters=params, adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'verified', result.get('strategy_application_diagnostics'))
        self.assertEqual(result['tasks']['b']['gates'], {'plan': 'passed'})
        finalized = [item for item in self.applications(result) if item['phase'] == 'finalized']
        self.assertEqual([item['decision']['path'] for item in finalized], ['fast', 'standard', 'fast'])
        self.assertEqual(process.call_count, 1)

    def test_resume_rejects_removed_application_suffix_and_changed_task_state(self):
        tasks = [self.task('a'), self.task('b')]
        first = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        state = self.plane.state_store.load_task_state('dag-test')
        state['strategy_application_refs'] = state['strategy_application_refs'][:4]
        self.plane.state_store.save_task_state(state)
        with self.assertRaises(ValueError):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        state = first.copy()
        state['tasks']['a']['semantic_retries'] = 1
        self.plane.state_store.save_task_state(state)
        with self.assertRaisesRegex(ValueError, 'history|budget|Acceptance'):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 2)

    def test_resume_rejects_forged_disabled_mode_and_keeps_legacy_resume(self):
        tasks = [self.task('a')]
        result = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        result.pop('adaptive_strategy_enabled')
        result.pop('strategy_application_refs')
        self.plane.state_store.save_task_state(result)
        with self.assertRaisesRegex(ValueError, 'mode|history'):
            self.run_tasks(tasks, resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_changed_definition_or_scope_after_preparation_cannot_dispatch(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def changed(decision, preparation, **kwargs):
            preparation['handoff']['mutation_scope'] = {'allowed_paths': ['Assets/unapproved.asset'], 'prohibited_paths': []}
            return consume_strategy(decision, preparation, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=changed):
            result = self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.calls, [])

    def test_all_application_stages_fail_closed_before_dispatch(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        for phase in ('prepared', 'dispatching'):
            with self.subTest(phase=phase):
                self.setUp()
                def failing(path, payload):
                    if path.parent.name == 'strategy-application' and payload['phase'] == phase:
                        raise OSError('fixture ' + phase)
                    return write_immutable_json(path, payload)
                with patch('unityagent.persistence.state.strategy_application.write_immutable_json', side_effect=failing):
                    with self.assertRaises(OSError):
                        self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
                self.assertEqual(self.calls, [])

    def test_blocked_policy_and_unobserved_gate_are_not_repaired_by_promotion(self):
        self.execute_file = lambda *args: {'status': 'failed', 'failure_class': 'blocked_by_policy', 'evidence': []}
        task = self.task('a')
        task['repair_candidates'] = [self.task('repair')['entry_request']]
        result = self.run_tasks([task], adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tasks']['a']['semantic_retries'], 0)
        self.assertEqual([item['decision']['path'] for item in self.applications(result) if item['phase'] == 'finalized'], ['fast'])

    def test_legitimate_dependency_blocker_does_not_reject_independent_orchestrated_task(self):
        original = self.execute_file
        attempts = []
        def failing_first(*args):
            attempts.append(1)
            if len(attempts) == 1:
                return {'status': 'failed', 'failure_class': 'execution_failed', 'evidence': []}
            return original(*args)
        self.execute_file = failing_first
        independent = self.task('c')
        independent['resource_claims'] = ['claim-c']
        result = self.run_tasks([self.task('a'), self.task('b', ['a']), independent], adaptive_strategy_enabled=True)
        self.assertEqual(result['tasks']['b']['status'], 'blocked_dependency')
        self.assertEqual(result['tasks']['c']['status'], 'verified')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.applications(result)[-1]['phase'], 'finalized')

    def test_resume_rejects_changed_coordination_path_and_child_result_binding(self):
        tasks = [self.task('a')]
        self.run_tasks(tasks, adaptive_strategy_enabled=True)
        state = self.plane.state_store.load_task_state('dag-test')
        state['coordination_path'] = 'orchestrated'
        self.plane.state_store.save_task_state(state)
        with self.assertRaisesRegex(ValueError, 'coordination|mode'):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        state['coordination_path'] = 'fast'
        state['tasks']['a']['result']['context_manifest_ref'] = 'forged'
        self.plane.state_store.save_task_state(state)
        with self.assertRaisesRegex(ValueError, 'result|Context|binding'):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 1)

    def test_specialist_context_rematerialization_keeps_initial_receipt_and_final_acceptance(self):
        from unityagent.control_plane import unity_agent_control_plane as control
        original = control.resolve_specialist
        def observed(*args, **kwargs):
            return {**original(*args, **kwargs), 'required_observation_capabilities': ['project.inspect']}
        with patch.object(control, 'resolve_specialist', side_effect=observed):
            self.test_world_plan_specialist_promotion_and_demotion_reach_fixed_acceptance()
        state = self.plane.state_store.load_task_state('dag-test')
        applications = self.applications(state)
        final = next(item for item in applications if item['task_id'] == 'b' and item['phase'] == 'finalized')
        prepared = json.loads((self.plane.state_store.layout.root / final['preparation_ref']).read_text())
        result = state['tasks']['b']['result']
        self.assertNotEqual(prepared['manifest_ref'], result['context_manifest_ref'])
        self.assertEqual(result['handoff']['runtime_action']['kind'], 'specialist_reasoning')
        self.assertEqual(final['gates'], {'plan': 'passed'})

    def test_persisted_dispatch_marker_does_not_bypass_fact_freshness(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        def changed(path, payload):
            result = write_immutable_json(path, payload)
            if path.parent.name == 'strategy-application' and payload['phase'] == 'dispatching':
                (self.project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: changed\n')
            return result
        with patch('unityagent.persistence.state.strategy_application.write_immutable_json', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.run_tasks([self.task('a')], adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])

    def test_reader_binds_every_application_to_the_fixed_contract_and_latest_boundary(self):
        from copy import deepcopy
        from unityagent.orchestration.routing.strategy_application import read_strategy_application
        from unityagent.persistence.store.atomic_store import sha256_json, write_immutable_json, relative_ref
        state = self.run_tasks([self.task('a'), self.task('b')], adaptive_strategy_enabled=True)
        layout = self.plane.state_store.layout
        contract = json.loads((layout.root / state['contract_ref']).read_text())
        contract['tasks'][0]['goal'] = 'changed fixed goal'
        path = layout.snapshot('dag-test', 'task-contract', sha256_json(contract['tasks']))
        write_immutable_json(path, contract)
        alternate = relative_ref(layout.root, path)
        original = [json.loads((layout.root / ref).read_text()) for ref in state['strategy_application_refs']]
        for change in ('contract', 'boundary'):
            with self.subTest(change=change):
                previous = None
                for item in deepcopy(original):
                    item['previous_ref'] = previous
                    if change == 'contract':
                        item['contract_ref'] = alternate
                    elif item['task_id'] == 'b':
                        item['prior_boundary_ref'] = None
                    path = layout.snapshot('dag-test', 'strategy-application', sha256_json(item))
                    write_immutable_json(path, item)
                    previous = relative_ref(layout.root, path)
                with self.assertRaises(ValueError):
                    read_strategy_application(layout.root, previous, run_id='dag-test')

    def test_resume_rejects_changed_budget_counters_or_attempt_descriptor(self):
        from copy import deepcopy
        tasks = [self.task('a')]
        self.run_tasks(tasks, adaptive_strategy_enabled=True)
        original = self.plane.state_store.load_task_state('dag-test')
        for change in ('budget', 'attempt'):
            with self.subTest(change=change):
                state = deepcopy(original)
                if change == 'budget':
                    state['tasks']['a']['budget_counts']['global_replans'] = 1
                else:
                    state['tasks']['a']['handoff_history'][0]['requested_subagent'] = 'qa_subagent'
                self.plane.state_store.save_task_state(state)
                with self.assertRaises(ValueError):
                    self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 1)

    def test_rejected_application_stops_remaining_dispatch_and_resume_does_not_replay(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def reject(decision, preparation, **kwargs):
            if preparation['task_id'] == 'a':
                raise ValueError('fixture rejected preparation')
            return consume_strategy(decision, preparation, **kwargs)
        tasks = [self.task('a'), self.task('b')]
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=reject):
            result = self.run_tasks(tasks, adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tasks']['b']['status'], 'pending')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.applications(result)[-1]['phase'], 'rejected')
        with self.assertRaises(ValueError):
            self.run_tasks(tasks, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(self.calls, [])

    def test_standard_consumes_prior_evidence_audit_before_the_next_provider(self):
        from unityagent.persistence.store.atomic_store import PersistenceError
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def tampered(decision, preparation, **kwargs):
            if preparation['task_id'] == 'b':
                state = self.plane.state_store.load_task_state('dag-test')
                evidence_id = state['tasks']['a']['result']['evidence_refs'][0]
                path = self.plane.evidence_store.layout.evidence(evidence_id)
                evidence = json.loads(path.read_text())
                evidence['verification_status'] = 'unverified'
                path.write_text(json.dumps(evidence))
            return consume_strategy(decision, preparation, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=tampered):
            with self.assertRaises(PersistenceError):
                self.test_world_plan_specialist_promotion_and_demotion_reach_fixed_acceptance()
        # 名前やreceiptだけを変えても、bのProvider到達を防がなければこの検証は失敗する。
        self.assertEqual(self.calls, ['project.inspect'])
