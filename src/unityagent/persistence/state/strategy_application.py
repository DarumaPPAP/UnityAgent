"""適用の準備・受理・dispatch・確定を既存観測とは別のimmutable記録に保存する。"""
from copy import deepcopy

from unityagent.persistence.store.atomic_store import relative_ref, sha256_json, write_immutable_json


def save_application(plane, state, payload):
    refs = state['strategy_application_refs']
    value = {'schema_version': '1.0', 'target': {'kind': 'parent_dag', 'run_id': state['run_id']},
             'sequence': len(refs), 'previous_ref': refs[-1] if refs else None, **deepcopy(payload)}
    layout = plane.state_store.layout
    path = layout.snapshot(state['run_id'], 'strategy-application', sha256_json(value))
    write_immutable_json(path, value)
    refs.append(relative_ref(layout.root, path))
    # current更新に失敗した場合も、呼出し側はdispatchを開始しない。
    plane.state_store.save_task_state(state)
    return refs[-1]
