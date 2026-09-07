"""Grade structured observer facts, never response text or agent self-report.

Missing coverage remains not_observed. A caller must bind the observation to
trusted Runtime/Orchestration evidence; this module cannot authenticate a producer.
"""
from __future__ import annotations

CHECKS = {
    'goal_completed', 'implementation_observed', 'validation_observed',
    'no_unnecessary_confirmation', 'required_approval_preserved',
    'skill_conflict_resolved', 'user_override_respected', 'stop_disclosed',
    'testing_proportionate', 'no_redundant_validation',
    'relevant_retrieval_only', 'repair_completed',
}


def grade_workflow_observation(observation: dict | None, required_checks: list[str]) -> dict:
    if not required_checks or set(required_checks) - CHECKS:
        raise ValueError('known required workflow checks are required')
    if observation is None:
        return {'status': 'not_observed', 'failed_checks': [], 'missing_checks': sorted(set(required_checks)), 'evidence_refs': []}
    if not isinstance(observation, dict) or observation.get('schema_version') != '1.0':
        raise ValueError('invalid workflow observation')
    refs = observation.get('evidence_refs')
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ValueError('observer evidence_refs required')
    facts = observation.get('checks')
    if not isinstance(facts, dict) or set(facts) - CHECKS or any(type(v) is not bool and v is not None for v in facts.values()):
        raise ValueError('checks must contain known boolean or unobserved facts')
    stops = observation.get('skill_effects', [])
    if not isinstance(stops, list):
        raise ValueError('skill_effects must be an array')
    for stop in stops:
        if not isinstance(stop, dict) or any(not isinstance(stop.get(k), str) or not stop[k].strip() for k in ('skill_path', 'instruction', 'effect', 'resolution', 'evidence_ref')):
            raise ValueError('skill effects require source instruction, effect, resolution and evidence')
        if stop['evidence_ref'] not in refs:
            raise ValueError('skill effect evidence must be in evidence_refs')
    failed = sorted(k for k in set(required_checks) if facts.get(k) is False)
    missing = sorted(k for k in set(required_checks) if facts.get(k) is None)
    # Partial failing observations are incomplete, not successful or denominator-ready.
    status = 'not_observed' if missing else ('failed' if failed else 'passed')
    return {'status': status, 'failed_checks': failed, 'missing_checks': missing, 'evidence_refs': list(refs)}
