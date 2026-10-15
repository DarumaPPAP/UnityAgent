"""固定Required Gateを観測Evidenceから判定し、修正先の判断材料を返す。"""

def assess_task(records, *, required_gates, run_id, definition_fingerprint):
    observed = set()
    failed = unavailable = False
    for record in records:
        if record['run_id'] != run_id or record['definition_fingerprint'] != definition_fingerprint:
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
