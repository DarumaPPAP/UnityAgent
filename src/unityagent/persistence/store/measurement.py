"""Persistenceは数値を通知するだけで、Operationsや実行判断へ依存しない。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time

_sink = ContextVar('persistence_measurement_sink', default=None)


@contextmanager
def capture(sink):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def notify(event, value, unit):
    sink = _sink.get()
    if sink is not None:
        try:
            sink(event, value, unit)
        except Exception:
            pass


def observed(event):
    def decorate(operation):
        @wraps(operation)
        def execute(*args, **kwargs):
            if _sink.get() is None:
                return operation(*args, **kwargs)
            started = time.monotonic_ns()
            try:
                return operation(*args, **kwargs)
            finally:
                notify(event, (time.monotonic_ns() - started) / 1_000_000, 'ms')
        return execute
    return decorate
