"""同一Task/環境/Trialの観測値だけを比較する。未計測値を補完しない。"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import statistics


def compare(samples):
    if not samples:
        return {'status':'BLOCKED_NOT_RUN','reason':'No measured paired trials','enable_by_default':False,
                'tokens':'unmeasured','latency':'unmeasured'}
    tasks = set()
    environments = set()
    pairs = {}
    for sample in samples:
        tasks.add(sample['task_digest'])
        environments.add(sample['environment_digest'])
        condition = sample['condition']
        trial = sample['trial_id']
        if condition not in {'compile','hot_reload'} or (trial,condition) in pairs:
            raise ValueError('Unknown condition or duplicate trial')
        latency = sample['latency_ms']
        if isinstance(latency,bool) or not isinstance(latency,(int,float)) or not math.isfinite(latency) or latency<0:
            raise ValueError('Latency must be an observed finite nonnegative number')
        for name in ('retries','fallbacks'):
            if isinstance(sample[name],bool) or not isinstance(sample[name],int) or sample[name]<0:
                raise ValueError('Retry/fallback counts must be observed nonnegative integers')
        tokens = sample['tokens']
        if tokens is not None and (isinstance(tokens,bool) or not isinstance(tokens,int) or tokens<0):
            raise ValueError('Tokens must be observed or null (unmeasured)')
        if not isinstance(sample['completed'],bool) or not isinstance(sample['regression'],bool) or not isinstance(sample['runtime_side_effects'],list):
            raise ValueError('Completion, regression and side effects must be observed facts')
        if sample['completed'] and any(sample[g]!='passed' for g in ('normal_compile','play_behavior','qa_acceptance')):
            raise ValueError('Completed trial requires ordinary Compile, Play behavior and QA acceptance')
        pairs[trial,condition] = sample
    if len(tasks)!=1 or len(environments)!=1 or len(pairs)%2 or any(
            (trial,other) not in pairs for trial,_ in pairs for other in ('compile','hot_reload')):
        raise ValueError('Comparison requires paired identical Task/Environment observations')
    conditions = {}
    for condition in ('compile','hot_reload'):
        rows = [s for s in samples if s['condition']==condition]
        latencies = sorted(s['latency_ms'] for s in rows)
        conditions[condition] = {'samples':len(rows),'median_ms':statistics.median(latencies),
            'p95_ms':latencies[math.ceil(len(latencies)*0.95)-1],
            'completion_rate':sum(s['completed'] for s in rows)/len(rows),
            'retry_count':sum(s['retries'] for s in rows),'fallback_count':sum(s['fallbacks'] for s in rows),
            'tokens':'unmeasured' if any(s['tokens'] is None for s in rows) else sum(s['tokens'] for s in rows),
            'regression_rate':sum(s['regression'] for s in rows)/len(rows),
            'runtime_side_effects':[effect for s in rows for effect in s['runtime_side_effects']]}
    baseline, candidate = conditions['compile'],conditions['hot_reload']
    improvement = (baseline['samples']>=5 and candidate['median_ms']<baseline['median_ms']
        and candidate['p95_ms']<baseline['p95_ms'] and candidate['completion_rate']>=baseline['completion_rate']
        and candidate['regression_rate']<=baseline['regression_rate'] and not candidate['runtime_side_effects'])
    return {'status':'compared','conditions':conditions,'improvement_observed':improvement,
            'enable_by_default':False,'recommendation':'keep_optional; review measured quality and side effects',
            'percentile_method':'nearest_rank','sample_provenance':'caller_supplied_observations; verify durable runtime evidence separately'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare(json.loads(args.samples.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return 0 if result['status']=='compared' else 1


if __name__=='__main__':
    raise SystemExit(main())
