import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('comparison',Path(__file__).parents[2]/'eval/production_e2e/compare_iterations.py')
comparison=importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def samples(self):
        return [{'trial_id':str(i),'task_digest':'task','environment_digest':'env','condition':condition,
                 'latency_ms':latency,'completed':True,'retries':0,'fallbacks':0,'tokens':None,
                 'normal_compile':'passed','play_behavior':'passed','qa_acceptance':'passed',
                 'runtime_side_effects':[], 'regression':False}
                for i in range(5) for condition,latency in [('compile',1000+i),('hot_reload',100+i)]]

    def test_paired_median_p95_and_missing_token_measurements(self):
        result=comparison.compare(self.samples())
        self.assertEqual(result['conditions']['compile']['median_ms'],1002)
        self.assertEqual(result['conditions']['hot_reload']['p95_ms'],104)
        self.assertEqual(result['conditions']['compile']['tokens'],'unmeasured')
        self.assertTrue(result['improvement_observed'])
        self.assertFalse(result['enable_by_default'])

    def test_missing_compile_gate_changed_task_and_unpaired_runs_are_rejected(self):
        for field,value in [('normal_compile','not_observed'),('task_digest','different'),('latency_ms',float('nan'))]:
            samples=self.samples(); samples[0][field]=value
            with self.assertRaises(ValueError): comparison.compare(samples)
        with self.assertRaises(ValueError): comparison.compare(self.samples()[:-1])

    def test_failed_attempts_reduce_completion_rate_and_disable_recommendation(self):
        samples=self.samples(); samples[1]['completed']=False
        result=comparison.compare(samples)
        self.assertEqual(result['conditions']['hot_reload']['completion_rate'],0.8)
        self.assertFalse(result['improvement_observed'])
