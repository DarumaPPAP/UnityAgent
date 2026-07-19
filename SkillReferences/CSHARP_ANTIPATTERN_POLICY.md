# C# Anti-pattern Policy

## Finding confidence

- Confirmed: backed by profiler, test, runtime evidence or deterministic semantics.
- High confidence: source and platform characteristics strongly indicate a problem.
- Evidence required: compiler, workload or target device can reverse the conclusion.

## Severity

- Error: correctness, AOT, serialization, thread-safety or security failure.
- Warning: likely runtime or maintainability cost under stated conditions.
- Suggestion: local improvement with limited impact.
- Evidence Required: do not change before measurement.

## Safe patch levels

- Safe: local semantic-preserving change with no API/serialization impact.
- Review Required: behavior, allocation, scheduling or compatibility may change.
- Manual Only: public API, serialized data, save format, class/struct identity, async propagation, Job dependencies or architectural ownership changes.

## Review order

1. Specification and semantics
2. Ownership and lifetime
3. Correctness, AOT, thread and security risks
4. Runtime frequency and measured performance
5. Maintainability

Do not optimize based only on style preference. Do not claim performance improvement without suitable evidence.
