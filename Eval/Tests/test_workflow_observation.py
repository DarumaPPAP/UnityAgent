from copy import deepcopy
from pathlib import Path
import unittest
import yaml
from Eval.Behavior.workflow_observation import grade_workflow_observation


class WorkflowObservationTests(unittest.TestCase):
    def test_seven_cases_accept_pass_reject_each_failure_and_missing_fact(self):
        path = Path(__file__).resolve().parents[1] / 'Datasets/Behavior/workflow-regression.yaml'
        cases = yaml.safe_load(path.read_text(encoding='utf-8'))['cases']
        self.assertEqual(len(cases), 7)
        for case in cases:
            required = case['required_checks']
            good = {'schema_version':'1.0', 'checks':dict.fromkeys(required, True), 'evidence_refs':['runtime:observed-events']}
            with self.subTest(case=case['id']):
                self.assertEqual(grade_workflow_observation(good, required)['status'], 'passed')
                self.assertEqual(grade_workflow_observation(None, required)['status'], 'not_observed')
                for key in required:
                    bad = deepcopy(good); bad['checks'][key] = False
                    self.assertEqual(grade_workflow_observation(bad, required)['failed_checks'], [key])
                    del bad['checks'][key]
                    self.assertEqual(grade_workflow_observation(bad, required)['status'], 'not_observed')

    def test_self_report_and_incomplete_skill_provenance_rejected(self):
        with self.assertRaises(ValueError):
            grade_workflow_observation({'schema_version':'1.0','checks':{'goal_completed':True}}, ['goal_completed'])
        observation = {'schema_version':'1.0','checks':{'stop_disclosed':True},'evidence_refs':['trace:1'], 'skill_effects':[{'skill_path':'skill'}]}
        with self.assertRaises(ValueError):
            grade_workflow_observation(observation, ['stop_disclosed'])
        observation['skill_effects'] = [{'skill_path':'skill','instruction':'ask first','effect':'confirmation','resolution':'existing authorization','evidence_ref':'trace:1'}]
        self.assertEqual(grade_workflow_observation(observation, ['stop_disclosed'])['status'], 'passed')

    def test_adapter_missing_observation_excluded_and_failure_attributed(self):
        from Eval.Behavior.runtime_adapter import adapt_execution_result
        result = {'schema_version':'1.0', 'run_id':'run', 'status':'passed',
                  'changed_paths':{'observation_state':'observed','paths':['source.cs']},
                  'runtime_failure':None, 'evidence_refs':['runtime:events']}
        args = dict(eval_id='eval', source_execution_result_ref='execution:1', required_workflow_checks=['goal_completed'])
        missing = adapt_execution_result(result, **args)
        self.assertFalse(missing['eval_record']['quality_denominator_eligible'])
        observation = {'schema_version':'1.0','checks':{'goal_completed':False},'evidence_refs':['workflow:1']}
        failed = adapt_execution_result(result, workflow_observation=observation, **args)
        self.assertEqual(failed['eval_record']['failure_class'], 'agent_behavior_regression')
        self.assertIn('workflow:1', failed['eval_record']['evidence_refs'])
        result['runtime_failure'] = {'failure_class':'runtime_timeout','observation_state':'not_observed','reason':'timeout'}
        infra = adapt_execution_result(result, workflow_observation=observation, **args)
        self.assertEqual(infra['eval_record']['failure_class'], 'runtime_timeout')
        self.assertFalse(infra['eval_record']['quality_denominator_eligible'])

    def test_non_boolean_fact_rejected(self):
        with self.assertRaises(ValueError):
            grade_workflow_observation({'schema_version':'1.0','checks':{'goal_completed':'true'}, 'evidence_refs':['x']}, ['goal_completed'])


if __name__ == '__main__':
    unittest.main()
