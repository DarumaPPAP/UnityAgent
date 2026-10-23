"""確定処理とは独立した、固定数値だけのOperations計測。"""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time

from unityagent.operations.observability.event_store import OperationalEventStore
from unityagent.runtime.telemetry.builders import runtime_metric, runtime_span

PHASES = {'preparation', 'coordination', 'context', 'evidence', 'provider', 'lease', 'integration', 'gate', 'model', 'persistence'}
COUNTERS = {'selected_utf8_bytes': 'bytes', 'snapshot_bytes': 'bytes', 'estimated_tokens': 'estimated_tokens',
            'selected_artifacts': 'count', 'provider_calls': 'count', 'evidence_records': 'count',
            'plan_proposals': 'count', 'plan_rejections': 'count'}
_binding = ContextVar('execution_measurement_binding', default={})


def record_counters(plane, run_id, phase, **values):
    try:
        store = OperationalEventStore(plane.state_store.layout.root / 'operations')
        for name, value in values.items():
            if name in COUNTERS and type(value) in (int, float) and math.isfinite(value) and value >= 0:
                store.append('metric', runtime_metric(run_id=run_id, step_id=None,
                    metric_name='adaptive.' + phase + '.' + name, value=value, unit=COUNTERS[name],
                    attributes={**_binding.get(), 'phase': phase}))
    except Exception:
        pass


def record_model_usage(plane, run_id, usage):
    keys = {'usage_source', 'unit', 'scope', 'configured_model', 'model_revision', 'reasoning_effort',
            'completed_turns', 'input_tokens', 'cached_input_tokens', 'output_tokens'}
    try:
        safe = {key: value for key, value in (usage or {}).items() if key in keys}
        OperationalEventStore(plane.state_store.layout.root / 'operations').append('trace',
            runtime_span(run_id=run_id, step_id=None, event='adaptive.model_usage',
                         attributes={**_binding.get(), **safe}))
    except Exception:
        pass


@contextmanager
def measurement_binding(job):
    keys = {'parent_run_id', 'task_id', 'attempt', 'plan_digest', 'task_definition_digest', 'input_revision'}
    token = _binding.set({key: value for key, value in job.items() if key in keys})
    try:
        yield
    finally:
        _binding.reset(token)


@contextmanager
def capture_persistence(plane, run_id):
    from unityagent.persistence.store.measurement import capture
    def sink(event, value, unit):
        store = OperationalEventStore(plane.state_store.layout.root / 'operations')
        attributes = {**_binding.get(), 'clock': 'monotonic', 'aggregation': 'inclusive_per_phase'}
        store.append('metric', runtime_metric(run_id=run_id, step_id=None,
            metric_name='adaptive.' + event, value=value, unit=unit, attributes=attributes))
        if unit == 'ms':
            store.append('metric', runtime_metric(run_id=run_id, step_id=None,
                metric_name='adaptive.' + event + '.calls', value=1, unit='count', attributes=attributes))
    with capture(sink):
        yield


@contextmanager
def measured(plane, run_id, phase):
    if phase not in PHASES:
        raise ValueError('Unknown execution measurement phase')
    started, values, outcome = time.monotonic_ns(), {}, 'failed'
    try:
        yield values
        outcome = 'completed'
    finally:
        duration = (time.monotonic_ns() - started) / 1_000_000
        try:
            store = OperationalEventStore(plane.state_store.layout.root / 'operations')
            attributes = {**_binding.get(), 'phase': phase, 'outcome': outcome, 'clock': 'monotonic',
                          'aggregation': 'inclusive_per_phase'}
            for name, value, unit in [('duration', duration, 'ms'), ('calls', 1, 'count'),
                                      *((name, value, COUNTERS[name]) for name, value in values.items()
                                        if name in COUNTERS and type(value) in (int, float)
                                        and math.isfinite(value) and value >= 0)]:
                store.append('metric', runtime_metric(run_id=run_id, step_id=None,
                    metric_name='adaptive.' + phase + '.' + name, value=value, unit=unit, attributes=attributes))
        except Exception:
            # 補助記録の失敗は確定処理を再送させない。Evidenceの保存失敗は呼出し元で扱う。
            pass


def measured_call(plane, run_id, phase, operation, *args, **kwargs):
    with measured(plane, run_id, phase) as values:
        result = operation(*args, **kwargs)
        if phase == 'context' and isinstance(result, dict):
            budget = result.get('budget_report', {})
            values.update({key: budget.get(key) for key in ('selected_utf8_bytes', 'selected_artifacts', 'estimated_tokens')})
        if phase in {'provider', 'gate'} and isinstance(result, dict) and result.get('provider_result') is not None:
            values['provider_calls'] = 1
        return result
