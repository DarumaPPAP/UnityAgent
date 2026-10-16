"""旧Performance IDをQA正本へ移行する。別Runtime/Profileを生成しない。"""
SUBAGENT_ID_ALIASES = {'performance_subagent': 'qa_subagent'}


def canonical_subagent_id(profile_id: str | None) -> str | None:
    return SUBAGENT_ID_ALIASES.get(profile_id, profile_id)
