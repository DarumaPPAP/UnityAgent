"""Session/JobをTaskに拘束し、曖昧なTimeoutの自動再送を防ぐ。"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

from unityagent.persistence.store.atomic_store import (
    safe_id, sha256_json, read_json, atomic_write_json, exclusive_file_lock,
)
from .rock_template import rock_template, ROCK_MARKER


def _observed_rock_record(mcp_reply):
    """MCPの文字列応答からレビュー済みTemplateのマーカーだけを取得する。"""
    contents = mcp_reply.get('content') if isinstance(mcp_reply, dict) else None
    if not isinstance(contents, list) or mcp_reply.get('isError'):
        raise ValueError('Blender MCP did not return a successful tool result')
    matches = []
    for part in contents:
        if not isinstance(part, dict) or part.get('type') != 'text':
            continue
        message = part.get('text', '')
        if ROCK_MARKER in message:
            prefix, marker, payload = message.partition(ROCK_MARKER)
            if not marker or not isinstance(payload, str):
                raise ValueError('Invalid Blender response')
            decoder = json.JSONDecoder()
            document = payload.lstrip()
            record, end = decoder.raw_decode(document)
            if document[end:].strip():
                raise ValueError('Unexpected trailing content after Blender Rock evidence')
            matches.append(record)
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError('Blender output lacks one trusted Rock observation')
    record = matches[0]
    if (record.get('schema_version') != '1.0' or record.get('object_name') != 'UnityAgentRock'
            or isinstance(record.get('vertices'), bool) or not isinstance(record.get('vertices'), int)
            or isinstance(record.get('triangles'), bool) or not isinstance(record.get('triangles'), int)
            or record['vertices'] <= 0 or record['triangles'] <= 0
            or record.get('scale') != [1, 1, 1] or not isinstance(record.get('uv_layers'), int)
            or record['uv_layers'] < 1 or record.get('texture_dependencies') != []):
        raise ValueError('Blender Rock observation failed geometry validation')
    dims = record.get('dimensions')
    if not isinstance(dims, list) or len(dims) != 3 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 1e6 for value in dims):
        raise ValueError('Blender Rock dimensions invalid')
    return record


class RockJob:
    def __init__(self, state_root, client, *, check_approval, session_lock_root=None):
        self.root = Path(state_root).resolve()
        self.client = client
        self.check_approval = check_approval
        if session_lock_root is None:
            from unityagent.runtime.guardrails.project_lease import _default_lock_root
            session_lock_root = _default_lock_root().parent / 'BlenderSessions'
        self.session_lock_root = Path(session_lock_root)

    def run(self, job_id, *, approval_ref):
        if not approval_ref or not getattr(self.client, 'blender_session_identity', None):
            raise ValueError('Blender Scene mutation requires Approval and observed Session binding')
        folder = self.root / 'blender-jobs' / safe_id(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        output, artifact_manifest = folder / 'Rock.fbx', folder / 'artifact.json'
        code = rock_template(output, artifact_manifest)
        digest = sha256_json({'template': code, 'approval_ref': approval_ref})
        state_path = folder / 'job.json'
        with exclusive_file_lock(self.session_lock_root / (safe_id(self.client.session_id) + '.lock')):
            if state_path.exists():
                state = read_json(state_path)
                if state['request_digest'] != digest or state['session_id'] != self.client.session_id:
                    raise ValueError('Blender Job request or Session changed; reconcile before resume')
                return state
            self.check_approval(digest)
            recheck = getattr(self.client, 'recheck_session', None)
            if callable(recheck):
                recheck()
            if output.exists() or artifact_manifest.exists():
                raise ValueError('Orphaned Rock artifact requires manual reconciliation before new mutation')
            state = {'schema_version': '1.0', 'job_id': job_id, 'session_id': self.client.session_id,
                     'approval_ref': approval_ref, 'request_digest': digest, 'status': 'submitted',
                     'submitted_at': datetime.now(timezone.utc).isoformat(),
                     'artifact_path': str(output), 'token_usage': 'unmeasured',
                     'backend_identity': getattr(self.client, 'identity', None),
                     'addon_version': getattr(self.client, 'addon_version', 'unmeasured')}
            atomic_write_json(state_path, state)
            try:
                result = self.client.tool('execute_blender_code', {'code': code})
                state['mcp_result'] = result
                artifact = _observed_rock_record(result)
                content = output.read_bytes()
                if len(content) < 1024 or not content.startswith(b'Kaydara FBX Binary  \x00\x1a\x00'):
                    raise ValueError('Expected binary FBX export is missing or truncated')
                measured_hash = hashlib.sha256(content).hexdigest()
                artifact.update(sha256=measured_hash, blender_version=getattr(self.client, 'blender_version', 'unmeasured'),
                                artifact=str(output))
                atomic_write_json(artifact_manifest, artifact)
                state.update(status='completed', artifact=artifact, artifact_hash=measured_hash)
            except (TimeoutError, OSError) as exc:
                state.update(status='uncertain', reason=str(exc))
            except (ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
                state.update(status='failed', reason=str(exc))
            atomic_write_json(state_path, state)
            return state
