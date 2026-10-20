"""固定Required Gateを観測Evidenceから判定し、修正先の判断材料を返す。"""

def assess_task(records, *, required_gates, run_id, definition_fingerprint, prior_context=None):
    observed = set()
    failed = unavailable = False
    for record in records:
        expected = definition_fingerprint
        if prior_context is not None:
            matches = record['evidence_id'] in prior_context['evidence_ids'] or any(
                record.get('capability') == request['capability'] and record['step_id'] == f"{prior_context['step_id']}-{index + 1}"
                for index, request in enumerate(prior_context['capability_requests']))
            if matches:
                expected = prior_context['definition_fingerprint']
                if any(expected.get(key) != value for key, value in definition_fingerprint.items() if key not in {'policy_revision', 'context_revision'}):
                    raise ValueError('Prior Context changed the fixed definition')
        if record['run_id'] != run_id or record['definition_fingerprint'] != expected:
            raise ValueError('Evidence task or definition revision mismatch')
        failed |= record['verification_status'] == 'failed'
        unavailable |= record['verification_status'] == 'unavailable'
        if (record['verification_status'] == 'passed' and record.get('observation_state') == 'observed'
                and record.get('completion') == 'verified'):
            observed.update(record.get('observed_evidence', []))
    gates = {gate: 'passed' if set(required) <= observed else
             'failed' if failed else 'unavailable' if unavailable else 'not_observed'
             for gate, required in required_gates.items()}
    return {'profile_id': 'qa_subagent', 'gates': gates,
            'verdict': 'verified' if all(v == 'passed' for v in gates.values()) else 'blocked',
            'failure_attribution': [
                {'gate': gate, 'status': status,
                 'required_observations': required_gates[gate],
                 'recommended_action': 'reproduce_and_replan' if status == 'failed' else 'collect_evidence'}
                for gate, status in gates.items() if status != 'passed'],
            'dispatch_performed': False}
