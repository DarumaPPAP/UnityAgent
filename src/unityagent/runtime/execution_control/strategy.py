"""調整モードを追加のdispatch前検証として消費する。実行権限は既存Guardが所有する。"""
from unityagent.persistence.store.atomic_store import sha256_json


def consume_strategy(decision, preparation, *, verify_prepared, verify_boundary, verify_dag):
    """Fastでも必須検証は省略しない。追加監査が拒否したAttemptを実行しない。"""
    path = decision['path']
    if path not in {'fast', 'standard', 'orchestrated'}:
        raise ValueError('Unsupported coordination mode')
    verify_prepared()
    checks = ['prepared_binding']
    if path in {'standard', 'orchestrated'}:
        verify_boundary()
        checks.append('prior_acceptance')
    if path == 'orchestrated':
        verify_dag()
        checks.append('fixed_dag')
    return {'path': path, 'checks': checks, 'preparation_digest': sha256_json(preparation)}
